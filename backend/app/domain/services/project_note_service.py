"""Notes of the owner on an object (Stage 18): a list with the time of each, write, change, remove. Every call is owner-scoped."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    ProjectNoteInvalidError,
    ProjectNoteNotFoundError,
    ProjectNotFoundError,
)
from app.models.project import Project
from app.domain.services.client_ids import find_repeat
from app.models.project_note import MAX_NOTE_LENGTH, ProjectNote


def _clean(body: str) -> str:
    text = body.strip()
    if not text:
        raise ProjectNoteInvalidError("A note cannot be empty")
    if len(text) > MAX_NOTE_LENGTH:
        raise ProjectNoteInvalidError(f"A note is at most {MAX_NOTE_LENGTH} characters")
    return text


class ProjectNoteService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _get(self, owner_id: uuid.UUID, project_id: uuid.UUID, note_id: uuid.UUID) -> ProjectNote:
        await self._ensure_project(owner_id, project_id)
        note = (
            await self.db.execute(
                select(ProjectNote).where(ProjectNote.id == note_id, ProjectNote.project_id == project_id, ProjectNote.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        if note is None:
            raise ProjectNoteNotFoundError(f"Note {note_id} not found")
        return note

    async def list_notes(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> tuple[list[ProjectNote], int]:
        """The newest first (the order of writing; the id keeps two notes of one instant in a stable order)."""
        await self._ensure_project(owner_id, project_id)
        rows = list(
            (
                await self.db.execute(
                    select(ProjectNote)
                    .where(ProjectNote.project_id == project_id, ProjectNote.owner_id == owner_id)
                    .order_by(ProjectNote.created_at.desc(), ProjectNote.id.desc())
                )
            ).scalars()
        )
        return rows, len(rows)

    async def count_notes(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> int:
        await self._ensure_project(owner_id, project_id)
        return (
            await self.db.execute(
                select(func.count()).select_from(ProjectNote).where(ProjectNote.project_id == project_id, ProjectNote.owner_id == owner_id)
            )
        ).scalar_one()

    async def create_note(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, body: str, *, client_id: uuid.UUID | None = None
    ) -> ProjectNote:
        await self._ensure_project(owner_id, project_id)
        text = _clean(body)
        repeat = await find_repeat(self.db, ProjectNote, client_id, {"owner_id": owner_id, "project_id": project_id, "body": text})
        if repeat is not None:
            return repeat
        now = datetime.now(UTC)
        note = ProjectNote(id=client_id or uuid.uuid4(), owner_id=owner_id, project_id=project_id, body=text, created_at=now, updated_at=now)
        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def update_note(self, owner_id: uuid.UUID, project_id: uuid.UUID, note_id: uuid.UUID, body: str) -> ProjectNote:
        note = await self._get(owner_id, project_id, note_id)
        note.body = _clean(body)
        note.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def delete_note(self, owner_id: uuid.UUID, project_id: uuid.UUID, note_id: uuid.UUID) -> None:
        await self._get(owner_id, project_id, note_id)
        await self.db.execute(delete(ProjectNote).where(ProjectNote.id == note_id))
        await self.db.commit()
