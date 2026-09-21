"""Recommendation materialization + lifecycle (Stage 11B.1 + 11B.2).

`evaluate_recommendations` reconciles a whole room's currently active
`Risk`/`InspectionFinding` state against the `WorkRecommendationRule` catalog,
exactly mirroring `RiskService._reconcile_risks`'s materialize-once /
reconcile-by-identity / resolve-never-delete idiom, extended with the
multi-work-per-trigger and sticky-lifecycle rules in
docs/stage-11-architecture.md. `dismiss`/`reconsider` are explicit owner
commands. Nothing in this module ever mutates a `SurfaceWorkPlan`,
`OpeningRevealPlannedWork`, or `Estimate` -- acceptance is Stage 11C.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.work_recommendation_rules import (
    build_baseline_work_recommendation_rules,
)
from app.domain.exceptions import (
    PriceItemNotFoundError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceWorkPlanNotFoundError,
    SurfaceWorkPlanValidationError,
    WorkRecommendationNotFoundError,
    WorkRecommendationStateError,
    WorkRecommendationTargetError,
)
from app.domain.rules.risk_rules import compute_source_signature, derive_target_type
from app.domain.services.canonical_planes import find_active_plane_surface
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.area_segment import AreaPlane
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from app.models.price_item import PriceCategory, PriceItem
from app.models.project import Project
from app.models.risk import Risk
from app.models.room import Room
from app.models.surface import SurfaceType
from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationRule,
    WorkRecommendationStatus,
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)

Identity = tuple[uuid.UUID, WorkRecommendationTriggerType, str, str, str]

# Serializes concurrent first-call bootstraps within the process; the
# (trigger_type, trigger_code, recommended_work_code) unique constraint
# guarantees correctness even without it -- mirrors RiskService's own
# _bootstrap_lock precedent.
_bootstrap_lock = asyncio.Lock()


@dataclass
class _Desired:
    inspection_id: uuid.UUID
    trigger_type: WorkRecommendationTriggerType
    trigger_code: str
    source_signature: str
    recommended_work_code: str
    rule_id: uuid.UUID
    room_id: uuid.UUID
    surface_id: uuid.UUID | None
    target_kind: WorkRecommendationTargetKind
    risk_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None

    @property
    def identity(self) -> Identity:
        return (
            self.inspection_id,
            self.trigger_type,
            self.trigger_code,
            self.source_signature,
            self.recommended_work_code,
        )


@dataclass
class RecommendationEvaluation:
    created: int = 0
    reactivated: int = 0
    unchanged: int = 0
    resolved: int = 0
    recommendations: list[WorkRecommendation] = field(default_factory=list)


class WorkRecommendationService:
    """Persistence-level operations over `WorkRecommendation`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- Ownership -----------------------------------------------------------

    async def _ensure_room_owned(
        self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID
    ) -> None:
        project = (
            await self.db.execute(
                select(Project.id).where(
                    Project.id == project_id, Project.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        room = (
            await self.db.execute(
                select(Room.id).where(
                    Room.id == room_id, Room.project_id == project_id
                )
            )
        ).scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError(f"Room {room_id} not found")

    async def _get_owned_recommendation(
        self, project_id: uuid.UUID, recommendation_id: uuid.UUID, owner_id: uuid.UUID
    ) -> WorkRecommendation:
        """Resolve a recommendation strictly through the owner's own resource
        graph -- project_id + owner_id, never a bare recommendation_id.
        """
        stmt = (
            select(WorkRecommendation)
            .join(Room, WorkRecommendation.room_id == Room.id)
            .join(Project, Room.project_id == Project.id)
            .where(
                WorkRecommendation.id == recommendation_id,
                Room.project_id == project_id,
                Project.owner_id == owner_id,
            )
        )
        recommendation = (await self.db.execute(stmt)).scalar_one_or_none()
        if recommendation is None:
            raise WorkRecommendationNotFoundError(
                f"WorkRecommendation {recommendation_id} not found"
            )
        return recommendation

    async def _get_owned_recommendation_for_update(
        self, project_id: uuid.UUID, recommendation_id: uuid.UUID, owner_id: uuid.UUID
    ) -> WorkRecommendation:
        """Same ownership resolution as `_get_owned_recommendation`, but
        acquires a PostgreSQL row lock (`SELECT ... FOR UPDATE OF
        work_recommendations`) on the recommendation itself -- never on the
        joined Room/Project rows -- so two simultaneous accept requests for
        the SAME recommendation cannot both observe PENDING and append
        twice. Mirrors the existing EstimateService._lock_project precedent.
        """
        stmt = (
            select(WorkRecommendation)
            .join(Room, WorkRecommendation.room_id == Room.id)
            .join(Project, Room.project_id == Project.id)
            .where(
                WorkRecommendation.id == recommendation_id,
                Room.project_id == project_id,
                Project.owner_id == owner_id,
            )
            .with_for_update(of=WorkRecommendation)
        )
        recommendation = (await self.db.execute(stmt)).scalar_one_or_none()
        if recommendation is None:
            raise WorkRecommendationNotFoundError(
                f"WorkRecommendation {recommendation_id} not found"
            )
        return recommendation

    # -- Baseline catalog bootstrap (Stage 11B.1.1) -----------------------------

    async def _ensure_bootstrapped(self) -> None:
        """Materialize every missing baseline `WorkRecommendationRule` row
        exactly once. Mirrors `RiskService._ensure_bootstrapped` verbatim:
        lazy, idempotent, no Alembic data migration, no manual seed step --
        the owner's currently running application picks it up automatically
        the next time recommendations are listed or evaluated.
        """
        async with _bootstrap_lock:
            existing_rows = (
                await self.db.execute(
                    select(
                        WorkRecommendationRule.trigger_type,
                        WorkRecommendationRule.trigger_code,
                        WorkRecommendationRule.recommended_work_code,
                    )
                )
            ).all()
            existing = {
                (row.trigger_type, row.trigger_code, row.recommended_work_code)
                for row in existing_rows
            }
            missing = [
                data
                for data in build_baseline_work_recommendation_rules()
                if (data.trigger_type, data.trigger_code, data.recommended_work_code)
                not in existing
            ]
            if not missing:
                return

            for data in missing:
                self.db.add(
                    WorkRecommendationRule(
                        trigger_type=data.trigger_type,
                        trigger_code=data.trigger_code,
                        recommended_work_code=data.recommended_work_code,
                        active=True,
                    )
                )
            await self.db.commit()

    # -- Identity lookup (Stage 11B.1) ----------------------------------------

    async def get_by_identity(
        self,
        inspection_id: uuid.UUID,
        trigger_type: WorkRecommendationTriggerType,
        trigger_code: str,
        source_signature: str,
        recommended_work_code: str,
    ) -> WorkRecommendation | None:
        """Fetch a recommendation by its deterministic identity.

        Full identity: `(inspection_id, trigger_type, trigger_code,
        source_signature, recommended_work_code)`.
        """
        stmt = select(WorkRecommendation).where(
            WorkRecommendation.inspection_id == inspection_id,
            WorkRecommendation.trigger_type == trigger_type,
            WorkRecommendation.trigger_code == trigger_code,
            WorkRecommendation.source_signature == source_signature,
            WorkRecommendation.recommended_work_code == recommended_work_code,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def materialize_one(
        self,
        *,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        surface_id: uuid.UUID | None,
        target_kind: WorkRecommendationTargetKind,
        rule: WorkRecommendationRule,
        source_signature: str,
        risk_id: uuid.UUID | None = None,
        finding_id: uuid.UUID | None = None,
    ) -> WorkRecommendation:
        """Create, or reuse by identity, exactly one recommendation row.

        Kept for Stage 11B.1 focused-test compatibility; `evaluate_recommendations`
        below is the real room-wide reconciliation entry point.
        """
        existing = await self.get_by_identity(
            inspection_id,
            rule.trigger_type,
            rule.trigger_code,
            source_signature,
            rule.recommended_work_code,
        )
        if existing is not None:
            existing.is_active = True
            existing.resolved_at = None
            await self.db.flush()
            return existing

        recommendation = WorkRecommendation(
            trigger_type=rule.trigger_type,
            trigger_code=rule.trigger_code,
            source_signature=source_signature,
            inspection_id=inspection_id,
            rule_id=rule.id,
            risk_id=risk_id,
            finding_id=finding_id,
            room_id=room_id,
            surface_id=surface_id,
            target_kind=target_kind,
            recommended_work_code=rule.recommended_work_code,
        )
        self.db.add(recommendation)
        await self.db.flush()
        return recommendation

    # -- Target derivation -----------------------------------------------------

    async def _derive_target(
        self, inspection: Inspection
    ) -> tuple[WorkRecommendationTargetKind, uuid.UUID | None] | None:
        """Map an inspection's own target to a recommendation target.

        Returns None (skip -- fail safe, never fabricate) if a FLOOR/CEILING
        inspection's canonical Surface is structurally missing, which should
        not happen since Stage 10C.1A provisions it at room creation.
        """
        target_type = derive_target_type(
            surface_id=inspection.surface_id, plane=inspection.plane
        )
        if target_type == "WALL":
            return WorkRecommendationTargetKind.WALL, inspection.surface_id
        if target_type == "ROOM":
            return WorkRecommendationTargetKind.ROOM, None

        surface_type = (
            SurfaceType.FLOOR if inspection.plane is AreaPlane.FLOOR else SurfaceType.CEILING
        )
        canonical = await find_active_plane_surface(
            self.db, inspection.room_id, surface_type
        )
        if canonical is None:
            return None
        target_kind = (
            WorkRecommendationTargetKind.FLOOR
            if surface_type is SurfaceType.FLOOR
            else WorkRecommendationTargetKind.CEILING
        )
        return target_kind, canonical.id

    # -- Room-wide reconciliation (Stage 11B.2) ---------------------------------

    async def evaluate_recommendations(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> RecommendationEvaluation:
        """Explicit, deterministic, idempotent room-wide reconciliation.

        Never mutates a SurfaceWorkPlan/OpeningRevealPlannedWork/Estimate.
        """
        await self._ensure_room_owned(project_id, room_id, owner_id)
        await self._ensure_bootstrapped()

        active_rules = list(
            (
                await self.db.execute(
                    select(WorkRecommendationRule).where(
                        WorkRecommendationRule.active.is_(True)
                    )
                )
            ).scalars().all()
        )
        rules_by_trigger: dict[tuple[WorkRecommendationTriggerType, str], list[WorkRecommendationRule]] = {}
        for rule in active_rules:
            rules_by_trigger.setdefault(
                (rule.trigger_type, rule.trigger_code), []
            ).append(rule)

        active_risks = list(
            (
                await self.db.execute(
                    select(Risk).where(
                        Risk.room_id == room_id, Risk.is_active.is_(True)
                    )
                )
            ).scalars().all()
        )
        active_findings = list(
            (
                await self.db.execute(
                    select(InspectionFinding)
                    .join(Inspection, InspectionFinding.inspection_id == Inspection.id)
                    .where(
                        Inspection.room_id == room_id,
                        Inspection.status == InspectionStatus.COMPLETED,
                        InspectionFinding.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )

        inspection_ids = {risk.inspection_id for risk in active_risks} | {
            finding.inspection_id for finding in active_findings
        }
        inspections_by_id: dict[uuid.UUID, Inspection] = {}
        if inspection_ids:
            inspections_by_id = {
                inspection.id: inspection
                for inspection in (
                    await self.db.execute(
                        select(Inspection).where(Inspection.id.in_(inspection_ids))
                    )
                ).scalars().all()
            }

        desired_by_identity: dict[Identity, _Desired] = {}

        for risk in active_risks:
            inspection = inspections_by_id.get(risk.inspection_id)
            if inspection is None:
                continue
            target = await self._derive_target(inspection)
            if target is None:
                continue
            target_kind, surface_id = target
            for rule in rules_by_trigger.get(
                (WorkRecommendationTriggerType.RISK_RULE, risk.rule_code), []
            ):
                desired = _Desired(
                    inspection_id=inspection.id,
                    trigger_type=WorkRecommendationTriggerType.RISK_RULE,
                    trigger_code=risk.rule_code,
                    source_signature=risk.source_signature,
                    recommended_work_code=rule.recommended_work_code,
                    rule_id=rule.id,
                    room_id=room_id,
                    surface_id=surface_id,
                    target_kind=target_kind,
                    risk_id=risk.id,
                )
                desired_by_identity[desired.identity] = desired

        for finding in active_findings:
            inspection = inspections_by_id.get(finding.inspection_id)
            if inspection is None:
                continue
            target = await self._derive_target(inspection)
            if target is None:
                continue
            target_kind, surface_id = target
            signature = compute_source_signature([finding.id])
            for rule in rules_by_trigger.get(
                (WorkRecommendationTriggerType.FINDING, finding.finding_key), []
            ):
                desired = _Desired(
                    inspection_id=inspection.id,
                    trigger_type=WorkRecommendationTriggerType.FINDING,
                    trigger_code=finding.finding_key,
                    source_signature=signature,
                    recommended_work_code=rule.recommended_work_code,
                    rule_id=rule.id,
                    room_id=room_id,
                    surface_id=surface_id,
                    target_kind=target_kind,
                    finding_id=finding.id,
                )
                desired_by_identity[desired.identity] = desired

        existing_rows = list(
            (
                await self.db.execute(
                    select(WorkRecommendation).where(
                        WorkRecommendation.room_id == room_id
                    )
                )
            ).scalars().all()
        )
        existing_by_identity: dict[Identity, WorkRecommendation] = {
            (
                row.inspection_id,
                row.trigger_type,
                row.trigger_code,
                row.source_signature,
                row.recommended_work_code,
            ): row
            for row in existing_rows
        }

        result = RecommendationEvaluation()
        now = datetime.now(timezone.utc)

        for identity, desired in desired_by_identity.items():
            existing = existing_by_identity.get(identity)
            if existing is None:
                row = WorkRecommendation(
                    trigger_type=desired.trigger_type,
                    trigger_code=desired.trigger_code,
                    source_signature=desired.source_signature,
                    inspection_id=desired.inspection_id,
                    rule_id=desired.rule_id,
                    risk_id=desired.risk_id,
                    finding_id=desired.finding_id,
                    room_id=desired.room_id,
                    surface_id=desired.surface_id,
                    target_kind=desired.target_kind,
                    recommended_work_code=desired.recommended_work_code,
                )
                self.db.add(row)
                await self.db.flush()
                result.created += 1
            elif not existing.is_active:
                # Reactivate only -- lifecycle status (PENDING/ACCEPTED/
                # DISMISSED) is an owner decision and is never touched here.
                existing.is_active = True
                existing.resolved_at = None
                result.reactivated += 1
            else:
                # Genuinely unchanged: do not touch any field, so no UPDATE
                # is emitted and updated_at is not gratuitously bumped.
                result.unchanged += 1

        for identity, row in existing_by_identity.items():
            if identity not in desired_by_identity and row.is_active:
                row.is_active = False
                row.resolved_at = now
                result.resolved += 1

        await self.db.commit()

        result.recommendations = await self._list_active(room_id)
        return result

    async def _list_active(self, room_id: uuid.UUID) -> list[WorkRecommendation]:
        stmt = (
            select(WorkRecommendation)
            .where(
                WorkRecommendation.room_id == room_id,
                WorkRecommendation.is_active.is_(True),
            )
            .order_by(WorkRecommendation.created_at.asc(), WorkRecommendation.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # -- List (Stage 11B.2) ------------------------------------------------------

    async def list_recommendations(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        activity: str = "active",
    ) -> tuple[list[WorkRecommendation], int]:
        """List a room's recommendations. Never materializes or mutates."""
        await self._ensure_room_owned(project_id, room_id, owner_id)
        await self._ensure_bootstrapped()

        stmt = select(WorkRecommendation).where(WorkRecommendation.room_id == room_id)
        if activity == "resolved":
            stmt = stmt.where(WorkRecommendation.is_active.is_(False))
        elif activity == "active":
            stmt = stmt.where(WorkRecommendation.is_active.is_(True))

        items = list(
            (
                await self.db.execute(
                    stmt.order_by(
                        WorkRecommendation.created_at.asc(),
                        WorkRecommendation.id.asc(),
                    )
                )
            ).scalars().all()
        )
        return items, len(items)

    async def get_price_item_by_id(
        self, owner_id: uuid.UUID, price_item_id: uuid.UUID
    ) -> PriceItem | None:
        """Owner-scoped lookup by id -- used only to render the accept
        response's snapshot preview (resolved_price_item_id), never to
        resolve a recommendation's semantic code (see
        resolve_current_price_items for that).
        """
        return (
            await self.db.execute(
                select(PriceItem).where(
                    PriceItem.id == price_item_id, PriceItem.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()

    async def resolve_current_price_items(
        self, owner_id: uuid.UUID, recommendations: list[WorkRecommendation]
    ) -> dict[str, PriceItem]:
        """Read-time-only PriceBook resolution preview, keyed by code.

        Never writes resolved_price_item_id -- that stays the Stage 11C
        acceptance snapshot. Never reads market/reference prices.
        """
        codes = {rec.recommended_work_code for rec in recommendations}
        if not codes:
            return {}
        items = (
            await self.db.execute(
                select(PriceItem).where(
                    PriceItem.owner_id == owner_id, PriceItem.code.in_(codes)
                )
            )
        ).scalars().all()
        return {item.code: item for item in items}

    # -- Dismiss / reconsider (Stage 11B.2) --------------------------------------

    async def dismiss(
        self, project_id: uuid.UUID, recommendation_id: uuid.UUID, owner_id: uuid.UUID
    ) -> WorkRecommendation:
        """PENDING -> DISMISSED. Idempotent if already DISMISSED. Rejects ACCEPTED."""
        recommendation = await self._get_owned_recommendation(
            project_id, recommendation_id, owner_id
        )
        if recommendation.status is WorkRecommendationStatus.DISMISSED:
            return recommendation
        if recommendation.status is WorkRecommendationStatus.ACCEPTED:
            raise WorkRecommendationStateError(
                "Cannot dismiss an already-accepted recommendation"
            )
        recommendation.status = WorkRecommendationStatus.DISMISSED
        recommendation.dismissed_at = datetime.now(timezone.utc)
        await self.db.commit()
        return recommendation

    async def reconsider(
        self, project_id: uuid.UUID, recommendation_id: uuid.UUID, owner_id: uuid.UUID
    ) -> WorkRecommendation:
        """DISMISSED -> PENDING. Idempotent if already PENDING. Rejects ACCEPTED.

        Only evaluation can reactivate is_active based on real current source
        evidence -- reconsider never fabricates is_active=True.
        """
        recommendation = await self._get_owned_recommendation(
            project_id, recommendation_id, owner_id
        )
        if recommendation.status is WorkRecommendationStatus.PENDING:
            return recommendation
        if recommendation.status is WorkRecommendationStatus.ACCEPTED:
            raise WorkRecommendationStateError(
                "Cannot reconsider an already-accepted recommendation"
            )
        recommendation.status = WorkRecommendationStatus.PENDING
        recommendation.dismissed_at = None
        await self.db.commit()
        return recommendation

    # -- Accept (Stage 11C.1) -----------------------------------------------------

    async def _resolve_accept_price_item(
        self,
        owner_id: uuid.UUID,
        recommendation: WorkRecommendation,
        explicit_price_item_id: uuid.UUID | None,
    ) -> PriceItem:
        """Resolve the PriceItem to append, fresh, at accept time.

        No explicit id -> semantic resolution by (owner_id, recommended_
        work_code). Explicit id -> owner-validated manual override/fallback,
        which may legitimately have a different code than
        recommended_work_code (recommended_work_code is never overwritten).
        Never reads market/reference price; never substitutes another
        owner's item.
        """
        if explicit_price_item_id is not None:
            item = (
                await self.db.execute(
                    select(PriceItem).where(
                        PriceItem.id == explicit_price_item_id,
                        PriceItem.owner_id == owner_id,
                    )
                )
            ).scalar_one_or_none()
            if item is None:
                raise PriceItemNotFoundError(
                    f"Price item {explicit_price_item_id} not found"
                )
        else:
            item = (
                await self.db.execute(
                    select(PriceItem).where(
                        PriceItem.owner_id == owner_id,
                        PriceItem.code == recommendation.recommended_work_code,
                    )
                )
            ).scalar_one_or_none()
            if item is None:
                raise PriceItemNotFoundError(
                    "No price item with code "
                    f"{recommendation.recommended_work_code!r} found for the "
                    "current owner"
                )

        # Stage-11-only guard: not a Stage 10 SurfaceWorkPlan invariant, and
        # must never affect the existing manual Work Plan picker (which
        # deliberately has no category restriction). Opening/reveal
        # recommendation acceptance is explicitly deferred (D1), so a REVEAL
        # item can never be a valid Surface-recommendation resolution.
        if item.category == PriceCategory.REVEAL:
            raise SurfaceWorkPlanValidationError(
                f"Price item {item.id} is a REVEAL-category item; Stage 11 "
                "surface recommendation acceptance does not support REVEAL "
                "items"
            )
        return item

    async def accept_recommendation(
        self,
        project_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        price_item_id: uuid.UUID | None = None,
    ) -> WorkRecommendation:
        """Explicit, atomic acceptance.

        append exactly one SurfacePlannedWork occurrence + recommendation
        PENDING -> ACCEPTED + resolved_price_item_id + accepted_at, all in
        ONE commit. Never mutates Estimate/EstimateLine, never auto-creates
        a SurfaceWorkPlan, never reactivates is_active (only evaluation
        does that), and never renumbers or deletes existing planned works.

        Lock ordering is deterministic and must never be inverted:
        1. WorkRecommendation row (same-recommendation idempotency)
        2. SurfaceWorkPlan row (same-plan position-assignment safety)
        """
        recommendation = await self._get_owned_recommendation_for_update(
            project_id, recommendation_id, owner_id
        )

        if recommendation.status == WorkRecommendationStatus.ACCEPTED:
            # Idempotent: the original acceptance snapshot wins, untouched,
            # even if this retry supplies a different manual price_item_id.
            return recommendation
        if recommendation.status == WorkRecommendationStatus.DISMISSED:
            raise WorkRecommendationStateError(
                "Cannot accept a dismissed recommendation; reconsider it first"
            )

        if (
            recommendation.target_kind == WorkRecommendationTargetKind.ROOM
            or recommendation.surface_id is None
        ):
            raise WorkRecommendationTargetError(
                "ROOM-level recommendations are advisory-only and cannot be "
                "accepted directly into a Surface work plan"
            )

        work_plan_service = SurfaceWorkPlanService(self.db)
        plan = await work_plan_service.lock_plan(recommendation.surface_id)
        if plan is None:
            raise SurfaceWorkPlanNotFoundError(
                f"Surface {recommendation.surface_id} has no work plan yet"
            )

        selected_item = await self._resolve_accept_price_item(
            owner_id, recommendation, price_item_id
        )

        # PENDING, active or inactive/resolved, is accepted as-is (settled
        # in docs/stage-11-architecture.md Sec 6) -- acceptance never
        # touches is_active/resolved_at; only evaluation does.
        await work_plan_service.append_one_planned_work_no_commit(
            plan, selected_item
        )

        recommendation.status = WorkRecommendationStatus.ACCEPTED
        recommendation.resolved_price_item_id = selected_item.id
        recommendation.accepted_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(recommendation)
        return recommendation
