"""Issuing a client document and sending it to the owner (Stage 15F.2).

`start_*` checks everything that is cheap and can be wrong -- the owner's data, the state of the estimate, the executor
profile, the photo limit -- in the request, so a mistake is answered at once; then it takes the numbers (the journal row is
PENDING) and starts the slow part -- the picture of the document and its delivery -- as a background task of this process.
The task opens its own database session, always ends the journal row (SENT or FAILED with a stable code) and never lets an
error vanish: an unexpected one is logged and recorded as INTERNAL_ERROR.

One render at a time is the renderer's own rule (the server has one core); at most `max_active` documents may be queued
here, more are refused with DOCUMENT_QUEUE_FULL before a number is taken. A server restart ends the tasks: the rows they
left PENDING become FAILED / INTERRUPTED by the journal after its TTL.
"""

import asyncio
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.contracts.answers import effective_answers
from app.domain.contracts.catalog import load_contract_catalog
from app.domain.contracts.gate import load_gate_data
from app.domain.documents import formatting
from app.domain.documents.contract_document import build_contract_document, render_contract_html, snapshot_of
from app.domain.documents.delivery import DocumentDelivery
from app.domain.documents.handover_document import build_handover_document, render_handover_html
from app.domain.documents.handover_document import snapshot_of as handover_snapshot_of
from app.domain.documents.estimate_document import EstimateDocumentService
from app.domain.documents.photo_report_document import PhotoReportDocumentService
from app.domain.documents.production_plan_document import ProductionPlanDocumentService
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.tech_card_document import TechCardDocumentService
from app.domain.exceptions import (
    ContractGateError,
    ContractNotEditableError,
    DocumentDataError,
    DocumentDeliveryError,
    DocumentQueueFullError,
    DocumentRenderError,
    HandoverGateError,
    HandoverNotEditableError,
    IssuedDocumentNotFoundError,
)
from app.domain.protocols.sources import load_handover_sources
from app.domain.services.contract_service import ContractService
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.domain.services.handover_service import HandoverService, _data as handover_data
from app.domain.services.issued_document_service import (
    IssuedDocumentService,
    Reservation,
)
from app.domain.services.media_storage import MediaStorage
from app.models.contract import Contract
from app.models.handover_protocol import HandoverProtocol
from app.models.issued_document import IssuedDocument, IssuedDocumentKind
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class PreviewResult:
    pages: int
    byte_size: int


def pdf_filename(number: str) -> str:
    """`KOSZ/2026/10/08/1953-2` -> `KOSZ-2026-10-08-1953-2.pdf`: safe on every phone and file system."""
    return _UNSAFE_FILENAME.sub("-", number).strip("-.") + ".pdf"


class DocumentIssuer:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        renderer: DocumentRenderer,
        delivery: DocumentDelivery,
        storage: Callable[[], MediaStorage],
        storage_name: str,
        max_photos: int,
        max_active: int = 3,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_factory = session_factory
        self.renderer = renderer
        self.delivery = delivery
        self.storage = storage
        self.storage_name = storage_name
        self.max_photos = max_photos
        self.max_active = max_active
        self.clock = clock
        self._tasks: set[asyncio.Task] = set()

    @property
    def active(self) -> int:
        return len(self._tasks)

    async def drain(self) -> None:
        """Wait for every running document (shutdown and tests)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # -- starting -----------------------------------------------------------------------------------------------------------------

    async def start_estimate(self, db: AsyncSession, user: User, project_id: uuid.UUID, estimate_id: uuid.UUID) -> Reservation:
        self._ensure_capacity()
        owner_id = user.id
        document = await EstimateDocumentService(db).build(project_id, estimate_id, owner_id, issued_on=self._today())
        if document.layout.draft:
            raise DocumentDataError("ESTIMATE_NOT_FINAL", "only a finished (FINAL or ACCEPTED) estimate is issued; a draft can only be previewed")
        project = await self._project(db, owner_id, project_id)
        title = f"Kosztorys — {document.name}" if document.name else f"Kosztorys — wersja {document.version}"
        reservation = await IssuedDocumentService(db, clock=self.clock).reserve(
            owner_id,
            project_id,
            IssuedDocumentKind.ESTIMATE,
            title=title,
            template_version=get_template(DocumentKind.ESTIMATE).version,
            source_id=estimate_id,
            source_version=document.version,
            client_id=project.client_id,
        )
        return self._launch(reservation)

    async def start_photo_report(
        self,
        db: AsyncSession,
        user: User,
        project_id: uuid.UUID,
        *,
        room_ids: frozenset[uuid.UUID] | None = None,
        include_project_photos: bool | None = None,
    ) -> Reservation:
        self._ensure_capacity()
        owner_id = user.id
        service = self._photo_service(db)
        project, details, _, _ = await service.prepare(
            owner_id, project_id, room_ids=room_ids, include_project_photos=include_project_photos
        )
        if await ExecutorProfileService(db).get(owner_id) is None:
            raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a photo report")
        scope = None
        title = "Raport fotograficzny"
        if room_ids is not None:
            names = [room.name for room in details.rooms if room.room_id in room_ids]
            scope = {
                "room_ids": sorted(str(room_id) for room_id in room_ids),
                "include_project_photos": bool(include_project_photos),
            }
            title = f"Raport fotograficzny (część: {', '.join(names)})"
        reservation = await IssuedDocumentService(db, clock=self.clock).reserve(
            owner_id,
            project_id,
            IssuedDocumentKind.PHOTO_REPORT,
            title=title,
            template_version=get_template(DocumentKind.PHOTO_REPORT).version,
            client_id=project.client_id,
            scope=scope,
        )
        return self._launch(reservation)

    async def start_tech_card(self, db: AsyncSession, user: User, project_id: uuid.UUID) -> Reservation:
        """A numbered technological card. The data are checked now (the card is refused with a stable code while a surface
        with works lacks its agreed standard or a finished inspection), so a number is never given to a card that cannot
        be made; the slow part runs in the background like the other documents."""
        self._ensure_capacity()
        owner_id = user.id
        document = await TechCardDocumentService(db).build(owner_id, project_id, working=False, issued_on=self._today())
        project = await self._project(db, owner_id, project_id)
        reservation = await IssuedDocumentService(db, clock=self.clock).reserve(
            owner_id,
            project_id,
            IssuedDocumentKind.TECH_CARD,
            title=document.layout.meta.title,
            template_version=get_template(DocumentKind.TECH_CARD).version,
            client_id=project.client_id,
        )
        return self._launch(reservation)

    async def preview_tech_card(self, db: AsyncSession, user: User, project_id: uuid.UUID) -> PreviewResult:
        """The working version of the card (watermark, no number, no journal row) to the owner's chat. It never refuses for
        missing data: what is not there yet prints as an empty line to write in, so the owner can print it and talk it
        through with the customer before the inspection is done."""
        owner_id, chat_id = user.id, user.telegram_user_id  # read once: a rollback below would expire the object
        document = await TechCardDocumentService(db).build(owner_id, project_id, working=True, issued_on=self._today())
        project = await self._project(db, owner_id, project_id)
        rendered = await self.renderer.render(TechCardDocumentService.html(document))
        await self.delivery.send_document(
            chat_id,
            "Karta-technologiczna-wersja-robocza.pdf",
            rendered.pdf,
            f"WERSJA ROBOCZA — Karta technologiczna — {project.name}",
        )
        return PreviewResult(rendered.pages, rendered.byte_size)

    async def start_production_plan(self, db: AsyncSession, user: User, project_id: uuid.UUID) -> Reservation:
        """A numbered production plan: checked now (refused with a stable code while no surface has a planned work), so a number
        is never given to a plan that cannot be made; the slow part runs in the background like the other documents."""
        self._ensure_capacity()
        owner_id = user.id
        document = await ProductionPlanDocumentService(db).build(owner_id, project_id, working=False, issued_on=self._today())
        project = await self._project(db, owner_id, project_id)
        reservation = await IssuedDocumentService(db, clock=self.clock).reserve(
            owner_id,
            project_id,
            IssuedDocumentKind.PRODUCTION_PLAN,
            title=document.layout.meta.title,
            template_version=get_template(DocumentKind.PRODUCTION_PLAN).version,
            client_id=project.client_id,
        )
        return self._launch(reservation)

    async def preview_production_plan(self, db: AsyncSession, user: User, project_id: uuid.UUID) -> PreviewResult:
        """The working version of the plan (pale watermark, no number, no journal row) to the owner's chat; it never refuses for
        missing data -- what is not there prints as an empty line to write in."""
        owner_id, chat_id = user.id, user.telegram_user_id  # read once: a rollback below would expire the object
        document = await ProductionPlanDocumentService(db).build(owner_id, project_id, working=True, issued_on=self._today())
        project = await self._project(db, owner_id, project_id)
        rendered = await self.renderer.render(ProductionPlanDocumentService.html(document))
        await self.delivery.send_document(
            chat_id,
            "Plan-produkcji-prac-wersja-robocza.pdf",
            rendered.pdf,
            f"WERSJA ROBOCZA — Plan produkcji prac — {project.name}",
        )
        return PreviewResult(rendered.pages, rendered.byte_size)

    async def start_contract(self, db: AsyncSession, user: User, project_id: uuid.UUID, contract_id: uuid.UUID) -> Reservation:
        """Issue a draft of the contract: the gate first (a refusal lists what to fix and takes no number), then the number, then
        the freeze -- the conditions, the exact page and the estimate that priced it -- and the slow part (the PDF and its delivery)
        in the background."""
        self._ensure_capacity()
        owner_id = user.id
        service = ContractService(db)
        contract, data, blockers = await service.gate(project_id, contract_id, owner_id)
        if contract.status != "DRAFT":
            raise ContractNotEditableError(f"contract {contract_id} is {contract.status}: only a draft is issued")
        if blockers:
            raise ContractGateError(blockers)
        effective = effective_answers(contract.answers or {}, load_contract_catalog())
        build_contract_document(contract, effective, data, working=False, issued_on=self._today())  # a refusal here takes no number
        project = await self._project(db, owner_id, project_id)
        reservation = await IssuedDocumentService(db, clock=self.clock).reserve(
            owner_id,
            project_id,
            IssuedDocumentKind.CONTRACT,
            title=f"Umowa — wersja {contract.version}",
            template_version=get_template(DocumentKind.CONTRACT).version,
            source_id=contract.id,
            source_version=contract.version,
            client_id=project.client_id,
        )
        if reservation.reused:
            return reservation
        try:
            document = build_contract_document(
                contract, effective, data, working=False, issued_on=self._today(),
                number=reservation.document.number, sequence=reservation.document.project_seq,
            )
            await service.mark_issued(
                project_id, contract.id, owner_id,
                issued_at=self.clock(),
                snapshot=snapshot_of(contract, effective, data, document),
                document_html=render_contract_html(document),
                estimate_id=data.estimate.id if data.estimate else None,
                estimate_version=data.estimate.version if data.estimate else None,
            )
        except Exception:
            logger.exception("freezing contract %s failed", contract_id)
            await db.rollback()
            await IssuedDocumentService(db, clock=self.clock).mark_failed(owner_id, reservation.document.id, "INTERNAL_ERROR")
            raise
        await db.refresh(reservation.document)  # the freeze committed: the journal row is read again, not left expired
        return self._launch(reservation)

    async def preview_contract(self, db: AsyncSession, user: User, project_id: uuid.UUID) -> PreviewResult:
        """The working version of the contract with its annexes (pale watermark, no number, no journal row) to the owner's chat.
        It never refuses for missing data: whatever is not answered yet is an empty line to write in. It follows the open draft's
        answers, or is a blank form when there is none."""
        owner_id, chat_id = user.id, user.telegram_user_id  # read once: a rollback below would expire the object
        service = ContractService(db)
        data = await load_gate_data(db, owner_id, project_id)
        drafts = [c for c in await service.list(project_id, owner_id) if c.status == "DRAFT"]
        effective = effective_answers(drafts[0].answers or {}, load_contract_catalog()) if drafts else {}
        document = build_contract_document(drafts[0] if drafts else None, effective, data, working=True, issued_on=self._today())
        project = await self._project(db, owner_id, project_id)
        rendered = await self.renderer.render(render_contract_html(document))
        await self.delivery.send_document(
            chat_id,
            "Umowa-wersja-robocza.pdf",
            rendered.pdf,
            f"WERSJA ROBOCZA — Umowa — {project.name}",
        )
        return PreviewResult(rendered.pages, rendered.byte_size)

    async def start_handover(self, db: AsyncSession, user: User, project_id: uuid.UUID, handover_id: uuid.UUID) -> Reservation:
        """Issue a draft of the handover protocol: the gate first (a refusal lists what to fix and takes no number), then the number,
        then the freeze -- what was found, the exact page and the contract it was made under -- and the slow part (the PDF and its
        delivery) in the background."""
        self._ensure_capacity()
        owner_id = user.id
        service = HandoverService(db)
        row, sources, blockers = await service.gate(project_id, handover_id, owner_id)
        if row.status != "DRAFT":
            raise HandoverNotEditableError(f"handover protocol {handover_id} is {row.status}: only a draft is issued")
        if blockers:
            raise HandoverGateError(blockers)
        data = handover_data(row)
        build_handover_document(data, sources, working=False, issued_on=self._today())  # a refusal here takes no number
        reservation = await IssuedDocumentService(db, clock=self.clock).reserve(
            owner_id,
            project_id,
            IssuedDocumentKind.HANDOVER_PROTOCOL,
            title=f"Protokół przekazania pomieszczeń — nr {row.sequence}",
            template_version=get_template(DocumentKind.HANDOVER_PROTOCOL).version,
            source_id=row.id,
            source_version=row.sequence,
            client_id=sources.project.client_id,
        )
        if reservation.reused:
            return reservation
        try:
            document = build_handover_document(
                data, sources, working=False, issued_on=self._today(),
                number=reservation.document.number, sequence=reservation.document.project_seq,
            )
            await service.mark_issued(
                project_id, row.id, owner_id,
                issued_at=self.clock(),
                snapshot=handover_snapshot_of(data, sources, document),
                document_html=render_handover_html(document),
                contract_id=sources.contract.id if sources.contract else None,
                contract_version=sources.contract.version if sources.contract else None,
            )
        except Exception:
            logger.exception("freezing handover protocol %s failed", handover_id)
            await db.rollback()
            await IssuedDocumentService(db, clock=self.clock).mark_failed(owner_id, reservation.document.id, "INTERNAL_ERROR")
            raise
        await db.refresh(reservation.document)  # the freeze committed: the journal row is read again, not left expired
        return self._launch(reservation)

    async def preview_handover(self, db: AsyncSession, user: User, project_id: uuid.UUID) -> PreviewResult:
        """The working version of the protocol (pale watermark, no number, no journal row) to the owner's chat, to print and fill in
        on the premises. It never refuses for missing data; it follows the open draft, or is a blank form when there is none."""
        owner_id, chat_id = user.id, user.telegram_user_id  # read once: a rollback below would expire the object
        sources = await load_handover_sources(db, owner_id, project_id)
        drafts = [r for r in await HandoverService(db).list(project_id, owner_id) if r.status == "DRAFT"]
        data = handover_data(drafts[0]) if drafts else {}
        document = build_handover_document(data, sources, working=True, issued_on=self._today())
        rendered = await self.renderer.render(render_handover_html(document))
        await self.delivery.send_document(
            chat_id,
            "Protokol-przekazania-wersja-robocza.pdf",
            rendered.pdf,
            f"WERSJA ROBOCZA — Protokół przekazania pomieszczeń — {sources.project.name}",
        )
        return PreviewResult(rendered.pages, rendered.byte_size)

    async def preview_estimate(self, db: AsyncSession, user: User, project_id: uuid.UUID, estimate_id: uuid.UUID) -> PreviewResult:
        """A working version of an unfinished estimate to the owner's chat: watermark, no number, no journal row. The slow
        part runs in the request (a one-page document), so the owner sees at once whether it arrived."""
        owner_id, chat_id = user.id, user.telegram_user_id  # read once: a rollback below would expire the object
        document = await EstimateDocumentService(db).build(project_id, estimate_id, owner_id, issued_on=self._today())
        if not document.layout.draft:
            raise DocumentDataError("PREVIEW_ONLY_FOR_DRAFT", "a finished estimate is issued, not previewed")
        project = await self._project(db, owner_id, project_id)
        rendered = await self.renderer.render(EstimateDocumentService.html(document))
        await self.delivery.send_document(
            chat_id,
            f"Kosztorys-wersja-robocza-{document.version}.pdf",
            rendered.pdf,
            f"WERSJA ROBOCZA — Kosztorys — {project.name}",
        )
        return PreviewResult(rendered.pages, rendered.byte_size)

    # -- the slow part ---------------------------------------------------------------------------------------------------------------

    def _launch(self, reservation: Reservation) -> Reservation:
        if not reservation.reused:
            document = reservation.document
            task = asyncio.get_running_loop().create_task(self._run(document.owner_id, document.project_id, document.id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return reservation

    async def _run(self, owner_id: uuid.UUID, project_id: uuid.UUID, document_id: uuid.UUID) -> None:
        code = "INTERNAL_ERROR"
        try:
            async with self.session_factory() as db:
                journal = IssuedDocumentService(db, clock=self.clock)
                try:
                    document = await journal.get(owner_id, project_id, document_id)
                    user = (await db.execute(select(User).where(User.id == owner_id))).scalar_one()
                    project = await self._project(db, owner_id, project_id)
                    rendered = await self._render(db, document)
                    await self.delivery.send_document(
                        user.telegram_user_id, pdf_filename(document.number), rendered.pdf, f"{document.title} — {project.name}\n{document.number}"
                    )
                    await journal.mark_sent(
                        owner_id, document_id, pages=rendered.pages, byte_size=rendered.byte_size, sha256=rendered.sha256
                    )
                    return
                except DocumentDeliveryError as exc:
                    code = exc.code
                except DocumentDataError as exc:
                    code = exc.reason
                except DocumentRenderError as exc:
                    code = exc.code
                except IssuedDocumentNotFoundError:
                    logger.error("issued document %s vanished before it was made", document_id)
                    return
                except asyncio.CancelledError:
                    await asyncio.shield(self._end(journal, owner_id, document_id, "INTERRUPTED"))
                    raise
                except Exception:
                    logger.exception("issuing document %s failed", document_id)
                await self._end(journal, owner_id, document_id, code)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("could not record the end of document %s", document_id)

    @staticmethod
    async def _end(journal: IssuedDocumentService, owner_id: uuid.UUID, document_id: uuid.UUID, code: str) -> None:
        await journal.db.rollback()
        await journal.mark_failed(owner_id, document_id, code)

    async def _render(self, db: AsyncSession, document: IssuedDocument) -> RenderedPdf:
        issued_on = formatting.local_datetime(document.issued_at).date()
        if document.kind == IssuedDocumentKind.ESTIMATE.value:
            return await EstimateDocumentService(db).render(
                document.project_id, document.source_id, document.owner_id, self.renderer,
                issued_on=issued_on, number=document.number, sequence=document.project_seq,
            )
        if document.kind == IssuedDocumentKind.CONTRACT.value:
            contract = (await db.execute(select(Contract).where(Contract.id == document.source_id, Contract.owner_id == document.owner_id))).scalar_one_or_none()
            if contract is None or not contract.document_html:
                raise DocumentDataError("CONTRACT_NOT_ISSUED", "the contract of this document is not frozen")
            return await self.renderer.render(contract.document_html)
        if document.kind == IssuedDocumentKind.HANDOVER_PROTOCOL.value:
            protocol = (
                await db.execute(select(HandoverProtocol).where(HandoverProtocol.id == document.source_id, HandoverProtocol.owner_id == document.owner_id))
            ).scalar_one_or_none()
            if protocol is None or not protocol.document_html:
                raise DocumentDataError("HANDOVER_NOT_ISSUED", "the protocol of this document is not frozen")
            return await self.renderer.render(protocol.document_html)
        if document.kind == IssuedDocumentKind.PRODUCTION_PLAN.value:
            return await ProductionPlanDocumentService(db).render(
                document.owner_id, document.project_id, self.renderer,
                working=False, issued_on=issued_on, number=document.number, sequence=document.project_seq,
            )
        if document.kind == IssuedDocumentKind.TECH_CARD.value:
            return await TechCardDocumentService(db).render(
                document.owner_id, document.project_id, self.renderer,
                working=False, issued_on=issued_on, number=document.number, sequence=document.project_seq,
            )
        scope = document.scope or {}
        room_ids = frozenset(uuid.UUID(value) for value in scope["room_ids"]) if scope.get("room_ids") is not None else None
        return await self._photo_service(db).render(
            document.owner_id, document.project_id, self.renderer,
            issued_on=issued_on, number=document.number, sequence=document.project_seq,
            room_ids=room_ids, include_project_photos=scope.get("include_project_photos"),
        )

    # -- helpers --------------------------------------------------------------------------------------------------------------------------

    def _photo_service(self, db: AsyncSession) -> PhotoReportDocumentService:
        return PhotoReportDocumentService(db, self.storage(), storage_name=self.storage_name, max_photos=self.max_photos)

    def _ensure_capacity(self) -> None:
        if self.active >= self.max_active:
            raise DocumentQueueFullError("too many documents are being made at once")

    def _today(self) -> date:
        return formatting.local_datetime(self.clock()).date()

    @staticmethod
    async def _project(db: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        return (await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one()
