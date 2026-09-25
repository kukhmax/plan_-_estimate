"""Workflow template domain service (Stage 13B).

Owner-scoped persistence rules for technological workflow templates
(`docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md` §4, §8, §9, §14).
A template is a recipe, never project state: nothing here touches a
SurfaceWorkPlan, an occurrence, a coefficient or an Estimate. Applying a
template (13E), its API (13C) and default recipes (13D) are later sub-stages.

Rules enforced here:
- every step references an owned PriceItem directly (atomic or bundled);
- REVEAL PriceItems are never valid surface template steps (reveal work is
  planned per opening, D11);
- an archived PriceItem cannot be newly added to a template, but a step
  already referencing it may be kept (its count cannot increase), mirroring
  the WorkPlan rule;
- `wait_after_hours` is NULL (no break) or a whole number of hours >= 1;
- steps are replaced as a whole; positions are renumbered from 0;
- templates are soft-archived / restored, never hard-deleted here.
"""
import uuid
from collections import Counter
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.exceptions import (
    PriceItemNotFoundError,
    WorkflowTemplateNotFoundError,
    WorkflowTemplateValidationError,
)
from app.models.checklist import QualityLevel, Substrate
from app.models.price_item import PriceCategory, PriceItem
from app.models.surface import SurfaceType
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateStep

_UNSET = object()


@dataclass(frozen=True)
class WorkflowTemplateStepSpec:
    """One requested template step, in order (list order = position)."""

    price_item_id: uuid.UUID
    is_optional: bool = False
    note: str | None = None
    wait_after_hours: int | None = None


def _normalize_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _filter_values(values: list[Enum] | None) -> list[str] | None:
    """Store an applicability filter as a de-duplicated list of enum values;
    None or empty means "any"."""
    if not values:
        return None
    return list(dict.fromkeys(v.value for v in values))


def validate_wait_after_hours(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkflowTemplateValidationError(
            "wait_after_hours must be empty (no break) or a whole number of hours >= 1"
        )
    return value


class WorkflowTemplateService:
    """Owner-scoped persistence operations over workflow templates."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _generate_code(self, owner_id: uuid.UUID) -> str:
        """Return a unique, stable CUSTOM_* code for the owner (server-side)."""
        while True:
            code = f"CUSTOM_{uuid.uuid4().hex[:12].upper()}"
            exists = (
                await self.db.execute(
                    select(WorkflowTemplate.id).where(
                        WorkflowTemplate.owner_id == owner_id,
                        WorkflowTemplate.code == code,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                return code

    async def get_owned_template(
        self, owner_id: uuid.UUID, template_id: uuid.UUID
    ) -> WorkflowTemplate:
        stmt = (
            select(WorkflowTemplate)
            .where(
                WorkflowTemplate.id == template_id,
                WorkflowTemplate.owner_id == owner_id,
            )
            .options(
                selectinload(WorkflowTemplate.steps).selectinload(
                    WorkflowTemplateStep.price_item
                )
            )
            .execution_options(populate_existing=True)
        )
        template = (await self.db.execute(stmt)).scalar_one_or_none()
        if template is None:
            raise WorkflowTemplateNotFoundError(
                f"Workflow template {template_id} not found"
            )
        return template

    async def create_template(
        self,
        owner_id: uuid.UUID,
        *,
        display_name: str,
        description: str | None = None,
        applies_to_substrates: list[Substrate] | None = None,
        applies_to_quality: list[QualityLevel] | None = None,
        applies_to_surface_types: list[SurfaceType] | None = None,
        steps: list[WorkflowTemplateStepSpec] | None = None,
    ) -> WorkflowTemplate:
        """Create an owner-authored template (generated immutable code) with
        its ordered steps, atomically. Every step is validated first."""
        name = _normalize_text(display_name)
        if name is None:
            raise WorkflowTemplateValidationError(
                "owner-created templates require a display_name"
            )
        resolved = await self._resolve_steps(owner_id, steps or [], Counter())
        template = WorkflowTemplate(
            owner_id=owner_id,
            code=await self._generate_code(owner_id),
            display_name=name,
            description=_normalize_text(description),
            applies_to_substrates=_filter_values(applies_to_substrates),
            applies_to_quality=_filter_values(applies_to_quality),
            applies_to_surface_types=_filter_values(applies_to_surface_types),
        )
        self._append_steps(template, resolved)
        self.db.add(template)
        await self.db.commit()
        return await self.get_owned_template(owner_id, template.id)

    async def update_template(
        self,
        owner_id: uuid.UUID,
        template_id: uuid.UUID,
        *,
        display_name: str | None = None,
        description: str | None | object = _UNSET,
        applies_to_substrates: list[Substrate] | None | object = _UNSET,
        applies_to_quality: list[QualityLevel] | None | object = _UNSET,
        applies_to_surface_types: list[SurfaceType] | None | object = _UNSET,
    ) -> WorkflowTemplate:
        """Update editable fields; `code` is immutable. Never retroactive:
        no existing plan or provenance record is touched."""
        template = await self.get_owned_template(owner_id, template_id)
        if display_name is not None:
            name = _normalize_text(display_name)
            if name is None and template.name_key is None:
                raise WorkflowTemplateValidationError(
                    "owner-created templates require a display_name"
                )
            template.display_name = name
        if description is not _UNSET:
            template.description = _normalize_text(description)  # type: ignore[arg-type]
        if applies_to_substrates is not _UNSET:
            template.applies_to_substrates = _filter_values(applies_to_substrates)  # type: ignore[arg-type]
        if applies_to_quality is not _UNSET:
            template.applies_to_quality = _filter_values(applies_to_quality)  # type: ignore[arg-type]
        if applies_to_surface_types is not _UNSET:
            template.applies_to_surface_types = _filter_values(applies_to_surface_types)  # type: ignore[arg-type]
        await self.db.commit()
        return await self.get_owned_template(owner_id, template_id)

    async def replace_steps(
        self,
        owner_id: uuid.UUID,
        template_id: uuid.UUID,
        steps: list[WorkflowTemplateStepSpec],
    ) -> WorkflowTemplate:
        """Replace the template's ordered steps as a whole, atomically.
        Validation runs in full before any mutation."""
        template = await self.get_owned_template(owner_id, template_id)
        existing_counts = Counter(step.price_item_id for step in template.steps)
        resolved = await self._resolve_steps(owner_id, steps, existing_counts)
        # Nothing references steps, so the ORM delete-orphan cascade is safe;
        # flush the deletes first so renumbered positions cannot collide.
        template.steps.clear()
        await self.db.flush()
        self._append_steps(template, resolved)
        await self.db.commit()
        return await self.get_owned_template(owner_id, template_id)

    async def archive_template(
        self, owner_id: uuid.UUID, template_id: uuid.UUID
    ) -> WorkflowTemplate:
        """Soft-archive (idempotent). Plans and provenance are unaffected."""
        template = await self.get_owned_template(owner_id, template_id)
        template.is_archived = True
        await self.db.commit()
        return template

    async def restore_template(
        self, owner_id: uuid.UUID, template_id: uuid.UUID
    ) -> WorkflowTemplate:
        """Restore an archived template (idempotent); explicit only."""
        template = await self.get_owned_template(owner_id, template_id)
        template.is_archived = False
        await self.db.commit()
        return template

    async def _resolve_steps(
        self,
        owner_id: uuid.UUID,
        steps: list[WorkflowTemplateStepSpec],
        existing_counts: Counter[uuid.UUID],
    ) -> list[tuple[PriceItem, WorkflowTemplateStepSpec]]:
        if not steps:
            return []
        ids = [step.price_item_id for step in steps]
        requested_counts = Counter(ids)
        items = (
            await self.db.execute(select(PriceItem).where(PriceItem.id.in_(ids)))
        ).scalars().all()
        by_id = {item.id: item for item in items}
        resolved: list[tuple[PriceItem, WorkflowTemplateStepSpec]] = []
        for step in steps:
            item = by_id.get(step.price_item_id)
            if item is None or item.owner_id != owner_id:
                raise PriceItemNotFoundError(
                    f"Price item {step.price_item_id} not found"
                )
            if item.category == PriceCategory.REVEAL:
                raise WorkflowTemplateValidationError(
                    f"Price item {item.id}: reveal work belongs under an opening, "
                    "not in a surface workflow template"
                )
            if (
                item.is_archived
                and requested_counts[item.id] > existing_counts[item.id]
            ):
                raise WorkflowTemplateValidationError(
                    f"Archived price item {item.id} cannot be added to a workflow template"
                )
            validate_wait_after_hours(step.wait_after_hours)
            resolved.append((item, step))
        return resolved

    @staticmethod
    def _append_steps(
        template: WorkflowTemplate,
        resolved: list[tuple[PriceItem, WorkflowTemplateStepSpec]],
    ) -> None:
        for position, (item, step) in enumerate(resolved):
            template.steps.append(
                WorkflowTemplateStep(
                    position=position,
                    price_item_id=item.id,
                    is_optional=step.is_optional,
                    note=_normalize_text(step.note),
                    wait_after_hours=step.wait_after_hours,
                )
            )
