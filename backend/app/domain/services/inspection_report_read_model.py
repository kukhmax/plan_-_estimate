"""What an inspection says, for a document (Stage 15E): the answered checklist and the active risks of every live
inspection of one project, read-only.

The photo read model (14I) knows only the nodes that have selected photos. A client report also has to say what was
found and why extra work may be needed, even where no photo was taken, so this reads the inspections themselves.

Rules: only inspections of live rooms that are not archived themselves and whose own surface is not archived; the answers
and risks of an inspection are read only when it is COMPLETED (a draft is unfinished: its risks were never evaluated and
its answers may still change); only answered questions; only active risks, most severe first; the number of SQL statements
does not depend on the number of inspections. Texts stay keys here -- the document layer puts them into Polish.
"""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.project_service import ProjectService
from app.models.checklist import (
    AnswerType,
    ChecklistOption,
    ChecklistQuestion,
    ChecklistSection,
)
from app.models.inspection import Inspection, InspectionAnswer, InspectionStatus
from app.models.risk import Risk, RiskSeverity
from app.models.room import Room
from app.models.surface import Surface

_SEVERITY_RANK = {
    RiskSeverity.CRITICAL: 0,
    RiskSeverity.HIGH: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.LOW: 3,
}
_NO_POSITION = 1 << 30


@dataclass(frozen=True, slots=True)
class AnswerLine:
    section_key: str | None  # title key of the checklist section
    question_key: str  # text key of the question
    answer_type: str
    unit: str | None
    value_bool: bool | None
    value_number: Decimal | None
    value_text: str | None
    option_label_keys: tuple[str, ...]  # label keys of the chosen options (one for a single choice)


@dataclass(frozen=True, slots=True)
class RiskLine:
    severity: str
    title_key: str
    explanation_key: str
    consequence_key: str
    communication_key: str
    blocks_finishing: bool


@dataclass(frozen=True, slots=True)
class InspectionInfo:
    inspection_id: uuid.UUID
    room_id: uuid.UUID
    surface_id: uuid.UUID | None
    surface_name: str | None
    plane: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None
    substrate: str
    quality_target: str | None
    notes: str | None
    answers: tuple[AnswerLine, ...]
    risks: tuple[RiskLine, ...]

    @property
    def has_content(self) -> bool:
        return bool(self.answers or self.risks or self.notes)


@dataclass(frozen=True, slots=True)
class RoomInfo:
    room_id: uuid.UUID
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InspectionReportData:
    rooms: tuple[RoomInfo, ...]  # live rooms, in document order
    inspections: tuple[InspectionInfo, ...]  # live inspections, in document order (by creation)

    def of_room(self, room_id: uuid.UUID) -> tuple[InspectionInfo, ...]:
        return tuple(i for i in self.inspections if i.room_id == room_id)


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class InspectionReportReadModel:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> InspectionReportData:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        rooms = [
            room
            for room in (await self.db.execute(select(Room).where(Room.project_id == project_id))).scalars().all()
            if not room.is_archived
        ]
        room_ids = [room.id for room in rooms]
        inspections = await self._rows(Inspection, Inspection.room_id, room_ids)
        surface_ids = {i.surface_id for i in inspections if i.surface_id is not None}
        surfaces = {s.id: s for s in await self._rows(Surface, Surface.id, list(surface_ids))}
        live = [
            i for i in inspections
            if not i.is_archived and (i.surface_id is None or (i.surface_id in surfaces and not surfaces[i.surface_id].is_archived))
        ]
        completed = [i for i in live if i.status is InspectionStatus.COMPLETED]
        answers = await self._answers(completed)
        risks = await self._risks([i.id for i in completed])
        infos = tuple(
            InspectionInfo(
                inspection_id=i.id,
                room_id=i.room_id,
                surface_id=i.surface_id,
                surface_name=surfaces[i.surface_id].name if i.surface_id else None,
                plane=i.plane.value if i.plane else None,
                status=i.status.value,
                created_at=_utc(i.created_at),
                completed_at=_utc(i.completed_at),
                substrate=i.substrate.value,
                quality_target=i.quality_target.value if i.quality_target else None,
                notes=(i.notes or "").strip() or None if i.status is InspectionStatus.COMPLETED else None,
                answers=answers.get(i.id, ()),
                risks=risks.get(i.id, ()),
            )
            for i in sorted(live, key=lambda row: (_utc(row.created_at), row.id))
        )
        room_infos = tuple(
            RoomInfo(room.id, room.name, _utc(room.created_at))
            for room in sorted(rooms, key=lambda row: (_utc(row.created_at), row.id))
        )
        return InspectionReportData(room_infos, infos)

    async def _rows(self, model, column, ids: list) -> list:
        if not ids:
            return []
        return list((await self.db.execute(select(model).where(column.in_(ids)))).scalars().all())

    async def _answers(self, inspections: list[Inspection]) -> dict[uuid.UUID, tuple[AnswerLine, ...]]:
        if not inspections:
            return {}
        rows = await self._rows(InspectionAnswer, InspectionAnswer.inspection_id, [i.id for i in inspections])
        if not rows:
            return {}
        questions = {q.id: q for q in await self._rows(ChecklistQuestion, ChecklistQuestion.id, list({a.question_id for a in rows}))}
        sections = {
            s.id: s
            for s in await self._rows(ChecklistSection, ChecklistSection.id, list({q.section_id for q in questions.values() if q.section_id}))
        }
        options: dict[uuid.UUID, dict[str, str]] = {}
        for option in await self._rows(ChecklistOption, ChecklistOption.question_id, list(questions)):
            options.setdefault(option.question_id, {})[option.key] = option.label_key

        found: dict[uuid.UUID, list[tuple[tuple, AnswerLine]]] = {}
        for answer in rows:
            question = questions.get(answer.question_id)
            if question is None:
                continue
            keys: tuple[str, ...] = ()
            if question.answer_type is AnswerType.SINGLE_CHOICE and answer.option_key:
                keys = (options.get(question.id, {}).get(answer.option_key, answer.option_key),)
            elif question.answer_type is AnswerType.MULTI_CHOICE and answer.option_keys is not None:
                keys = tuple(options.get(question.id, {}).get(key, key) for key in answer.option_keys)
            answered = (
                answer.value_bool is not None
                or answer.value_number is not None
                or bool(answer.value_text)
                or bool(keys)
                or (question.answer_type is AnswerType.MULTI_CHOICE and answer.option_keys is not None)
            )
            if not answered:
                continue
            section = sections.get(question.section_id) if question.section_id else None
            line = AnswerLine(
                section_key=section.title_key if section else None,
                question_key=question.text_key,
                answer_type=question.answer_type.value,
                unit=question.unit_key,
                value_bool=answer.value_bool,
                value_number=answer.value_number,
                value_text=answer.value_text or None,
                option_label_keys=keys,
            )
            order = (section.position if section else -1, question.position, question.id)
            found.setdefault(answer.inspection_id, []).append((order, line))
        return {key: tuple(line for _, line in sorted(items, key=lambda item: item[0])) for key, items in found.items()}

    async def _risks(self, inspection_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[RiskLine, ...]]:
        if not inspection_ids:
            return {}
        rows = [r for r in await self._rows(Risk, Risk.inspection_id, inspection_ids) if r.is_active]
        grouped: dict[uuid.UUID, list[Risk]] = {}
        for risk in rows:
            grouped.setdefault(risk.inspection_id, []).append(risk)
        return {
            inspection_id: tuple(
                RiskLine(
                    severity=r.severity.value,
                    title_key=r.title_key,
                    explanation_key=r.explanation_key,
                    consequence_key=r.consequence_key,
                    communication_key=r.communication_key,
                    blocks_finishing=r.blocks_finishing,
                )
                for r in sorted(
                    risks,
                    key=lambda r: (_SEVERITY_RANK[r.severity], r.position if r.position is not None else _NO_POSITION, r.rule_code, r.id),
                )
            )
            for inspection_id, risks in grouped.items()
        }
