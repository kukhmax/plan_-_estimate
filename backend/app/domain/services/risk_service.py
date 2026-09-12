import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.risk_rules import build_baseline_risk_rules
from app.domain.exceptions import (
    InspectionNotCompletedError,
    InspectionNotFoundError,
    ProjectNotFoundError,
    RiskNotFoundError,
    RoomNotFoundError,
)
from app.domain.rules.risk_rules import (
    RuleContext,
    compute_source_signature,
    derive_target_type,
    evaluate_rule,
)
from app.models.area_segment import AreaPlane
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from app.models.project import Project
from app.models.risk import Risk, RiskFinding, RiskRule, RiskRuleCondition
from app.models.room import Room

# Serializes concurrent first-call bootstraps within the process; the
# (code, version) unique constraint guarantees correctness even without it.
_bootstrap_lock = asyncio.Lock()


def _rule_keys(code: str) -> dict[str, str]:
    """The i18n key namespace snapshotted onto rules and their risks."""
    slug = code.lower()
    return {
        "title_key": f"risk.{slug}.title",
        "explanation_key": f"risk.{slug}.explanation",
        "consequence_key": f"risk.{slug}.consequence",
        "mitigation_key": f"risk.{slug}.mitigation",
        "communication_key": f"risk.{slug}.communication",
    }


class RiskService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_bootstrapped(self) -> None:
        """Materialize every missing baseline (code, version) rule exactly once."""
        async with _bootstrap_lock:
            existing_rows = (
                await self.db.execute(select(RiskRule.code, RiskRule.version))
            ).all()
            existing = {(row.code, row.version) for row in existing_rows}
            missing = [
                data
                for data in build_baseline_risk_rules()
                if (data.code, data.version) not in existing
            ]
            if not missing:
                return

            for data in missing:
                rule = RiskRule(
                    code=data.code,
                    version=data.version,
                    active=True,
                    severity=data.severity,
                    blocks_finishing=data.blocks_finishing,
                    warranty_exclusion_candidate=data.warranty_exclusion_candidate,
                    substrate=data.substrate,
                    **_rule_keys(data.code),
                )
                self.db.add(rule)
                await self.db.flush()
                for position, condition_data in enumerate(data.conditions):
                    self.db.add(
                        RiskRuleCondition(
                            rule_id=rule.id,
                            position=position,
                            operator=condition_data.operator,
                            finding_key=condition_data.finding_key,
                            value_json=condition_data.value,
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

    async def _load_active_rules(self) -> list[tuple[RiskRule, list[RiskRuleCondition]]]:
        """Active rules with conditions, using the highest version per code.

        Two bounded queries total; the (code, version) catalog keeps the active
        set small. Newly materialized risks snapshot the selected version.
        """
        rules = list(
            (
                await self.db.execute(
                    select(RiskRule).where(RiskRule.active.is_(True))
                )
            ).scalars().all()
        )
        by_code: dict[str, RiskRule] = {}
        for rule in rules:
            current = by_code.get(rule.code)
            if current is None or rule.version > current.version:
                by_code[rule.code] = rule
        selected = sorted(by_code.values(), key=lambda r: r.code)

        conditions_by_rule: dict[uuid.UUID, list[RiskRuleCondition]] = {
            rule.id: [] for rule in selected
        }
        selected_ids = [rule.id for rule in selected]
        if selected_ids:
            condition_rows = list(
                (
                    await self.db.execute(
                        select(RiskRuleCondition).where(
                            RiskRuleCondition.rule_id.in_(selected_ids)
                        )
                    )
                ).scalars().all()
            )
            for condition in condition_rows:
                conditions_by_rule[condition.rule_id].append(condition)
        return [
            (rule, sorted(conditions_by_rule[rule.id], key=lambda c: c.position))
            for rule in selected
        ]

    async def evaluate_risks(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[Risk]:
        """Evaluate one COMPLETED inspection and reconcile its risk rows.

        Deterministic and idempotent: identical inspection state yields
        identical rows with stable UUIDs. A non-COMPLETED inspection is
        rejected before any database change.
        """
        inspection = await self._get_inspection(
            project_id, room_id, inspection_id, owner_id
        )
        if inspection.status is not InspectionStatus.COMPLETED:
            raise InspectionNotCompletedError(
                "Risk evaluation requires a COMPLETED inspection"
            )
        await self._ensure_bootstrapped()

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
        findings_by_id: dict[uuid.UUID, InspectionFinding] = {}
        for finding in findings:
            findings_by_key.setdefault(finding.finding_key, []).append(finding)
            findings_by_id[finding.id] = finding

        ctx = RuleContext(
            substrate=inspection.substrate,
            quality_target=inspection.quality_target,
            target_type=derive_target_type(
                surface_id=inspection.surface_id,
                plane=inspection.plane,
            ),
            findings={
                key: tuple(value) for key, value in findings_by_key.items()
            },
        )

        evaluations = []
        for rule, conditions in await self._load_active_rules():
            source_ids = evaluate_rule(rule, conditions, ctx)
            if source_ids is not None:
                evaluations.append(
                    (rule, source_ids, compute_source_signature(source_ids))
                )

        await self._reconcile_risks(
            inspection.room_id, inspection.id, evaluations, findings_by_id
        )
        await self.db.commit()
        return await self._list_active_risks(inspection.id)

    async def _reconcile_risks(
        self,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        evaluations: list[tuple[RiskRule, tuple[uuid.UUID, ...], str]],
        findings_by_id: dict[uuid.UUID, InspectionFinding],
    ) -> None:
        """Create, reuse, or resolve risk rows for the current evaluation.

        Identity is (rule_code, source_signature): a reused row keeps its UUID
        and its original rule_version/text-key snapshot (version preservation),
        only refreshing activity state and source-finding links. Risks from a
        previous evaluation are resolved, never deleted.
        """
        existing = list(
            (
                await self.db.execute(
                    select(Risk).where(Risk.inspection_id == inspection_id)
                )
            ).scalars().all()
        )
        by_identity = {
            (risk.rule_code, risk.source_signature): risk for risk in existing
        }
        now = datetime.now(timezone.utc)
        seen: set[tuple[str, str]] = set()

        for position, (rule, source_ids, signature) in enumerate(evaluations):
            identity = (rule.code, signature)
            if identity in seen:
                continue
            seen.add(identity)

            risk = by_identity.get(identity)
            if risk is None:
                keys = _rule_keys(rule.code)
                risk = Risk(
                    room_id=room_id,
                    inspection_id=inspection_id,
                    risk_code=rule.code,
                    rule_code=rule.code,
                    rule_version=rule.version,
                    severity=rule.severity,
                    title_key=keys["title_key"],
                    explanation_key=keys["explanation_key"],
                    consequence_key=keys["consequence_key"],
                    mitigation_key=keys["mitigation_key"],
                    communication_key=keys["communication_key"],
                    warranty_exclusion_candidate=rule.warranty_exclusion_candidate,
                    blocks_finishing=rule.blocks_finishing,
                    source_signature=signature,
                    is_active=True,
                    position=position,
                )
                self.db.add(risk)
                await self.db.flush()
            else:
                # Version preservation: keep rule_version and the text-key
                # snapshot recorded at first materialization.
                risk.is_active = True
                risk.resolved_at = None
                risk.position = position

            await self._replace_risk_links(risk, source_ids, findings_by_id)

        for risk in existing:
            if (risk.rule_code, risk.source_signature) not in seen:
                risk.is_active = False
                risk.resolved_at = now

    async def _replace_risk_links(
        self,
        risk: Risk,
        source_ids: tuple[uuid.UUID, ...],
        findings_by_id: dict[uuid.UUID, InspectionFinding],
    ) -> None:
        """Replace the source-finding association with the current sources.

        Links are snapshots: they keep finding_key/value even if the source
        finding row is later removed (finding_id goes NULL via SET NULL).
        """
        await self.db.execute(
            delete(RiskFinding).where(RiskFinding.risk_id == risk.id)
        )
        await self.db.flush()
        for position, finding_id in enumerate(source_ids):
            finding = findings_by_id.get(finding_id)
            self.db.add(
                RiskFinding(
                    risk_id=risk.id,
                    finding_id=finding_id,
                    finding_key_snapshot=finding.finding_key if finding else "",
                    value_snapshot=finding.value_snapshot if finding else None,
                    position=position,
                )
            )

    async def _list_active_risks(
        self, inspection_id: uuid.UUID
    ) -> list[Risk]:
        stmt = (
            select(Risk)
            .where(
                Risk.inspection_id == inspection_id,
                Risk.is_active.is_(True),
            )
            .order_by(
                Risk.position.asc().nulls_last(),
                Risk.created_at.asc(),
                Risk.id.asc(),
            )
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_risks(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        inspection_id: uuid.UUID | None = None,
        surface_id: uuid.UUID | None = None,
        plane: AreaPlane | None = None,
        status: str = "active",
    ) -> tuple[list[Risk], int]:
        """List risks of a room, optionally narrowed to one inspection/target."""
        await self._ensure_room_owned(project_id, room_id, owner_id)
        await self._ensure_bootstrapped()

        stmt = select(Risk).where(Risk.room_id == room_id)
        if inspection_id is not None:
            stmt = stmt.where(Risk.inspection_id == inspection_id)
        if surface_id is not None or plane is not None:
            stmt = stmt.join(Inspection, Risk.inspection_id == Inspection.id)
            if surface_id is not None:
                stmt = stmt.where(Inspection.surface_id == surface_id)
            if plane is not None:
                stmt = stmt.where(Inspection.plane == plane)
        if status == "resolved":
            stmt = stmt.where(Risk.is_active.is_(False))
        elif status == "active":
            stmt = stmt.where(Risk.is_active.is_(True))

        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        items = list(
            (
                await self.db.execute(
                    stmt.order_by(
                        Risk.position.asc().nulls_last(),
                        Risk.created_at.asc(),
                        Risk.id.asc(),
                    )
                )
            ).scalars().all()
        )
        return items, total

    async def get_risk(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        risk_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Risk:
        """Fetch one risk of a room with its source findings attached."""
        await self._ensure_room_owned(project_id, room_id, owner_id)
        risk = (
            await self.db.execute(
                select(Risk).where(
                    Risk.id == risk_id,
                    Risk.room_id == room_id,
                )
            )
        ).scalar_one_or_none()
        if risk is None:
            raise RiskNotFoundError(f"Risk {risk_id} not found in room {room_id}")
        links = list(
            (
                await self.db.execute(
                    select(RiskFinding)
                    .where(RiskFinding.risk_id == risk.id)
                    .order_by(RiskFinding.position.asc().nulls_last())
                )
            ).scalars().all()
        )
        risk.source_findings = links
        return risk

    async def list_source_findings(
        self,
        risk_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[RiskFinding]]:
        """Grouped source-finding lookup so a risk batch never N+1s."""
        if not risk_ids:
            return {}
        rows = list(
            (
                await self.db.execute(
                    select(RiskFinding).where(RiskFinding.risk_id.in_(risk_ids))
                )
            ).scalars().all()
        )
        grouped: dict[uuid.UUID, list[RiskFinding]] = {}
        for row in rows:
            grouped.setdefault(row.risk_id, []).append(row)
        for links in grouped.values():
            links.sort(key=lambda link: (link.position is None, link.position))
        return grouped