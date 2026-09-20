"""Recommendation persistence foundation (Stage 11B.1).

Only the minimum internal helpers needed to materialize and look up a
`WorkRecommendation` deterministically. The public evaluation lifecycle
(reconciling every rule against a room's current active Risks/Findings,
listing, dismissing, reconsidering) is Stage 11B.2. This module never
mutates a `SurfaceWorkPlan` and never touches `Estimate`.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationRule,
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)


class WorkRecommendationService:
    """Persistence-level operations over `WorkRecommendation`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_identity(
        self,
        inspection_id: uuid.UUID,
        trigger_type: WorkRecommendationTriggerType,
        trigger_code: str,
        source_signature: str,
        recommended_work_code: str,
    ) -> WorkRecommendation | None:
        """Fetch a recommendation by its deterministic identity.

        Full identity: `(inspection_id, trigger_type, trigger_code,
        source_signature, recommended_work_code)`. `recommended_work_code`
        is part of the identity because `source_signature` identifies only
        the source evidence (a pure hash over finding UUIDs) and has no
        knowledge of which work is being suggested — one trigger firing can
        legitimately recommend several independent works, each its own row.
        `trigger_type` is included so a `RiskRule.code` and an
        `InspectionFinding.finding_key` can never accidentally collide into
        the same identity merely because the two independent vocabularies
        happen to share a string.
        """
        stmt = select(WorkRecommendation).where(
            WorkRecommendation.inspection_id == inspection_id,
            WorkRecommendation.trigger_type == trigger_type,
            WorkRecommendation.trigger_code == trigger_code,
            WorkRecommendation.source_signature == source_signature,
            WorkRecommendation.recommended_work_code == recommended_work_code,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def materialize_one(
        self,
        *,
        room_id: uuid.UUID,
        inspection_id: uuid.UUID,
        surface_id: uuid.UUID | None,
        target_kind: WorkRecommendationTargetKind,
        rule: WorkRecommendationRule,
        source_signature: str,
        risk_id: uuid.UUID | None = None,
        finding_id: uuid.UUID | None = None,
    ) -> WorkRecommendation:
        """Create, or reuse by identity, exactly one recommendation row.

        Mirrors `RiskService._reconcile_risks`'s single-row reconciliation:
        an existing row keeps its UUID and its owner-decided `status`
        (PENDING/ACCEPTED/DISMISSED are never touched here), only its
        `is_active`/`resolved_at` activity state is refreshed. Reconciling a
        whole room's rules against its current active Risks/Findings — and
        resolving rows no longer matched — is Stage 11B.2, not this method.
        """
        existing = await self.get_by_identity(
            inspection_id,
            rule.trigger_type,
            rule.trigger_code,
            source_signature,
            rule.recommended_work_code,
        )
        if existing is not None:
            existing.is_active = True
            existing.resolved_at = None
            await self.db.flush()
            return existing

        recommendation = WorkRecommendation(
            trigger_type=rule.trigger_type,
            trigger_code=rule.trigger_code,
            source_signature=source_signature,
            inspection_id=inspection_id,
            rule_id=rule.id,
            risk_id=risk_id,
            finding_id=finding_id,
            room_id=room_id,
            surface_id=surface_id,
            target_kind=target_kind,
            recommended_work_code=rule.recommended_work_code,
        )
        self.db.add(recommendation)
        await self.db.flush()
        return recommendation
