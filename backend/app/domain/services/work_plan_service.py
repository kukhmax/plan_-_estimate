"""Surface Work Plan domain service (Stage 10B.1 / 12D).

A SurfaceWorkPlan is the planning configuration for exactly one Surface:
the substrate, the agreed quality target, and an ordered list of Price Book
references. The plan never snapshots prices and never mutates a PriceItem;
archiving prevents its occurrence count from increasing while existing
occurrences may survive replacement. Ownership always resolves through
Surface -> Room -> Project -> Owner, so no tenancy columns exist on the plan.

Stage 12D adds an optional coefficient selection PER OCCURRENCE (never per
PriceItem). Per the approved Stage 12B architecture (Option C), a selection
has no identity of its own: it is validated in full BEFORE any mutation, then
deleted/recreated atomically together with its parent `SurfacePlannedWork`
row on every ordinary replace -- exactly like the row itself already is.
This requires no change to Stage 10's full-replace contract.

Stage 13B (D13) adds a stable logical `occurrence_key` per occurrence. Rows
are still deleted and recreated on every replace, but a payload entry that
echoes a CURRENT key of this plan (for the same PriceItem) is recreated with
that same key; an entry without a key is a new occurrence and gets a fresh,
server-generated key. Keys are validated in full before any mutation. The
technological break `wait_after_hours` (D9) is carried the same way as the
coefficient selection.
"""
import hashlib
import json
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes, selectinload

from app.domain.exceptions import (
    PriceItemNotFoundError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
    SurfaceWorkPlanNotFoundError,
    SurfaceWorkPlanOccurrenceConflictError,
    SurfaceWorkPlanValidationError,
    TemplateApplicationConflictError,
    TemplateApplicationStaleError,
    WorkflowTemplateNotFoundError,
)
from app.domain.rules.inspection_rules import assert_quality_scale_valid
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.models.checklist import QualityLevel, Substrate
from app.models.price_coefficient import CoefficientOption
from app.models.price_item import PriceCategory, PriceItem
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.work_plan import (
    SurfacePlannedWork,
    SurfacePlannedWorkCoefficientAssignment,
    SurfaceWorkPlan,
)
from app.models.workflow_template import (
    SurfaceWorkPlanTemplateApplication,
    TemplateApplicationMode,
    WorkflowTemplate,
    WorkflowTemplateStep,
)
from app.schemas.work_plan import (
    ApplyTemplateRequest,
    OrderedPriceItemSelection,
    TemplateApplicationIntent,
)


@dataclass(frozen=True)
class ResolvedOccurrence:
    """One validated planned-work occurrence ready to be (re)written: the
    PriceItem, its owner-scoped, order-preserved CoefficientOption selection,
    the existing `occurrence_key` to preserve (None = new occurrence, the
    server generates a key) and the technological break."""

    item: PriceItem
    options: list[CoefficientOption] = field(default_factory=list)
    occurrence_key: uuid.UUID | None = None
    wait_after_hours: int | None = None


def _application_fingerprint(plan_id: uuid.UUID, request: ApplyTemplateRequest) -> str:
    """Deterministic SHA-256 of the semantic apply-template request (13E.3).

    Covers the plan, template, mode, the optional-step selection (as a sorted
    set), the expected template version (ordered step ids) and, for REPLACE,
    the expected ordered plan composition. `application_id` itself is
    excluded: it is the key the fingerprint is compared under.
    """
    replace = request.mode == TemplateApplicationMode.REPLACE
    payload = {
        "v": 1,
        "work_plan_id": str(plan_id),
        "template_id": str(request.template_id),
        "mode": request.mode.value,
        "selected_optional_step_ids": sorted(str(i) for i in request.selected_optional_step_ids),
        "expected_step_ids": [str(i) for i in request.expected_step_ids],
        "expected_occurrence_keys": (
            [str(k) for k in request.expected_occurrence_keys]
            if replace and request.expected_occurrence_keys is not None
            else None
        ),
        "replace_confirmed": bool(request.replace_confirmed) if replace else None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _filter_allows(values: list[str] | None, value: str | None) -> bool:
    return not values or (value is not None and value in values)


class SurfaceWorkPlanService:
    """Owner-scoped operations over the per-surface work plan."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_surface_owned(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Surface:
        """Resolve the ownership chain and return the surface (or raise 404s)."""
        project_stmt = select(Project.id).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
        )
        if (await self.db.execute(project_stmt)).scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        room_stmt = select(Room.id).where(
            Room.id == room_id,
            Room.project_id == project_id,
        )
        if (await self.db.execute(room_stmt)).scalar_one_or_none() is None:
            raise RoomNotFoundError(f"Room {room_id} not found")

        surface_stmt = select(Surface).where(
            Surface.id == surface_id,
            Surface.room_id == room_id,
        )
        surface = (await self.db.execute(surface_stmt)).scalar_one_or_none()
        if surface is None:
            raise SurfaceNotFoundError(f"Surface {surface_id} not found")
        return surface

    async def _resolve_owned_items(
        self,
        owner_id: uuid.UUID,
        selection: list[OrderedPriceItemSelection],
        existing_counts: Counter[uuid.UUID],
    ) -> list[ResolvedOccurrence]:
        """Validate every selection row (PriceItem AND its coefficient
        selection) and return it in the given order. Called BEFORE any
        mutation, so any raised error leaves the existing plan untouched.

        Active items may be selected freely. An archived item's requested count
        cannot exceed the count already persisted on this same plan. Reveal
        (PriceCategory.REVEAL) work is planned per opening (Stage 10 D19), so a
        Surface plan may keep legacy reveal occurrences it already has but never
        gain new ones. Duplicate references and exact payload order are
        preserved.
        """
        if not selection:
            return []
        ids = [row.price_item_id for row in selection]
        requested_counts = Counter(ids)
        items = (
            await self.db.execute(select(PriceItem).where(PriceItem.id.in_(ids)))
        ).scalars().all()
        by_id = {item.id: item for item in items}
        coefficient_service = PriceCoefficientService(self.db)
        validated: list[ResolvedOccurrence] = []
        for row in selection:
            item = by_id.get(row.price_item_id)
            if item is None or item.owner_id != owner_id:
                raise PriceItemNotFoundError(
                    f"Price item {row.price_item_id} not found"
                )
            if (
                item.is_archived
                and requested_counts[item.id] > existing_counts[item.id]
            ):
                raise SurfaceWorkPlanValidationError(
                    f"Archived price item {row.price_item_id} cannot be selected "
                    "for a work plan"
                )
            if (
                item.category == PriceCategory.REVEAL
                and requested_counts[item.id] > existing_counts[item.id]
            ):
                raise SurfaceWorkPlanValidationError(
                    f"Price item {row.price_item_id}: reveal work belongs under an "
                    "opening (Prace na ościeżach), not on a surface work plan"
                )
            options = await coefficient_service.resolve_assignment_options(
                owner_id, item, row.coefficient_option_ids
            )
            validated.append(
                ResolvedOccurrence(
                    item=item,
                    options=options,
                    occurrence_key=row.occurrence_key,
                    wait_after_hours=row.wait_after_hours,
                )
            )
        return validated

    @staticmethod
    def _validate_occurrence_keys(
        plan: SurfaceWorkPlan | None,
        selection: list[OrderedPriceItemSelection],
    ) -> None:
        """Validate every echoed `occurrence_key` BEFORE any mutation (D13).

        - the same key twice in one payload -> validation error (two
          occurrences cannot share one logical identity);
        - a key that is not a CURRENT occurrence of this plan -> conflict. A
          stale draft's removed key, another plan's/owner's key and an
          invented key are deliberately indistinguishable, so nothing about
          other occurrences is disclosed and a removed key is never reused;
        - a known key with a different PriceItem -> validation error
          (changing the operation means remove + add).
        Omitted keys are new occurrences and need no validation.
        """
        keys = [row.occurrence_key for row in selection if row.occurrence_key is not None]
        if not keys:
            return
        duplicates = sorted(str(key) for key, n in Counter(keys).items() if n > 1)
        if duplicates:
            raise SurfaceWorkPlanValidationError(
                "occurrence_key used more than once in one work plan: "
                + ", ".join(duplicates)
            )
        current = (
            {work.occurrence_key: work.price_item_id for work in plan.planned_works}
            if plan is not None
            else {}
        )
        for row in selection:
            key = row.occurrence_key
            if key is None:
                continue
            if key not in current:
                raise SurfaceWorkPlanOccurrenceConflictError(
                    f"occurrence_key {key} is not a current occurrence of this "
                    "work plan; reload the plan and try again"
                )
            if current[key] != row.price_item_id:
                raise SurfaceWorkPlanValidationError(
                    f"occurrence_key {key} belongs to a different price item; "
                    "remove the occurrence and add a new one instead"
                )

    async def _resolve_template_applications(
        self,
        owner_id: uuid.UUID,
        plan: SurfaceWorkPlan | None,
        selection: list[OrderedPriceItemSelection],
        intents: list[TemplateApplicationIntent],
    ) -> list[SurfaceWorkPlanTemplateApplication]:
        """Validate template-application provenance intents BEFORE any
        mutation (Stage 13C) and return the history rows to record.

        - templates must belong to the owner (else not found, no disclosure);
        - snapshot code/name and applied_at come from the server, never the
          client;
        - `application_id` is the idempotency key and becomes the record id:
          an id already recorded for THIS plan with the same template, mode
          and count is a retry and is not recorded again; any other reuse is
          a conflict;
        - a REPLACE removes every previous occurrence, so the saved plan may
          not echo any existing occurrence_key alongside it;
        - the applied step counts cannot exceed the payload's new (key-less)
          occurrences -- materialised steps are always new occurrences.
        """
        if not intents:
            return []
        app_ids = [intent.application_id for intent in intents]
        if len(set(app_ids)) != len(app_ids):
            raise SurfaceWorkPlanValidationError(
                "application_id used more than once in one work plan save"
            )
        echoed = any(row.occurrence_key is not None for row in selection)
        if echoed and any(i.mode == TemplateApplicationMode.REPLACE for i in intents):
            raise SurfaceWorkPlanValidationError(
                "a REPLACE template application removes all previous occurrences; "
                "the saved plan cannot keep existing occurrence_keys"
            )
        new_occurrences = sum(1 for row in selection if row.occurrence_key is None)
        if sum(i.steps_applied for i in intents) > new_occurrences:
            raise SurfaceWorkPlanValidationError(
                "steps_applied exceeds the number of new occurrences in this save"
            )

        template_ids = {intent.template_id for intent in intents}
        templates = {
            t.id: t
            for t in (
                await self.db.execute(
                    select(WorkflowTemplate).where(
                        WorkflowTemplate.id.in_(template_ids),
                        WorkflowTemplate.owner_id == owner_id,
                    )
                )
            ).scalars().all()
        }
        missing = template_ids - templates.keys()
        if missing:
            raise WorkflowTemplateNotFoundError(
                f"Workflow template {sorted(str(m) for m in missing)[0]} not found"
            )

        existing = {
            row.id: row
            for row in (
                await self.db.execute(
                    select(SurfaceWorkPlanTemplateApplication).where(
                        SurfaceWorkPlanTemplateApplication.id.in_(app_ids)
                    )
                )
            ).scalars().all()
        }
        applied_at = datetime.now(timezone.utc)
        records: list[SurfaceWorkPlanTemplateApplication] = []
        for intent in intents:
            recorded = existing.get(intent.application_id)
            if recorded is not None:
                if (
                    plan is not None
                    and recorded.work_plan_id == plan.id
                    and recorded.template_id == intent.template_id
                    and recorded.mode == intent.mode
                    and recorded.steps_applied == intent.steps_applied
                ):
                    continue  # retry of an already-recorded application
                raise TemplateApplicationConflictError(
                    f"application_id {intent.application_id} cannot be recorded "
                    "for this save; generate a new one for a new application"
                )
            template = templates[intent.template_id]
            records.append(
                SurfaceWorkPlanTemplateApplication(
                    id=intent.application_id,
                    template_id=template.id,
                    template_code=template.code,
                    template_name=template.display_name or template.name_key or template.code,
                    mode=intent.mode,
                    steps_applied=intent.steps_applied,
                    applied_at=applied_at,
                )
            )
        return records

    async def _rewrite_works(
        self,
        plan: SurfaceWorkPlan,
        selection: list[ResolvedOccurrence],
    ) -> None:
        """Atomically replace the plan's works (and their coefficient
        assignments), appending position from 0.

        The old rows are deleted with an immediate statement: SQLAlchemy's unit
        of work inserts new rows before deleting cleared orphans, which would
        collide on the unique (work_plan_id, position). Deleting
        SurfacePlannedWork cascades to its own coefficient_assignments rows
        (ON DELETE CASCADE). `plan.planned_works` may already hold the old,
        eager-loaded work/assignment objects (e.g. from `_fetch_plan` in
        `set_plan`); resetting it via `set_committed_value` -- rather than
        `.clear()` -- forgets them without walking the delete-orphan cascade,
        so the ORM never re-issues a DELETE for rows the raw statement (and
        the DB's own cascade) already removed. The freshly-appended rows'
        assignments are created via the relationship, atomically, in the
        same commit.
        """
        if plan.id is not None:
            await self.db.execute(
                delete(SurfacePlannedWork).where(
                    SurfacePlannedWork.work_plan_id == plan.id
                )
            )
        attributes.set_committed_value(plan, "planned_works", [])
        for position, occurrence in enumerate(selection):
            work = SurfacePlannedWork(
                work_plan_id=plan.id,
                price_item_id=occurrence.item.id,
                position=position,
                # Preserved (already validated) or freshly server-generated;
                # safe under the global unique index because the old rows
                # were deleted above, in this same transaction.
                occurrence_key=occurrence.occurrence_key or uuid.uuid4(),
                wait_after_hours=occurrence.wait_after_hours,
            )
            for option in occurrence.options:
                work.coefficient_assignments.append(
                    SurfacePlannedWorkCoefficientAssignment(
                        coefficient_option_id=option.id
                    )
                )
            plan.planned_works.append(work)

    async def lock_plan(self, surface_id: uuid.UUID) -> SurfaceWorkPlan | None:
        """Acquire a row-level exclusive lock on the surface's plan, if any.

        Used by Stage 11 recommendation acceptance to serialize concurrent
        appends to the same plan before computing the next occurrence's
        position (see append_one_planned_work_no_commit). Mirrors the
        existing EstimateService._lock_project row-lock precedent. Returns
        None (never creates) when the surface has no plan yet -- callers
        must not invent one.
        """
        stmt = (
            select(SurfaceWorkPlan)
            .where(SurfaceWorkPlan.surface_id == surface_id)
            .with_for_update()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def append_one_planned_work_no_commit(
        self,
        plan: SurfaceWorkPlan,
        price_item: PriceItem,
    ) -> SurfacePlannedWork:
        """Append exactly one new occurrence, additive-only, never committing.

        The new occurrence gets a fresh occurrence_key and no technological
        break (Stage 13 D13/D9); nothing is taken from any template.
        Unlike set_plan/replace_planned_works/apply_to_room_walls, this never
        calls _rewrite_works: no existing row is deleted, renumbered, or
        otherwise touched, and substrate/quality_target are left exactly as
        they are. The caller MUST already hold plan's row lock (lock_plan
        above) before calling this, so the MAX(position) read below is safe
        under concurrent appends to the same plan. Duplicates are allowed by
        design (Stage 10 invariant) -- this never checks whether price_item
        already appears in the plan. The caller owns the transaction: this
        method only adds and flushes, it never commits.
        """
        if price_item.is_archived:
            raise SurfaceWorkPlanValidationError(
                f"Archived price item {price_item.id} cannot be selected "
                "for a work plan"
            )
        max_position = (
            await self.db.execute(
                select(func.max(SurfacePlannedWork.position)).where(
                    SurfacePlannedWork.work_plan_id == plan.id
                )
            )
        ).scalar_one()
        next_position = 0 if max_position is None else max_position + 1

        work = SurfacePlannedWork(
            work_plan_id=plan.id,
            price_item_id=price_item.id,
            position=next_position,
            occurrence_key=uuid.uuid4(),
        )
        self.db.add(work)
        await self.db.flush()
        return work

    async def _fetch_plan(self, surface_id: uuid.UUID) -> SurfaceWorkPlan | None:
        stmt = (
            select(SurfaceWorkPlan)
            .where(SurfaceWorkPlan.surface_id == surface_id)
            .options(
                selectinload(SurfaceWorkPlan.planned_works).selectinload(
                    SurfacePlannedWork.price_item
                ),
                # Eager-load the full coefficient chain so
                # SurfacePlannedWork.coefficient_options (a plain property)
                # never triggers an implicit lazy load during serialization
                # (async sessions disallow it) -- populate_existing forces a
                # fresh reload even for an already identity-mapped plan
                # (mirrors PriceCoefficientService's own precedent).
                selectinload(SurfaceWorkPlan.planned_works)
                .selectinload(SurfacePlannedWork.coefficient_assignments)
                .selectinload(SurfacePlannedWorkCoefficientAssignment.coefficient_option)
                .selectinload(CoefficientOption.group),
                selectinload(SurfaceWorkPlan.template_applications),
            )
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_work_plan(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> SurfaceWorkPlan | None:
        """Return the surface's plan (with ordered works) or None when unplanned."""
        await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)
        return await self._fetch_plan(surface_id)

    async def set_plan(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        substrate: Substrate,
        quality_target: QualityLevel | None = None,
        planned_works: list[OrderedPriceItemSelection] | None = None,
        template_applications: list[TemplateApplicationIntent] | None = None,
    ) -> SurfaceWorkPlan:
        """Create or fully replace the surface's plan in one atomic commit.

        Optional template-application intents (Stage 13C) are validated with
        everything else before any mutation and recorded in the same commit,
        so provenance exists only if the plan save itself succeeds.

        Setting a plan is an explicit owner action: the substrate and quality
        target are validated together (S/Q scale compatibility reuses the
        Stage 6 rule), the works replace any previous planning, and an
        incompatible current quality target on a substrate change must be
        cleared explicitly rather than silently converted.
        """
        await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)
        assert_quality_scale_valid(substrate, quality_target)

        selection = planned_works or []
        plan = await self._fetch_plan(surface_id)
        existing_counts = (
            Counter(work.price_item_id for work in plan.planned_works)
            if plan is not None
            else Counter()
        )
        validated = await self._resolve_owned_items(
            owner_id, selection, existing_counts
        )
        self._validate_occurrence_keys(plan, selection)
        applications = await self._resolve_template_applications(
            owner_id, plan, selection, template_applications or []
        )

        if plan is None:
            plan = SurfaceWorkPlan(
                surface_id=surface_id,
                substrate=substrate,
                quality_target=quality_target,
            )
            self.db.add(plan)
        else:
            plan.substrate = substrate
            plan.quality_target = quality_target
        await self._rewrite_works(plan, validated)
        for record in applications:
            record.work_plan = plan
            self.db.add(record)
        await self.db.commit()
        return await self._fetch_plan(surface_id)

    async def replace_planned_works(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        planned_works: list[OrderedPriceItemSelection],
    ) -> SurfaceWorkPlan:
        """Replace only the works of an existing plan (substrate/quality kept).

        Nothing changes when the plan does not exist yet — the caller must
        establish the plan configuration first, then order its works.
        """
        await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)
        plan = await self._fetch_plan(surface_id)
        if plan is None:
            raise SurfaceWorkPlanNotFoundError(
                f"Surface {surface_id} has no work plan yet"
            )

        existing_counts = Counter(
            work.price_item_id for work in plan.planned_works
        )
        validated = await self._resolve_owned_items(
            owner_id, planned_works, existing_counts
        )
        self._validate_occurrence_keys(plan, planned_works)
        await self._rewrite_works(plan, validated)
        await self.db.commit()
        return await self._fetch_plan(surface_id)

    async def apply_template(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
        request: ApplyTemplateRequest,
    ) -> SurfaceWorkPlan:
        """Materialize a workflow template into the CURRENT plan (13E.3).

        One transaction under the plan row lock (SELECT ... FOR UPDATE, taken
        before the application_id is examined, so concurrent identical
        requests serialize and the later one sees the committed record).
        Every materialized PriceItem, order and break comes from the server
        template; the client only sends identifiers and choices. Validation
        is complete before any mutation, so a rejected request changes
        nothing. Never touches an Estimate.

        APPEND adds the selected steps after the current occurrences without
        rewriting them. REPLACE removes every current occurrence (their
        coefficient assignments cascade) and materializes the selected steps
        at positions 0..N-1; old occurrence keys are never reused.
        """
        surface = await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)
        plan = await self.lock_plan(surface_id)
        if plan is None:
            raise SurfaceWorkPlanNotFoundError(f"Surface {surface_id} has no work plan yet")

        fingerprint = _application_fingerprint(plan.id, request)
        recorded = (
            await self.db.execute(
                select(SurfaceWorkPlanTemplateApplication).where(
                    SurfaceWorkPlanTemplateApplication.id == request.application_id
                )
            )
        ).scalar_one_or_none()
        if recorded is not None:
            if recorded.work_plan_id == plan.id and recorded.request_fingerprint == fingerprint:
                await self.db.commit()  # release the lock; nothing to apply
                return await self._fetch_plan(surface_id)
            raise TemplateApplicationConflictError(
                f"application_id {request.application_id} was already used for a "
                "different application; generate a new one"
            )

        template = (
            await self.db.execute(
                select(WorkflowTemplate)
                .where(
                    WorkflowTemplate.id == request.template_id,
                    WorkflowTemplate.owner_id == owner_id,
                )
                .options(
                    selectinload(WorkflowTemplate.steps).selectinload(
                        WorkflowTemplateStep.price_item
                    )
                )
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if template is None:
            raise WorkflowTemplateNotFoundError(
                f"Workflow template {request.template_id} not found"
            )
        if template.is_archived:
            raise TemplateApplicationStaleError(
                "the workflow template is archived; restore it before applying"
            )
        if plan.quality_target is None:
            raise SurfaceWorkPlanValidationError(
                "set the work plan's quality target before applying a technology"
            )
        if not (
            _filter_allows(template.applies_to_substrates, plan.substrate.value)
            and _filter_allows(template.applies_to_quality, plan.quality_target.value)
            and _filter_allows(template.applies_to_surface_types, surface.surface_type.value)
        ):
            raise SurfaceWorkPlanValidationError(
                "the workflow template does not match this surface's substrate, "
                "quality target or surface type"
            )

        steps = list(template.steps)
        if [step.id for step in steps] != list(request.expected_step_ids):
            raise TemplateApplicationStaleError(
                "the workflow template changed since it was previewed; refresh the preview"
            )
        optional_ids = {step.id for step in steps if step.is_optional}
        selected = list(request.selected_optional_step_ids)
        if len(set(selected)) != len(selected):
            raise SurfaceWorkPlanValidationError("an optional step was selected more than once")
        invalid = [i for i in selected if i not in optional_ids]
        if invalid:
            raise SurfaceWorkPlanValidationError(
                f"step {invalid[0]} is not an optional step of this template"
            )
        chosen = [s for s in steps if not s.is_optional or s.id in set(selected)]
        if not chosen:
            raise SurfaceWorkPlanValidationError(
                "no steps selected: at least one work must be applied"
            )
        for step in chosen:
            item = step.price_item
            if item is None or item.owner_id != owner_id:
                raise PriceItemNotFoundError(f"Price item {step.price_item_id} not found")
            if item.category == PriceCategory.REVEAL:
                raise SurfaceWorkPlanValidationError(
                    f"Price item {item.id}: reveal work belongs under an opening, "
                    "not on a surface work plan"
                )
            if item.is_archived:
                kind = "optional" if step.is_optional else "required"
                raise SurfaceWorkPlanValidationError(
                    f"the {kind} step's price item {item.id} is archived; restore it "
                    "in the Price Book to apply this technology"
                )

        current = (
            await self.db.execute(
                select(SurfacePlannedWork)
                .where(SurfacePlannedWork.work_plan_id == plan.id)
                .order_by(SurfacePlannedWork.position)
            )
        ).scalars().all()
        if request.mode == TemplateApplicationMode.REPLACE:
            if not request.replace_confirmed:
                raise SurfaceWorkPlanValidationError("REPLACE requires explicit confirmation")
            if request.expected_occurrence_keys is None:
                raise SurfaceWorkPlanValidationError(
                    "REPLACE requires expected_occurrence_keys (the confirmed plan composition)"
                )
            if [w.occurrence_key for w in current] != list(request.expected_occurrence_keys):
                raise TemplateApplicationStaleError(
                    "the work plan changed since it was confirmed for replacement; reload it"
                )
            await self._rewrite_works(
                plan,
                [
                    ResolvedOccurrence(
                        item=step.price_item,
                        options=[],
                        occurrence_key=None,
                        wait_after_hours=step.wait_after_hours,
                    )
                    for step in chosen
                ],
            )
        else:
            next_position = (max((w.position for w in current), default=-1)) + 1
            for offset, step in enumerate(chosen):
                self.db.add(
                    SurfacePlannedWork(
                        work_plan_id=plan.id,
                        price_item_id=step.price_item_id,
                        position=next_position + offset,
                        occurrence_key=uuid.uuid4(),
                        wait_after_hours=step.wait_after_hours,
                    )
                )

        self.db.add(
            SurfaceWorkPlanTemplateApplication(
                id=request.application_id,
                work_plan_id=plan.id,
                template_id=template.id,
                template_code=template.code,
                template_name=template.display_name or template.name_key or template.code,
                mode=request.mode,
                steps_applied=len(chosen),
                applied_at=datetime.now(timezone.utc),
                request_fingerprint=fingerprint,
            )
        )
        await self.db.commit()
        return await self._fetch_plan(surface_id)

    async def apply_to_room_walls(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        source_surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[SurfaceWorkPlan]:
        """Atomically copy a source wall's planning configuration to every
        other active WALL surface in the same room (Stage 10B.2 / 12D).

        Only planning configuration is copied: substrate, quality target, the
        ordered planned works, AND each occurrence's coefficient selection
        (Stage 12 architecture Sec 15 -- a coefficient is part of the
        occurrence's own pricing configuration, so it travels with it exactly
        like the PriceItem reference does). Geometry, openings/deductions,
        inspections, findings, risks, photos, archive state, and every Price
        Book/coefficient catalog row are never touched. Each target receives
        its own persisted plan rows, so the walls stay independent
        afterwards. Each copied occurrence is a distinct occurrence with its
        own NEW occurrence_key (the source key is never copied); its
        technological break (wait_after_hours) is plan configuration and is
        copied like the coefficient selection (Stage 13 D13/D9). The whole
        batch commits together or not at all — every source-side validation
        runs before any mutation, so a failed apply cannot leave half the
        room updated.
        """
        source = await self._ensure_surface_owned(
            project_id, room_id, source_surface_id, owner_id
        )
        if source.surface_type != SurfaceType.WALL:
            raise SurfaceWorkPlanValidationError(
                "apply-to-room-walls requires a WALL source surface"
            )
        if source.is_archived:
            raise SurfaceWorkPlanValidationError(
                "an archived surface cannot start apply-to-room-walls"
            )
        source_plan = await self._fetch_plan(source.id)
        if source_plan is None:
            raise SurfaceWorkPlanNotFoundError(
                f"Surface {source.id} has no work plan to apply"
            )

        # New target rows must never silently reference an archived catalog
        # item; NULL commercial prices are fine (planning is independent of
        # commercial completeness). The source plan itself is never mutated.
        # An archived coefficient option/group is rejected the same way an
        # archived PriceItem already is -- copying stale configuration into
        # fresh target rows would be surprising; the owner must resolve the
        # source occurrence first.
        validated_items: list[ResolvedOccurrence] = []
        for work in source_plan.planned_works:
            item = work.price_item
            if item is None or item.is_archived:
                raise SurfaceWorkPlanValidationError(
                    f"Source plan references an archived price item "
                    f"{work.price_item_id}; update the source plan first"
                )
            if item.category == PriceCategory.REVEAL:
                # Copying would create new surface-level reveal occurrences.
                raise SurfaceWorkPlanValidationError(
                    f"Source plan contains price item {work.price_item_id}: "
                    "reveal work belongs under an opening; remove it from the "
                    "source plan first"
                )
            options = work.coefficient_options
            for option in options:
                if option.is_archived or option.group.is_archived:
                    raise SurfaceWorkPlanValidationError(
                        f"Source plan references an archived coefficient "
                        f"option {option.id}; update the source plan first"
                    )
            validated_items.append(
                ResolvedOccurrence(
                    item=item,
                    options=options,
                    occurrence_key=None,
                    wait_after_hours=work.wait_after_hours,
                )
            )

        targets = (
            await self.db.execute(
                select(Surface)
                .where(
                    Surface.room_id == source.room_id,
                    Surface.surface_type == SurfaceType.WALL,
                    Surface.id != source.id,
                    Surface.is_archived.is_(False),
                )
                .order_by(Surface.position.nulls_last(), Surface.id)
            )
        ).scalars().all()

        target_plans: list[SurfaceWorkPlan] = []
        for target in targets:
            target_plan = await self._fetch_plan(target.id)
            if target_plan is None:
                target_plan = SurfaceWorkPlan(
                    surface_id=target.id,
                    substrate=source_plan.substrate,
                    quality_target=source_plan.quality_target,
                )
                self.db.add(target_plan)
            else:
                target_plan.substrate = source_plan.substrate
                target_plan.quality_target = source_plan.quality_target
            await self._rewrite_works(target_plan, validated_items)
            target_plans.append(target_plan)

        await self.db.commit()
        return [await self._fetch_plan(p.surface_id) for p in target_plans]