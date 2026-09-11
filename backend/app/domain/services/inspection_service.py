import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    ChecklistTemplateNotFoundError,
    InspectionAnswerValidationError,
    InspectionNotFoundError,
    InspectionStateError,
    InvalidInspectionTargetError,
    InvalidSurfaceTypeError,
    ProjectNotFoundError,
    QualityScaleMismatchError,
    RoomNotFoundError,
    SubstrateTemplateMismatchError,
    SurfaceNotFoundError,
)
from app.domain.rules.inspection_rules import (
    FindingSpec,
    assert_quality_scale_valid,
    build_finding_specs,
)
from app.models.checklist import (
    AnswerType,
    ChecklistOption,
    ChecklistQuestion,
    ChecklistSection,
    ChecklistTemplate,
)
from app.models.inspection import (
    Inspection,
    InspectionAnswer,
    InspectionFinding,
    InspectionStatus,
)
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.schemas.inspection import (
    InspectionAnswerPayload,
    InspectionAnswersPut,
    InspectionCreate,
    InspectionUpdate,
)


def _validate_answer_payload(
    question: ChecklistQuestion,
    options: list[ChecklistOption],
    payload: InspectionAnswerPayload,
) -> None:
    """Enforce that the payload matches the question's answer_type exactly.

    Only the value column(s) belonging to the answer type may be populated.
    """
    answer_type = question.answer_type
    if answer_type is AnswerType.BOOLEAN:
        if payload.value_bool is None:
            raise InspectionAnswerValidationError(
                f"Question {question.key} requires value_bool"
            )
        if (
            payload.value_number is not None
            or payload.value_text is not None
            or payload.option_key is not None
            or payload.option_keys is not None
        ):
            raise InspectionAnswerValidationError(
                f"Question {question.key} accepts only value_bool"
            )
    elif answer_type is AnswerType.NUMBER:
        if payload.value_number is None:
            raise InspectionAnswerValidationError(
                f"Question {question.key} requires value_number"
            )
        if (
            payload.value_bool is not None
            or payload.value_text is not None
            or payload.option_key is not None
            or payload.option_keys is not None
        ):
            raise InspectionAnswerValidationError(
                f"Question {question.key} accepts only value_number"
            )
    elif answer_type is AnswerType.TEXT:
        if not payload.value_text:
            raise InspectionAnswerValidationError(
                f"Question {question.key} requires value_text"
            )
        if (
            payload.value_bool is not None
            or payload.value_number is not None
            or payload.option_key is not None
            or payload.option_keys is not None
        ):
            raise InspectionAnswerValidationError(
                f"Question {question.key} accepts only value_text"
            )
    elif answer_type is AnswerType.SINGLE_CHOICE:
        if payload.option_key is None:
            raise InspectionAnswerValidationError(
                f"Question {question.key} requires option_key"
            )
        valid_keys = {option.key for option in options}
        if payload.option_key not in valid_keys:
            raise InspectionAnswerValidationError(
                f"Question {question.key} has no option {payload.option_key}"
            )
        if (
            payload.value_bool is not None
            or payload.value_number is not None
            or payload.value_text is not None
            or payload.option_keys is not None
        ):
            raise InspectionAnswerValidationError(
                f"Question {question.key} accepts only option_key"
            )
    elif answer_type is AnswerType.MULTI_CHOICE:
        if not payload.option_keys:
            raise InspectionAnswerValidationError(
                f"Question {question.key} requires option_keys"
            )
        valid_keys = {option.key for option in options}
        if any(key not in valid_keys for key in payload.option_keys):
            raise InspectionAnswerValidationError(
                f"Question {question.key} contains an unknown option"
            )
        if len(set(payload.option_keys)) != len(payload.option_keys):
            raise InspectionAnswerValidationError(
                f"Question {question.key} contains duplicate options"
            )
        if (
            payload.value_bool is not None
            or payload.value_number is not None
            or payload.value_text is not None
            or payload.option_key is not None
        ):
            raise InspectionAnswerValidationError(
                f"Question {question.key} accepts only option_keys"
            )


class InspectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_room_owned(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> None:
        project = (
            await self.db.execute(
                select(Project.id).where(
                    Project.id == project_id,
                    Project.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        room = (
            await self.db.execute(
                select(Room.id).where(
                    Room.id == room_id,
                    Room.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError(f"Room {room_id} not found")

    async def _ensure_surface_in_room(
        self,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
    ) -> Surface:
        surface = (
            await self.db.execute(
                select(Surface).where(
                    Surface.id == surface_id,
                    Surface.room_id == room_id,
                )
            )
        ).scalar_one_or_none()
        if surface is None:
            raise SurfaceNotFoundError(
                f"Surface {surface_id} not found in room {room_id}"
            )
        if surface.surface_type is not SurfaceType.WALL:
            raise InvalidSurfaceTypeError(
                "Inspection cannot target a non-WALL surface; use plane FLOOR/CEILING"
            )
        return surface

    async def _get_inspection(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Inspection:
        await self._ensure_room_owned(project_id, room_id, owner_id)
        inspection = (
            await self.db.execute(
                select(Inspection).where(
                    Inspection.id == inspection_id,
                    Inspection.room_id == room_id,
                )
            )
        ).scalar_one_or_none()
        if inspection is None:
            raise InspectionNotFoundError(
                f"Inspection {inspection_id} not found in room {room_id}"
            )
        return inspection

    async def _load_template_questions(
        self,
        template_id: uuid.UUID,
    ) -> dict[uuid.UUID, tuple[ChecklistQuestion, list[ChecklistOption]]]:
        questions = list(
            (
                await self.db.execute(
                    select(ChecklistQuestion).where(
                        ChecklistQuestion.template_id == template_id
                    )
                )
            ).scalars().all()
        )
        result: dict[uuid.UUID, tuple[ChecklistQuestion, list[ChecklistOption]]] = {}
        for question in questions:
            options = list(
                (
                    await self.db.execute(
                        select(ChecklistOption)
                        .where(ChecklistOption.question_id == question.id)
                        .order_by(ChecklistOption.position)
                    )
                ).scalars().all()
            )
            result[question.id] = (question, options)
        return result

    async def _list_answers(
        self,
        inspection_id: uuid.UUID,
    ) -> list[InspectionAnswer]:
        stmt = (
            select(InspectionAnswer)
            .join(
                ChecklistQuestion,
                InspectionAnswer.question_id == ChecklistQuestion.id,
            )
            .outerjoin(
                ChecklistSection,
                ChecklistQuestion.section_id == ChecklistSection.id,
            )
            .where(InspectionAnswer.inspection_id == inspection_id)
            .order_by(
                ChecklistSection.position.asc().nulls_last(),
                ChecklistQuestion.position.asc(),
                InspectionAnswer.created_at.asc(),
            )
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def _reconcile_findings(
        self,
        inspection_id: uuid.UUID,
        specs: list[FindingSpec],
    ) -> None:
        """Reconcile findings on completion: create, reuse, or deactivate.

        Findings are never deleted. The reconciliation identity is the source
        (question_id, finding_key) pair, so two distinct questions that happen
        to share a semantic finding_key remain two separate findings and never
        overwrite each other. A confirmed source is reused (its UUID stays
        stable for downstream photo linking) while its snapshot and source
        answer are refreshed; active findings absent from the new spec set are
        resolved.
        """
        active = list(
            (
                await self.db.execute(
                    select(InspectionFinding).where(
                        InspectionFinding.inspection_id == inspection_id,
                        InspectionFinding.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )
        by_identity = {
            (finding.question_id, finding.finding_key): finding
            for finding in active
        }
        now = datetime.now(timezone.utc)

        seen_identities: set[tuple[uuid.UUID | None, str]] = set()
        for position, spec in enumerate(specs):
            identity = (spec.question_id, spec.finding_key)
            if identity in seen_identities:
                # First occurrence wins if one completion yields the same source
                # twice (e.g. duplicate duplicate option keys on one question).
                continue
            seen_identities.add(identity)
            existing = by_identity.get(identity)
            if existing is None:
                self.db.add(
                    InspectionFinding(
                        inspection_id=inspection_id,
                        answer_id=spec.answer_id,
                        question_id=spec.question_id,
                        finding_key=spec.finding_key,
                        label_key=spec.label_key,
                        value_snapshot=spec.value_snapshot,
                        is_active=True,
                        position=position,
                    )
                )
            else:
                existing.answer_id = spec.answer_id
                existing.question_id = spec.question_id
                existing.label_key = spec.label_key
                existing.value_snapshot = spec.value_snapshot
                existing.position = position
                existing.resolved_at = None

        for finding in active:
            if (finding.question_id, finding.finding_key) not in seen_identities:
                finding.is_active = False
                finding.resolved_at = now

    async def list_inspections(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> tuple[list[Inspection], int]:
        await self._ensure_room_owned(project_id, room_id, owner_id)

        stmt = select(Inspection).where(Inspection.room_id == room_id)
        if not include_archived:
            stmt = stmt.where(Inspection.is_archived.is_(False))
        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        items = list(
            (
                await self.db.execute(
                    stmt.order_by(
                        Inspection.created_at.desc(),
                        Inspection.id.asc(),
                    )
                )
            ).scalars().all()
        )
        return items, total

    async def create_inspection(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
        payload: InspectionCreate,
    ) -> Inspection:
        await self._ensure_room_owned(project_id, room_id, owner_id)

        if payload.surface_id is not None and payload.plane is not None:
            raise InvalidInspectionTargetError(
                "Inspection cannot target both a surface and a plane"
            )

        template = (
            await self.db.execute(
                select(ChecklistTemplate).where(
                    ChecklistTemplate.id == payload.template_id,
                    ChecklistTemplate.active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if template is None:
            raise ChecklistTemplateNotFoundError(
                f"Active checklist template {payload.template_id} not found"
            )
        if template.substrate is not None and template.substrate != payload.substrate:
            raise SubstrateTemplateMismatchError(
                f"Template {template.code} does not serve substrate {payload.substrate.value}"
            )

        assert_quality_scale_valid(payload.substrate, payload.quality_target)

        if payload.surface_id is not None:
            await self._ensure_surface_in_room(room_id, payload.surface_id)

        inspection = Inspection(
            room_id=room_id,
            surface_id=payload.surface_id,
            plane=payload.plane,
            template_id=template.id,
            substrate=payload.substrate,
            quality_target=payload.quality_target,
            notes=payload.notes,
        )
        self.db.add(inspection)
        await self.db.commit()
        await self.db.refresh(inspection)
        return inspection

    async def get_inspection(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Inspection:
        return await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )

    async def update_inspection(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
        payload: InspectionUpdate,
    ) -> Inspection:
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        if inspection.status is not InspectionStatus.DRAFT:
            raise InspectionStateError(
                "Cannot update a completed inspection; reopen it first"
            )

        changes = payload.model_dump(exclude_unset=True)
        if "substrate" in changes:
            template = (
                await self.db.execute(
                    select(ChecklistTemplate).where(
                        ChecklistTemplate.id == inspection.template_id
                    )
                )
            ).scalar_one_or_none()
            if template is not None and template.substrate is not None:
                if template.substrate != changes["substrate"]:
                    raise SubstrateTemplateMismatchError(
                        f"Template {template.code} does not serve substrate "
                        f"{changes['substrate'].value}"
                    )

        if "quality_target" in changes:
            effective_substrate = changes.get("substrate", inspection.substrate)
            assert_quality_scale_valid(effective_substrate, changes["quality_target"])

        for field, value in changes.items():
            setattr(inspection, field, value)

        await self.db.commit()
        await self.db.refresh(inspection)
        return inspection

    async def replace_answers(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
        payload: InspectionAnswersPut,
    ) -> list[InspectionAnswer]:
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        if inspection.status is not InspectionStatus.DRAFT:
            raise InspectionStateError(
                "Answers can only be edited while the inspection is DRAFT"
            )

        question_map = await self._load_template_questions(inspection.template_id)
        seen: set[uuid.UUID] = set()
        new_answers: list[InspectionAnswer] = []
        for answer_payload in payload.answers:
            entry = question_map.get(answer_payload.question_id)
            if entry is None:
                raise InspectionAnswerValidationError(
                    f"Question {answer_payload.question_id} does not belong to "
                    "the inspection template"
                )
            if answer_payload.question_id in seen:
                raise InspectionAnswerValidationError(
                    "Cannot answer the same question more than once"
                )
            seen.add(answer_payload.question_id)
            question, options = entry
            _validate_answer_payload(question, options, answer_payload)
            new_answers.append(
                InspectionAnswer(
                    inspection_id=inspection.id,
                    question_id=answer_payload.question_id,
                    value_bool=answer_payload.value_bool,
                    value_number=answer_payload.value_number,
                    value_text=answer_payload.value_text,
                    option_key=answer_payload.option_key,
                    option_keys=answer_payload.option_keys,
                )
            )

        # Replace-set semantics: previous answers are dropped, the incoming set
        # becomes the whole answer state.
        await self.db.execute(
            delete(InspectionAnswer).where(
                InspectionAnswer.inspection_id == inspection.id
            )
        )
        await self.db.flush()
        self.db.add_all(new_answers)
        await self.db.commit()
        return await self._list_answers(inspection.id)

    async def list_answers(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[InspectionAnswer]:
        await self._get_inspection(project_id, room_id, inspection_id, owner_id)
        return await self._list_answers(inspection_id)

    async def complete_inspection(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Inspection:
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        if inspection.status is not InspectionStatus.DRAFT:
            raise InspectionStateError(
                "Only a DRAFT inspection can be completed"
            )

        answers = await self._list_answers(inspection.id)
        question_map = await self._load_template_questions(inspection.template_id)
        rows = []
        for answer in answers:
            entry = question_map.get(answer.question_id)
            if entry is None:
                continue
            question, options = entry
            rows.append((answer, question, options))

        await self._reconcile_findings(inspection.id, build_finding_specs(rows))
        inspection.status = InspectionStatus.COMPLETED
        inspection.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(inspection)
        return inspection

    async def reopen_inspection(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Inspection:
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        if inspection.status is not InspectionStatus.COMPLETED:
            raise InspectionStateError(
                "Only a COMPLETED inspection can be reopened"
            )
        inspection.status = InspectionStatus.DRAFT
        inspection.completed_at = None
        await self.db.commit()
        await self.db.refresh(inspection)
        return inspection

    async def archive_inspection(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Inspection:
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        inspection.is_archived = True
        await self.db.commit()
        await self.db.refresh(inspection)
        return inspection

    async def restore_inspection(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Inspection:
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        inspection.is_archived = False
        await self.db.commit()
        await self.db.refresh(inspection)
        return inspection

    async def list_findings(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        include_inactive: bool = False,
    ) -> list[InspectionFinding]:
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        stmt = select(InspectionFinding).where(
            InspectionFinding.inspection_id == inspection.id
        )
        if not include_inactive:
            stmt = stmt.where(InspectionFinding.is_active.is_(True))
        stmt = stmt.order_by(
            InspectionFinding.position.asc().nulls_last(),
            InspectionFinding.created_at.asc(),
        )
        return list((await self.db.execute(stmt)).scalars().all())