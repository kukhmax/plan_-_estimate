import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.communication_phrases import (
    build_baseline_communication_phrases,
    risk_phrase_code,
)
from app.domain.exceptions import (
    CommunicationNotFoundError,
    InspectionNotCompletedError,
    InspectionNotFoundError,
    ProjectNotFoundError,
    RoomNotFoundError,
)
from app.domain.rules.risk_rules import compute_source_signature
from app.models.communication import (
    CommunicationApplication,
    CommunicationPhrase,
)
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from app.models.project import Project
from app.models.risk import Risk, RiskFinding
from app.models.room import Room
from app.schemas.communication import (
    CommunicationFindingSnapshot,
    CommunicationFindingSource,
    CommunicationQualitySource,
    CommunicationRiskSource,
)
from app.schemas.risk import RiskSourceFindingRead

# Serializes concurrent first-call bootstraps within the process; the
# (code, version) unique constraint guarantees correctness even without it.
_bootstrap_lock = asyncio.Lock()

# Constant identity for context-only sources (quality phrases): the SHA-256 of
# the empty finding set. Distinct from any finding-derived signature because
# those always hash at least one finding UUID.
_EMPTY_SIGNATURE = compute_source_signature([])


class CommunicationService:
    """Deterministic, exact-key communication phrase engine (Stage 8).

    The engine consumes already-materialized facts — active Risk rows, active
    InspectionFinding rows, and the inspection substrate/quality target — and
    never recomputes Stage 7 rules. Selection is exact-key equality against the
    catalog; there is no condition graph and no generic evaluator.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_bootstrapped(self) -> None:
        """Materialize every missing baseline (code, version) phrase exactly once."""
        async with _bootstrap_lock:
            existing_rows = (
                await self.db.execute(
                    select(CommunicationPhrase.code, CommunicationPhrase.version)
                )
            ).all()
            existing = {(row.code, row.version) for row in existing_rows}
            missing = [
                data
                for data in build_baseline_communication_phrases()
                if (data.code, data.version) not in existing
            ]
            if not missing:
                return

            for data in missing:
                self.db.add(
                    CommunicationPhrase(
                        code=data.code,
                        version=data.version,
                        active=True,
                        category=data.category,
                        priority=data.priority,
                        risk_code=data.risk_code,
                        finding_key=data.finding_key,
                        substrate=data.substrate,
                        quality_level=data.quality_level,
                        phrase_key=data.phrase_key,
                        why_key=data.why_key,
                        seed_key=data.seed_key,
                    )
                )
            await self.db.commit()

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

    async def _load_active_phrases(self) -> list[CommunicationPhrase]:
        """Active phrase definitions at the highest version per code."""
        phrases = list(
            (
                await self.db.execute(
                    select(CommunicationPhrase).where(
                        CommunicationPhrase.active.is_(True)
                    )
                )
            ).scalars().all()
        )
        by_code: dict[str, CommunicationPhrase] = {}
        for phrase in phrases:
            current = by_code.get(phrase.code)
            if current is None or phrase.version > current.version:
                by_code[phrase.code] = phrase
        return [by_code[code] for code in sorted(by_code)]

    async def evaluate_communications(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[CommunicationApplication]:
        """Evaluate one COMPLETED inspection and reconcile its applications.

        Deterministic and idempotent: identical inspection state yields
        identical applications with stable UUIDs. A non-COMPLETED inspection is
        rejected before any database change.
        """
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        if inspection.status is not InspectionStatus.COMPLETED:
            raise InspectionNotCompletedError(
                "Communication evaluation requires a COMPLETED inspection"
            )
        await self._ensure_bootstrapped()
        phrases = await self._load_active_phrases()
        phrases_by_code = {phrase.code: phrase for phrase in phrases}

        findings = list(
            (
                await self.db.execute(
                    select(InspectionFinding).where(
                        InspectionFinding.inspection_id == inspection.id,
                        InspectionFinding.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )
        findings_by_key: dict[str, list[InspectionFinding]] = {}
        for finding in findings:
            findings_by_key.setdefault(finding.finding_key, []).append(finding)

        risks = list(
            (
                await self.db.execute(
                    select(Risk).where(
                        Risk.inspection_id == inspection.id,
                        Risk.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )

        # Findings already explained by an active risk are excluded from the
        # finding-only source so a covered finding never double-emits noise.
        covered_finding_ids = await self._covered_finding_ids(inspection.id)

        selections: list[
            tuple[CommunicationPhrase, str, str, uuid.UUID | None, str | None]
        ] = []

        # Source A — every materialized active risk with a catalogued phrase.
        for risk in risks:
            phrase = phrases_by_code.get(risk_phrase_code(risk.risk_code))
            if phrase is None:
                continue
            selections.append(
                (phrase, "RISK", risk.source_signature, risk.id, None)
            )

        # Source B — finding-only phrases for findings outside active risks.
        for key, key_findings in findings_by_key.items():
            uncovered = [
                finding for finding in key_findings
                if finding.id not in covered_finding_ids
            ]
            if not uncovered:
                continue
            candidates = [
                phrase
                for phrase in phrases
                if phrase.finding_key == key
                and (
                    phrase.substrate is None
                    or phrase.substrate == inspection.substrate
                )
                and (
                    phrase.quality_level is None
                    or (
                        inspection.quality_target is not None
                        and phrase.quality_level == inspection.quality_target
                    )
                )
            ]
            if not candidates:
                continue
            # Specificity precedence finding+substrate+quality > finding+substrate
            # > finding+quality > finding; a full (substrate, quality) match wins
            # over a partial one, ties break by priority then code.
            phrase = min(
                candidates,
                key=lambda p: (
                    (p.substrate is None),
                    (p.quality_level is None),
                    p.priority,
                    p.code,
                ),
            )
            signature = compute_source_signature(
                tuple(finding.id for finding in sorted(uncovered, key=lambda f: f.id))
            )
            selections.append((phrase, "FINDING", signature, None, key))

        # Source C — explicit substrate + quality target expectation.
        if inspection.quality_target is not None:
            quality = next(
                (
                    phrase
                    for phrase in phrases
                    if phrase.risk_code is None
                    and phrase.finding_key is None
                    and phrase.substrate == inspection.substrate
                    and phrase.quality_level == inspection.quality_target
                ),
                None,
            )
            if quality is not None:
                selections.append((quality, "QUALITY", _EMPTY_SIGNATURE, None, None))

        await self._reconcile_applications(inspection.id, selections)
        await self.db.commit()
        return await self._list_active_applications(inspection.id)

    async def _covered_finding_ids(self, inspection_id: uuid.UUID) -> set[uuid.UUID]:
        rows = list(
            (
                await self.db.execute(
                    select(RiskFinding.finding_id)
                    .join(Risk, RiskFinding.risk_id == Risk.id)
                    .where(
                        Risk.inspection_id == inspection_id,
                        Risk.is_active.is_(True),
                        RiskFinding.finding_id.is_not(None),
                    )
                )
            ).scalars().all()
        )
        return {row for row in rows if row is not None}

    async def _reconcile_applications(
        self,
        inspection_id: uuid.UUID,
        selections: list[
            tuple[CommunicationPhrase, str, str, uuid.UUID | None, str | None]
        ],
    ) -> None:
        """Create, reuse, or resolve applications for the current evaluation.

        Identity is (phrase_code, source_signature): a reused application keeps
        its UUID and its original phrase_version/text-key snapshot (version
        preservation), only refreshing activity state. Applications from a
        previous evaluation are resolved, never deleted.
        """
        existing = list(
            (
                await self.db.execute(
                    select(CommunicationApplication).where(
                        CommunicationApplication.inspection_id == inspection_id
                    )
                )
            ).scalars().all()
        )
        by_identity = {
            (app.phrase_code, app.source_signature): app for app in existing
        }
        now = datetime.now(timezone.utc)
        seen: set[tuple[str, str]] = set()

        for position, (
            phrase,
            source_kind,
            signature,
            risk_id,
            finding_key,
        ) in enumerate(selections):
            identity = (phrase.code, signature)
            if identity in seen:
                continue
            seen.add(identity)

            app = by_identity.get(identity)
            if app is None:
                app = CommunicationApplication(
                    inspection_id=inspection_id,
                    phrase_code=phrase.code,
                    phrase_version=phrase.version,
                    category=phrase.category,
                    priority=phrase.priority,
                    phrase_key=phrase.phrase_key,
                    why_key=phrase.why_key,
                    seed_key=phrase.seed_key,
                    source_kind=source_kind,
                    source_signature=signature,
                    risk_id=risk_id,
                    finding_key_snapshot=finding_key,
                    is_active=True,
                    position=position,
                )
                self.db.add(app)
            else:
                # Version preservation: keep phrase_version and the catalog
                # snapshot recorded at first materialization.
                app.is_active = True
                app.resolved_at = None
                app.position = position
                app.risk_id = risk_id
                app.finding_key_snapshot = finding_key

        for app in existing:
            if (app.phrase_code, app.source_signature) not in seen:
                app.is_active = False
                app.resolved_at = now

    async def _list_active_applications(
        self, inspection_id: uuid.UUID
    ) -> list[CommunicationApplication]:
        stmt = (
            select(CommunicationApplication)
            .where(
                CommunicationApplication.inspection_id == inspection_id,
                CommunicationApplication.is_active.is_(True),
            )
            .order_by(
                CommunicationApplication.position.asc().nulls_last(),
                CommunicationApplication.created_at.asc(),
                CommunicationApplication.id.asc(),
            )
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_applications(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        inspection_id: uuid.UUID,
        status: str = "active",
    ) -> tuple[list[CommunicationApplication], int]:
        """List the applications of one inspection, optionally by status."""
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        stmt = select(CommunicationApplication).where(
            CommunicationApplication.inspection_id == inspection.id
        )
        if status == "resolved":
            stmt = stmt.where(CommunicationApplication.is_active.is_(False))
        elif status == "active":
            stmt = stmt.where(CommunicationApplication.is_active.is_(True))

        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        items = list(
            (
                await self.db.execute(
                    stmt.order_by(
                        CommunicationApplication.position.asc().nulls_last(),
                        CommunicationApplication.created_at.asc(),
                        CommunicationApplication.id.asc(),
                    )
                )
            ).scalars().all()
        )
        return items, total

    async def get_application(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        application_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> CommunicationApplication:
        """Fetch one application of the given inspection inside the owned room."""
        await self._ensure_room_owned(project_id, room_id, owner_id)
        app = (
            await self.db.execute(
                select(CommunicationApplication)
                .join(
                    Inspection,
                    CommunicationApplication.inspection_id == Inspection.id,
                )
                .where(
                    CommunicationApplication.id == application_id,
                    CommunicationApplication.inspection_id == inspection_id,
                    Inspection.room_id == room_id,
                )
            )
        ).scalar_one_or_none()
        if app is None:
            raise CommunicationNotFoundError(
                f"Communication application {application_id} "
                f"not found in room {room_id}"
            )
        return app

    async def build_source(
        self,
        application: CommunicationApplication,
    ) -> (
        CommunicationRiskSource
        | CommunicationFindingSource
        | CommunicationQualitySource
    ):
        """Assemble the traceability source without recomputing any rule.

        RISK: the materialized risk context plus Stage 7 source-finding snapshots.
        FINDING: matching inspection finding label/value snapshots.
        QUALITY: the inspection substrate and quality target.
        Only keys and snapshots recorded by Stages 6/7 are surfaced; nothing is
        re-derived from rules.
        """
        if application.source_kind == "RISK":
            risk = None
            source_findings: list[RiskSourceFindingRead] = []
            if application.risk_id is not None:
                risk = (
                    await self.db.execute(
                        select(Risk).where(Risk.id == application.risk_id)
                    )
                ).scalar_one_or_none()
            if risk is not None:
                links = list(
                    (
                        await self.db.execute(
                            select(RiskFinding)
                            .where(RiskFinding.risk_id == risk.id)
                            .order_by(RiskFinding.position.asc().nulls_last())
                        )
                    ).scalars().all()
                )
                source_findings = [
                    RiskSourceFindingRead.model_validate(link) for link in links
                ]
            return CommunicationRiskSource(
                risk_id=risk.id if risk else None,
                risk_code=risk.risk_code if risk else None,
                severity=risk.severity if risk else None,
                risk_is_active=risk.is_active if risk else None,
                source_findings=source_findings,
            )

        if application.source_kind == "FINDING":
            findings = list(
                (
                    await self.db.execute(
                        select(InspectionFinding)
                        .where(
                            InspectionFinding.inspection_id
                            == application.inspection_id,
                            InspectionFinding.finding_key
                            == application.finding_key_snapshot,
                        )
                        .order_by(InspectionFinding.position.asc().nulls_last())
                    )
                ).scalars().all()
            )
            return CommunicationFindingSource(
                finding_key=application.finding_key_snapshot or "",
                findings=[
                    CommunicationFindingSnapshot(
                        finding_id=finding.id,
                        label_key=finding.label_key,
                        value_snapshot=finding.value_snapshot,
                        is_active=finding.is_active,
                        position=finding.position,
                    )
                    for finding in findings
                ],
            )

        inspection = (
            await self.db.execute(
                select(Inspection).where(Inspection.id == application.inspection_id)
            )
        ).scalar_one_or_none()
        return CommunicationQualitySource(
            substrate=inspection.substrate if inspection else None,
            quality_level=inspection.quality_target if inspection else None,
        )