"""The link for the client, the owner's side (V2-8): make, extend, revoke the link; write and withdraw extra-work proposals; read the journal of consents.

Every call is owner-scoped. The secret is made here and handed back once; only its SHA-256 is stored. Services commit internally.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import client_link as rules
from app.domain.exceptions import ProjectNotFoundError
from app.models.client_link import (
    ClientConsent,
    ClientLink,
    ClientProposal,
    ProposalStatus,
)
from app.models.project import Project

CURRENCY = "PLN"


def aware(value: datetime) -> datetime:
    """SQLite gives back naive instants; the database of the application keeps UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ClientLinkService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _current(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> ClientLink | None:
        return (
            await self.db.execute(
                select(ClientLink).where(
                    ClientLink.project_id == project_id, ClientLink.owner_id == owner_id, ClientLink.revoked_at.is_(None)
                )
            )
        ).scalar_one_or_none()

    # -- the link ---------------------------------------------------------------------------------------------------------------

    async def status(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> ClientLink | None:
        """The unrevoked link of the object (it may be expired: the screen says so), or None."""
        await self._ensure_project(owner_id, project_id)
        return await self._current(owner_id, project_id)

    async def create(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, language: str | None, *, now: datetime | None = None
    ) -> tuple[ClientLink, str]:
        """A new link; the earlier one of the object stops working. Returns the row and the secret (shown once)."""
        await self._ensure_project(owner_id, project_id)
        now = now or datetime.now(UTC)
        old = await self._current(owner_id, project_id)
        if old is not None:
            old.revoked_at = now
            await self.db.flush()  # the unique index of the unrevoked link must see the old one gone
        token = rules.new_token()
        link = ClientLink(
            owner_id=owner_id,
            project_id=project_id,
            token_hash=rules.hash_token(token),
            language=rules.clean_language(language),
            created_at=now,
            expires_at=now + rules.LINK_TERM,
            view_count=0,
        )
        self.db.add(link)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise rules.ClientLinkError("LINK_BUSY", "the link is being made by another request") from None
        await self.db.refresh(link)
        return link, token

    async def extend(self, owner_id: uuid.UUID, project_id: uuid.UUID, *, now: datetime | None = None) -> ClientLink:
        """Thirty more days counted from today (an expired link comes back to life; a revoked one does not)."""
        await self._ensure_project(owner_id, project_id)
        link = await self._current(owner_id, project_id)
        if link is None:
            raise rules.ClientLinkNotFoundError("no link")
        now = now or datetime.now(UTC)
        link.expires_at = max(aware(link.expires_at), now + rules.LINK_TERM)
        await self.db.commit()
        await self.db.refresh(link)
        return link

    async def revoke(self, owner_id: uuid.UUID, project_id: uuid.UUID, *, now: datetime | None = None) -> None:
        await self._ensure_project(owner_id, project_id)
        link = await self._current(owner_id, project_id)
        if link is None:
            raise rules.ClientLinkNotFoundError("no link")
        link.revoked_at = now or datetime.now(UTC)
        await self.db.commit()

    # -- the proposals ----------------------------------------------------------------------------------------------------------

    async def list_proposals(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[ClientProposal]:
        await self._ensure_project(owner_id, project_id)
        return list(
            (
                await self.db.execute(
                    select(ClientProposal)
                    .where(ClientProposal.project_id == project_id, ClientProposal.owner_id == owner_id)
                    .order_by(ClientProposal.sequence.desc())
                )
            ).scalars()
        )

    async def create_proposal(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        title: str,
        description: str | None,
        amount: Decimal,
        extra_days: int | None,
        now: datetime | None = None,
    ) -> ClientProposal:
        await self._ensure_project(owner_id, project_id)
        title = rules.clean_title(title)
        description = rules.clean_description(description)
        amount = rules.clean_amount(amount)
        extra_days = rules.clean_days(extra_days)
        count, top = (
            await self.db.execute(
                select(func.count(), func.coalesce(func.max(ClientProposal.sequence), 0)).where(
                    ClientProposal.project_id == project_id, ClientProposal.owner_id == owner_id
                )
            )
        ).one()
        if count >= rules.MAX_PROPOSALS:
            raise rules.ClientLinkError("TOO_MANY_PROPOSALS", f"at most {rules.MAX_PROPOSALS} proposals per object")
        row = ClientProposal(
            owner_id=owner_id,
            project_id=project_id,
            sequence=top + 1,
            title=title,
            description=description,
            amount=amount,
            currency=CURRENCY,
            extra_days=extra_days,
            status=ProposalStatus.OPEN.value,
            content_hash=rules.proposal_hash(title, description, amount, CURRENCY, extra_days),
            created_at=now or datetime.now(UTC),
        )
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise rules.ClientLinkError("PROPOSAL_BUSY", "another proposal was written at the same moment") from None
        await self.db.refresh(row)
        return row

    async def withdraw_proposal(self, owner_id: uuid.UUID, project_id: uuid.UUID, proposal_id: uuid.UUID) -> ClientProposal:
        await self._ensure_project(owner_id, project_id)
        row = (
            await self.db.execute(
                select(ClientProposal).where(
                    ClientProposal.id == proposal_id, ClientProposal.project_id == project_id, ClientProposal.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise rules.ClientLinkNotFoundError("no proposal")
        if row.status != ProposalStatus.OPEN.value:
            raise rules.ClientLinkError("PROPOSAL_NOT_OPEN", "only an open proposal can be withdrawn")
        row.status = ProposalStatus.WITHDRAWN.value
        await self.db.commit()
        await self.db.refresh(row)
        return row

    # -- the journal ------------------------------------------------------------------------------------------------------------

    async def journal(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[ClientConsent]:
        """What the client agreed to or declined, the newest first. Rows are only ever added."""
        await self._ensure_project(owner_id, project_id)
        return list(
            (
                await self.db.execute(
                    select(ClientConsent)
                    .where(ClientConsent.project_id == project_id, ClientConsent.owner_id == owner_id)
                    .order_by(ClientConsent.created_at.desc(), ClientConsent.id.desc())
                )
            ).scalars()
        )
