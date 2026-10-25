"""The open page for the client (V2-8): find the link by its secret, build the white-listed page, record the client's consent.

The only door is the secret of the link. Nothing here takes an owner or an object id from the request: both come from the link row. The key
of the owner is put in force after the link is found, so the encrypted words of the object can be read. The journal row, the new state of the
estimate or the proposal and the commit are one step; two clients pressing at once cannot both win (the unique indexes decide).
"""
import hmac
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import client_link as rules
from app.domain.calendar.messages import language_of_telegram
from app.domain.documents.catalog import localize_description
from app.domain.documents.surface_names import surface_title_or_none
from app.domain.exceptions import DocumentDataError
from app.domain.services.calendar_service import CalendarService
from app.domain.services.client_link_service import aware
from app.domain.services.data_key_service import DataKeyService
from app.domain.services.estimate_service import EstimateService
from app.models.client_link import (
    ClientConsent,
    ClientLink,
    ClientProposal,
    ConsentKind,
    ProposalStatus,
)
from app.models.estimate import Estimate, EstimateStatus
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project
from app.models.user import User
from app.schemas.client_portal import (
    PortalConsent,
    PortalContractor,
    PortalEstimate,
    PortalLine,
    PortalLinkInfo,
    PortalPage,
    PortalProject,
    PortalProposal,
    PortalStatement,
)

READABLE = (EstimateStatus.FINAL, EstimateStatus.ACCEPTED)


def _polish(description: str) -> str:
    """The name of a work as the PDF of the estimate prints it (a built-in key becomes its Polish name); an unknown key is shown as it is."""
    try:
        return localize_description(description)
    except DocumentDataError:
        return description


class ClientPortalService:
    def __init__(self, db: AsyncSession, secret: str, web_app_url: str = "") -> None:
        self.db = db
        self.secret = secret
        self.web_app_url = web_app_url

    # -- the door ---------------------------------------------------------------------------------------------------------------

    async def resolve(self, token: str | None, *, now: datetime | None = None) -> ClientLink:
        """The link of a secret. Unknown: not found (always the same answer); revoked or expired: inactive."""
        if not rules.looks_like_token(token):
            raise rules.ClientLinkNotFoundError("no link")
        link = (await self.db.execute(select(ClientLink).where(ClientLink.token_hash == rules.hash_token(token or "")))).scalar_one_or_none()
        if link is None:
            raise rules.ClientLinkNotFoundError("no link")
        now = now or datetime.now(UTC)
        if link.revoked_at is not None or aware(link.expires_at) <= now:
            raise rules.LinkInactiveError("inactive")
        await DataKeyService(self.db).put_in_force(link.owner_id)
        return link

    # -- the page ---------------------------------------------------------------------------------------------------------------

    async def _contractor(self, owner_id: uuid.UUID) -> PortalContractor:
        profile = (await self.db.execute(select(ExecutorProfile).where(ExecutorProfile.owner_id == owner_id))).scalar_one_or_none()
        if profile is not None:
            return PortalContractor(name=profile.name, phone=profile.phone, email=profile.email, city=profile.city)
        user = (await self.db.execute(select(User).where(User.id == owner_id))).scalar_one_or_none()
        name = " ".join(part for part in (user.first_name, user.last_name) if part) if user is not None else ""
        return PortalContractor(name=name or None)

    async def _latest_estimate_id(self, link: ClientLink) -> uuid.UUID | None:
        return (
            await self.db.execute(
                select(Estimate.id)
                .where(Estimate.project_id == link.project_id, Estimate.owner_id == link.owner_id, Estimate.status.in_(READABLE))
                .order_by(Estimate.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    def _consent(row: ClientConsent | None) -> PortalConsent | None:
        if row is None:
            return None
        return PortalConsent(kind=row.kind, signer_name=row.signer_name, comment=row.comment, created_at=row.created_at)

    def _pair(self, key: str, lang: str, **values) -> PortalStatement:
        return PortalStatement(pl=rules.statement(key, "pl", **values), text=rules.statement(key, lang, **values))

    async def page(self, link: ClientLink, lang: str | None, *, now: datetime | None = None, touch: bool = False) -> PortalPage:
        lang = rules.clean_language(lang or link.language)
        now = now or datetime.now(UTC)
        project = (await self.db.execute(select(Project).where(Project.id == link.project_id, Project.owner_id == link.owner_id))).scalar_one()
        contractor = await self._contractor(link.owner_id)
        who = contractor.name or ""
        if touch:
            link.last_viewed_at = now
            link.view_count = (link.view_count or 0) + 1
            await self.db.commit()
            await self.db.refresh(link)

        estimate: PortalEstimate | None = None
        estimate_id = await self._latest_estimate_id(link)
        if estimate_id is not None:
            read = await EstimateService(self.db).get_estimate_read_with_provenance(link.project_id, estimate_id, link.owner_id)
            consent = (await self.db.execute(select(ClientConsent).where(ClientConsent.estimate_id == estimate_id))).scalar_one_or_none()
            status = read.status.value if hasattr(read.status, "value") else str(read.status)
            waiting = consent is None and status == EstimateStatus.FINAL.value
            estimate = PortalEstimate(
                id=read.id,
                version=read.version,
                status=status,
                name=read.name,
                currency=read.currency,
                total=read.total,
                vat_mode=read.vat_mode,
                vat_rate_percent=read.vat_rate_percent,
                vat_amount=read.vat_amount,
                gross_total=read.gross_total,
                hash=rules.estimate_hash(read),
                lines=[
                    PortalLine(
                        position=ln.position,
                        room_name=ln.room_name,
                        surface_name=surface_title_or_none(ln.surface_name),
                        description=_polish(ln.description),
                        unit=ln.unit.value if hasattr(ln.unit, "value") else str(ln.unit),
                        quantity=ln.quantity,
                        unit_price=ln.unit_price,
                        amount=ln.amount,
                    )
                    for ln in read.lines
                ],
                consent=self._consent(consent),
                accept_statement=self._pair(
                    "estimate_accept", lang, contractor=who, amount=rules.payable(read), currency=read.currency, version=read.version
                )
                if waiting
                else None,
                decline_statement=self._pair(
                    "estimate_decline", lang, contractor=who, amount=rules.payable(read), currency=read.currency, version=read.version
                )
                if waiting
                else None,
            )

        rows = list(
            (
                await self.db.execute(
                    select(ClientProposal)
                    .where(
                        ClientProposal.project_id == link.project_id,
                        ClientProposal.owner_id == link.owner_id,
                        ClientProposal.status != ProposalStatus.WITHDRAWN.value,
                    )
                    .order_by(ClientProposal.sequence)
                )
            ).scalars()
        )
        consents = {
            c.proposal_id: c
            for c in (
                await self.db.execute(
                    select(ClientConsent).where(ClientConsent.project_id == link.project_id, ClientConsent.proposal_id.is_not(None))
                )
            ).scalars()
        }
        proposals: list[PortalProposal] = []
        for p in rows:
            open_ = p.status == ProposalStatus.OPEN.value
            values = {"contractor": who, "amount": p.amount, "currency": p.currency, "title": p.title, "extra_days": p.extra_days}
            proposals.append(
                PortalProposal(
                    id=p.id,
                    sequence=p.sequence,
                    title=p.title,
                    description=p.description,
                    amount=p.amount,
                    currency=p.currency,
                    extra_days=p.extra_days,
                    status=p.status,
                    hash=p.content_hash,
                    created_at=p.created_at,
                    consent=self._consent(consents.get(p.id)),
                    accept_statement=self._pair("proposal_accept", lang, **values) if open_ else None,
                    decline_statement=self._pair("proposal_decline", lang, **values) if open_ else None,
                )
            )

        return PortalPage(
            link=PortalLinkInfo(expires_at=link.expires_at, language=link.language),
            lang=lang,
            contractor=contractor,
            project=PortalProject(name=project.name, address=project.address, city=project.city, postal_code=project.postal_code),
            estimate=estimate,
            proposals=proposals,
        )

    # -- the consent ------------------------------------------------------------------------------------------------------------

    def _consent_row(
        self, link: ClientLink, *, kind: ConsentKind, signer: str, ip: str, agent: str, now: datetime, comment: str | None = None, **subject
    ) -> ClientConsent:
        return ClientConsent(
            owner_id=link.owner_id,
            project_id=link.project_id,
            link_id=link.id,
            kind=kind.value,
            statement_lang="pl",
            signer_name=signer,
            comment=comment,
            ip_hash=rules.hash_value(self.secret, ip),
            agent_hash=rules.hash_value(self.secret, agent[:300]),
            created_at=now,
            **subject,
        )

    async def decide_estimate(
        self,
        link: ClientLink,
        *,
        estimate_id: uuid.UUID,
        version: int,
        seen_hash: str,
        decision: str,
        signer_name: str,
        agree: bool,
        comment: str | None,
        ip: str,
        agent: str,
        now: datetime | None = None,
    ) -> ClientConsent:
        """The client approves the estimate (it becomes ACCEPTED) or declines it (it stays as it is; the owner makes a new version). One decision per version."""
        now = now or datetime.now(UTC)
        accepted = decision == "ACCEPT"
        if not agree:
            raise rules.ClientLinkError("AGREE_REQUIRED", "tick the box to agree", "agree")
        signer = rules.clean_name(signer_name)
        reason = rules.clean_comment(comment)
        if reason is not None and accepted:
            raise rules.ClientLinkError("COMMENT_ONLY_ON_DECLINE", "a reason is written only with a refusal", "comment")
        latest = await self._latest_estimate_id(link)
        if latest is None or latest != estimate_id:
            raise rules.ClientLinkError("ESTIMATE_CHANGED", "the estimate was replaced: reload the page")
        estimate = (
            await self.db.execute(
                select(Estimate).where(Estimate.id == estimate_id, Estimate.project_id == link.project_id, Estimate.owner_id == link.owner_id)
            )
        ).scalar_one()
        done = (await self.db.execute(select(ClientConsent.id).where(ClientConsent.estimate_id == estimate_id))).scalar_one_or_none()
        if done is not None:
            raise rules.ClientLinkError("ALREADY_DECIDED", "this version of the estimate is already decided")
        if not accepted and estimate.status == EstimateStatus.ACCEPTED:
            raise rules.ClientLinkError("ESTIMATE_ALREADY_APPROVED", "the estimate is already approved in the contract")
        read = await EstimateService(self.db).get_estimate_read_with_provenance(link.project_id, estimate_id, link.owner_id)
        current = rules.estimate_hash(read)
        if read.version != version or not hmac.compare_digest(current, seen_hash.lower()):
            raise rules.ClientLinkError("ESTIMATE_CHANGED", "the estimate changed: reload the page")
        contractor = await self._contractor(link.owner_id)
        amount = rules.payable(read)
        text = rules.statement(
            "estimate_accept" if accepted else "estimate_decline",
            "pl",
            contractor=contractor.name or "",
            amount=amount,
            currency=read.currency,
            version=read.version,
        )
        consent = self._consent_row(
            link,
            kind=ConsentKind.ESTIMATE_ACCEPTED if accepted else ConsentKind.ESTIMATE_DECLINED,
            signer=signer,
            ip=ip,
            agent=agent,
            now=now,
            comment=reason,
            estimate_id=estimate_id,
            estimate_version=read.version,
            subject_hash=current,
            amount=amount,
            currency=read.currency,
            statement=text,
        )
        self.db.add(consent)
        if accepted:
            estimate.status = EstimateStatus.ACCEPTED
        await self._commit_once()
        return consent

    async def decide_proposal(
        self,
        link: ClientLink,
        proposal_id: uuid.UUID,
        *,
        decision: str,
        seen_hash: str,
        signer_name: str,
        agree: bool,
        comment: str | None = None,
        ip: str,
        agent: str,
        now: datetime | None = None,
    ) -> ClientConsent:
        now = now or datetime.now(UTC)
        if not agree:
            raise rules.ClientLinkError("AGREE_REQUIRED", "tick the box to agree", "agree")
        signer = rules.clean_name(signer_name)
        reason = rules.clean_comment(comment)
        if reason is not None and decision == "ACCEPT":
            raise rules.ClientLinkError("COMMENT_ONLY_ON_DECLINE", "a reason is written only with a refusal", "comment")
        proposal = (
            await self.db.execute(
                select(ClientProposal).where(
                    ClientProposal.id == proposal_id,
                    ClientProposal.project_id == link.project_id,
                    ClientProposal.owner_id == link.owner_id,
                )
            )
        ).scalar_one_or_none()
        if proposal is None or proposal.status == ProposalStatus.WITHDRAWN.value:
            raise rules.ClientLinkNotFoundError("no proposal")
        if proposal.status != ProposalStatus.OPEN.value:
            raise rules.ClientLinkError("ALREADY_DECIDED", "the proposal is already decided")
        if not hmac.compare_digest(proposal.content_hash, seen_hash.lower()):
            raise rules.ClientLinkError("PROPOSAL_CHANGED", "the proposal changed: reload the page")
        contractor = await self._contractor(link.owner_id)
        accepted = decision == "ACCEPT"
        text = rules.statement(
            "proposal_accept" if accepted else "proposal_decline",
            "pl",
            contractor=contractor.name or "",
            amount=proposal.amount,
            currency=proposal.currency,
            title=proposal.title,
            extra_days=proposal.extra_days,
        )
        consent = self._consent_row(
            link,
            kind=ConsentKind.PROPOSAL_ACCEPTED if accepted else ConsentKind.PROPOSAL_DECLINED,
            signer=signer,
            ip=ip,
            agent=agent,
            now=now,
            comment=reason,
            proposal_id=proposal.id,
            subject_hash=proposal.content_hash,
            amount=proposal.amount,
            currency=proposal.currency,
            statement=text,
        )
        self.db.add(consent)
        proposal.status = ProposalStatus.ACCEPTED.value if accepted else ProposalStatus.DECLINED.value
        proposal.decided_at = now
        await self._commit_once()
        return consent

    async def owner_notice(self, link: ClientLink, consent: ClientConsent) -> rules.OwnerNotice | None:
        """The message to the owner's Telegram chat about a consent just recorded: in the language the owner chose for the messages of the calendar
        (else that of their Telegram), with a button that opens the object. None when the owner has no Telegram chat (signs in with a password)."""
        user = (await self.db.execute(select(User).where(User.id == link.owner_id))).scalar_one_or_none()
        if user is None or user.telegram_user_id <= 0:
            return None
        prefs = await CalendarService(self.db).prefs(link.owner_id)
        lang = prefs.language or language_of_telegram(user.language_code)
        lang = rules.clean_language(lang)
        project = (await self.db.execute(select(Project).where(Project.id == link.project_id, Project.owner_id == link.owner_id))).scalar_one()
        amount = rules.amount_text(consent.amount, lang)
        values = {"client": consent.signer_name, "project": project.name, "amount": amount, "currency": consent.currency}
        if consent.kind in (ConsentKind.ESTIMATE_ACCEPTED.value, ConsentKind.ESTIMATE_DECLINED.value):
            key = "notice_estimate" if consent.kind == ConsentKind.ESTIMATE_ACCEPTED.value else "notice_estimate_declined"
            text = rules.owner_notice_text(key, lang, version=str(consent.estimate_version or ""), **values)
        else:
            proposal = (await self.db.execute(select(ClientProposal).where(ClientProposal.id == consent.proposal_id))).scalar_one()
            key = "notice_accept" if consent.kind == ConsentKind.PROPOSAL_ACCEPTED.value else "notice_decline"
            text = rules.owner_notice_text(key, lang, title=proposal.title, **values)
        if consent.comment:
            text += "\n" + rules.owner_notice_text("notice_comment", lang, comment=consent.comment)
        return rules.OwnerNotice(
            chat_id=user.telegram_user_id,
            text=text,
            open_url=rules.project_open_url(self.web_app_url, link.project_id),
            button_text=rules.texts()["notice_button"][lang],
        )

    async def _commit_once(self) -> None:
        try:
            await self.db.commit()
        except IntegrityError:  # two presses at once: the unique index let one through
            await self.db.rollback()
            raise rules.ClientLinkError("ALREADY_DECIDED", "this was already decided") from None
