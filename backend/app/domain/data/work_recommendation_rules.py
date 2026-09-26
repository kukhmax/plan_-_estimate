"""Idempotent baseline data for the `WorkRecommendationRule` catalog
(Stage 11B.1.1).

Stage 11B.1 created `work_recommendation_rules` as an empty table with no
seed data. Manual Stage 11D.2 acceptance confirmed this makes every real
"Oceń zalecenia" evaluation return zero recommendations regardless of which
risks/findings actually fired -- a genuine catalog gap, not a runtime defect
(see docs/development-progress.md Stage 11B.1.1 entry for the full
diagnosis).

This module lists only OWNER-APPROVED, HIGH-confidence mappings: an existing
Stage 7 `RiskRule.code` (`app/domain/data/risk_rules.py`) whose title,
mitigation text, and the actually-fired production risk it produces are a
direct semantic match for one already-existing `PriceItem.code` in the
canonical seed catalog (`app/domain/data/price_book_seed.py`) -- verified
against that catalog's own PL locale descriptions, not merely code-name
pattern matching. It deliberately does NOT include every plausible mapping
found while auditing all 15 baseline Stage 7 risk rules; several additional
HIGH-confidence candidates exist (e.g. `OILY_SUBSTRATE_DEGREASE` ->
`CENNIK_PREP_DEGR-01`, `MOLD_TREATMENT_BEFORE_FINISH` -> `CENNIK_PREP_MOLD-01`,
`JOINT_TAPE_MISSING_REWORK` -> `CENNIK_GK_JOINT-01`) but were left out of
this pass pending explicit owner approval, exactly like several MEDIUM/NONE
candidates (compound multi-step mitigations with no single matching
PriceItem, or no matching item at all -- notably `EFFLORESCENCE_CAUSE_CHECK`,
whose mitigation calls for a salt-blocking treatment that has no
corresponding PriceItem in the current catalog and is intentionally left
unmapped rather than guessed).

`recommended_work_code` is always a semantic `PriceItem.code` string, never
a `price_item_id` -- resolved fresh against the *current* owner's own
PriceBook only at evaluate/accept time (Stage 11B.2/11C), per the canonical
Stage 11 contract. This module adds no owner_id, no PriceItem FK, and no
price snapshot.
"""
from dataclasses import dataclass

from app.models.work_recommendation import (
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)

_T = WorkRecommendationTargetKind
# Wall / ceiling finishing works: primers "pod szpachlowanie", skim-coat repairs.
_WALL_CEILING = frozenset({_T.WALL, _T.CEILING, _T.ROOM})

# Stage 13F-PRE: explicit catalog compatibility of each recommended work with
# the inspection target it may be recommended for. The four baseline works
# are wall/ceiling finishing operations (primer under skim coat, contact
# primer, local skim repair, crack repair) -- none is a floor work, so a FLOOR
# inspection gets no recommendation from them. ROOM stays allowed (advisory
# only, never accepted into a plan). The current catalog has no FLOOR work
# (e.g. floor primer, self-levelling screed): a documented future catalog
# task, never substituted by a wall/ceiling item.
RECOMMENDED_WORK_TARGET_KINDS: dict[str, frozenset[WorkRecommendationTargetKind]] = {
    "CENNIK_PRIM_STD-01": _WALL_CEILING,
    "CENNIK_PRIM_ADH-01": _WALL_CEILING,
    "CENNIK_SKIM_LOCAL-01": _WALL_CEILING,
    "CENNIK_SKIM_CRACK-01": _WALL_CEILING,
}


def recommended_work_allows_target(
    recommended_work_code: str, target_kind: WorkRecommendationTargetKind
) -> bool:
    """True when the recommended work is explicitly compatible with the target.
    A code without an explicit entry is never recommended for FLOOR (floor
    compatibility must be declared, never inferred); other targets keep the
    pre-13F-PRE behaviour."""
    allowed = RECOMMENDED_WORK_TARGET_KINDS.get(recommended_work_code)
    if allowed is None:
        return target_kind is not WorkRecommendationTargetKind.FLOOR
    return target_kind in allowed


@dataclass(frozen=True)
class WorkRecommendationRuleData:
    trigger_type: WorkRecommendationTriggerType
    trigger_code: str
    recommended_work_code: str


def build_baseline_work_recommendation_rules() -> list[WorkRecommendationRuleData]:
    """Return the initial deterministic catalog served by bootstrap.

    Each entry pairs an existing Stage 7 `RiskRule.code` with an existing
    `PriceItem.code`. All four are `RISK_RULE`-triggered, not `FINDING`
    -triggered: an owner-approved Stage 7 risk rule already exists for each
    underlying condition, so a duplicate `FINDING`-keyed mapping for the same
    condition would only risk a second, redundant recommendation for the
    same suggested work (see docs/stage-11-architecture.md's own trigger-type
    disambiguation rationale) -- the smallest coherent baseline uses the
    more specific, already-fired `RiskRule.code` where one exists.
    """
    return [
        WorkRecommendationRuleData(
            trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="DUSTY_SUBSTRATE_PRIME",
            recommended_work_code="CENNIK_PRIM_STD-01",
        ),
        WorkRecommendationRuleData(
            trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="WEAK_ADHESION_PREP",
            recommended_work_code="CENNIK_PRIM_ADH-01",
        ),
        WorkRecommendationRuleData(
            trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="UNEVENNESS_PREP_INCREASED",
            recommended_work_code="CENNIK_SKIM_LOCAL-01",
        ),
        WorkRecommendationRuleData(
            trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="CRACK_RECURRENCE",
            recommended_work_code="CENNIK_SKIM_CRACK-01",
        ),
    ]
