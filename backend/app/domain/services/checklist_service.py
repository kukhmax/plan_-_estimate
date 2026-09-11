import asyncio
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.checklist_templates import build_baseline_templates
from app.domain.exceptions import ChecklistTemplateNotFoundError
from app.models.checklist import (
    ChecklistOption,
    ChecklistQuestion,
    ChecklistSection,
    ChecklistTemplate,
    Substrate,
)

# Serializes concurrent first-call bootstraps within the process. Correctness
# (never double-insert) is additionally guaranteed by the (code, version)
# unique constraint; the lock just avoids a redundant IntegrityError.
_bootstrap_lock = asyncio.Lock()


class ChecklistService:
    """Catalog access and idempotent bootstrap for immutable checklist templates."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_bootstrapped(self) -> None:
        """Materialize every missing baseline (code, version) template exactly once.

        Runs on every catalog access: a single cheap existence query finds the
        missing versions, so the catalog heals automatically after a DB reset
        and picks up newly shipped template versions without any process-global
        cache that could go stale.
        """
        async with _bootstrap_lock:
            existing_rows = (
                await self.db.execute(
                    select(ChecklistTemplate.code, ChecklistTemplate.version)
                )
            ).all()
            existing = {(row.code, row.version) for row in existing_rows}
            missing = [
                data
                for data in build_baseline_templates()
                if (data.code, data.version) not in existing
            ]
            if not missing:
                return

            for data in missing:
                template = ChecklistTemplate(
                    code=data.code,
                    version=data.version,
                    substrate=data.substrate,
                    title_key=data.title_key,
                    active=True,
                )
                self.db.add(template)
                await self.db.flush()

                for section_position, section_data in enumerate(data.sections):
                    section = ChecklistSection(
                        template_id=template.id,
                        key=section_data.key,
                        position=section_position,
                        title_key=section_data.title_key,
                        description_key=section_data.description_key,
                    )
                    self.db.add(section)
                    await self.db.flush()

                    for question_position, question_data in enumerate(
                        section_data.questions
                    ):
                        question = ChecklistQuestion(
                            template_id=template.id,
                            section_id=section.id,
                            position=question_position,
                            key=question_data.key,
                            text_key=question_data.text_key,
                            hint_key=question_data.hint_key,
                            unit_key=question_data.unit_key,
                            answer_type=question_data.answer_type,
                            finding_key=question_data.finding_key,
                        )
                        self.db.add(question)
                        await self.db.flush()

                        for option_position, option_data in enumerate(
                            question_data.options
                        ):
                            self.db.add(
                                ChecklistOption(
                                    question_id=question.id,
                                    position=option_position,
                                    key=option_data.key,
                                    label_key=option_data.label_key,
                                    finding_key=option_data.finding_key,
                                )
                            )
            await self.db.commit()

    async def _load_sections(self, template_id: uuid.UUID) -> list[ChecklistSection]:
        sections = list(
            (
                await self.db.execute(
                    select(ChecklistSection)
                    .where(ChecklistSection.template_id == template_id)
                    .order_by(ChecklistSection.position)
                )
            ).scalars().all()
        )
        for section in sections:
            questions = list(
                (
                    await self.db.execute(
                        select(ChecklistQuestion)
                        .where(ChecklistQuestion.section_id == section.id)
                        .order_by(ChecklistQuestion.position)
                    )
                ).scalars().all()
            )
            for question in questions:
                question.options = list(
                    (
                        await self.db.execute(
                            select(ChecklistOption)
                            .where(ChecklistOption.question_id == question.id)
                            .order_by(ChecklistOption.position)
                        )
                    ).scalars().all()
                )
            section.questions = questions
        return sections

    async def list_templates(
        self,
        *,
        substrate: Substrate | None = None,
        include_inactive: bool = False,
    ) -> tuple[list[ChecklistTemplate], int]:
        await self._ensure_bootstrapped()

        stmt = select(ChecklistTemplate)
        if substrate is not None:
            stmt = stmt.where(ChecklistTemplate.substrate == substrate)
        if not include_inactive:
            stmt = stmt.where(ChecklistTemplate.active.is_(True))

        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        items = list(
            (
                await self.db.execute(
                    stmt.order_by(
                        ChecklistTemplate.substrate.asc().nulls_last(),
                        ChecklistTemplate.code.asc(),
                    )
                )
            ).scalars().all()
        )
        return items, total

    async def get_template(self, template_id: uuid.UUID) -> ChecklistTemplate:
        await self._ensure_bootstrapped()

        template = (
            await self.db.execute(
                select(ChecklistTemplate).where(ChecklistTemplate.id == template_id)
            )
        ).scalar_one_or_none()
        if template is None:
            raise ChecklistTemplateNotFoundError(
                f"Checklist template {template_id} not found"
            )
        template.sections = await self._load_sections(template.id)
        return template
