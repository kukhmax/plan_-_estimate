"""Pure domain rules for the deterministic risk engine (Stage 7).

The engine derives technical risks from materialized inspection findings and
inspection context (substrate, quality target, target plane). It is fully
deterministic: the same inspection state always yields the same risk set and
the same source signature. All conditions within a rule must match for the
rule to fire.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import uuid
from collections.abc import Mapping, Sequence

from app.models.area_segment import AreaPlane
from app.models.checklist import QualityLevel, Substrate
from app.models.inspection import InspectionFinding
from app.models.risk import RiskConditionOperator, RiskRule, RiskRuleCondition


@dataclass(frozen=True)
class RuleContext:
    """Facts available to a rule evaluation, extracted from an inspection."""

    substrate: Substrate
    quality_target: QualityLevel | None
    target_type: str
    findings: Mapping[str, tuple[InspectionFinding, ...]]


def derive_target_type(
    *,
    surface_id: uuid.UUID | None,
    plane: AreaPlane | None,
) -> str:
    """Classify the inspection target into a stable target-type key."""
    if surface_id is not None:
        return "WALL"
    if plane is AreaPlane.FLOOR:
        return "FLOOR"
    if plane is AreaPlane.CEILING:
        return "CEILING"
    return "ROOM"


def compute_source_signature(source_ids: Sequence[uuid.UUID]) -> str:
    """SHA-256 over sorted source finding UUIDs.

    Order-independent, so the signature is stable regardless of evaluation
    order and changes only when the underlying source set changes.
    """
    raw = "\n".join(sorted(str(fid) for fid in source_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finding_number(finding: InspectionFinding) -> Decimal | None:
    snapshot = finding.value_snapshot or {}
    raw = snapshot.get("number")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None


def _values(condition: RiskRuleCondition) -> list[str]:
    value_json = condition.value_json or {}
    values = value_json.get("values")
    if not isinstance(values, list):
        return []
    return [str(item) for item in values]


def _threshold(condition: RiskRuleCondition) -> Decimal | None:
    value_json = condition.value_json or {}
    raw = value_json.get("value")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None


def _match_condition(
    condition: RiskRuleCondition,
    ctx: RuleContext,
) -> set[uuid.UUID] | None:
    """Return matched source finding ids, or None when the condition fails.

    An empty set means the condition passed without contributing source
    findings (e.g. FINDING_ABSENT, substrate/target/quality membership).
    Malformed or missing numeric snapshots fail safely: the condition does
    not count them as a match and the rule does not fire on them.
    """
    operator = condition.operator
    key = condition.finding_key

    if operator is RiskConditionOperator.FINDING_PRESENT:
        found = ctx.findings.get(key, ())
        if not found:
            return None
        return {finding.id for finding in found}

    if operator is RiskConditionOperator.FINDING_ABSENT:
        if ctx.findings.get(key, ()):
            return None
        return set()

    if operator in (RiskConditionOperator.NUMBER_AT_LEAST, RiskConditionOperator.NUMBER_AT_MOST):
        if key is None:
            return None
        threshold = _threshold(condition)
        if threshold is None:
            return None
        matched: set[uuid.UUID] = set()
        for finding in ctx.findings.get(key, ()):
            number = _finding_number(finding)
            if number is None:
                continue
            if operator is RiskConditionOperator.NUMBER_AT_LEAST:
                if number >= threshold:
                    matched.add(finding.id)
            elif number <= threshold:
                matched.add(finding.id)
        if not matched:
            return None
        return matched

    if operator is RiskConditionOperator.SUBSTRATE_IN:
        if ctx.substrate.value not in _values(condition):
            return None
        return set()

    if operator is RiskConditionOperator.SUBSTRATE_NOT_IN:
        if ctx.substrate.value in _values(condition):
            return None
        return set()

    if operator is RiskConditionOperator.TARGET_IN:
        if ctx.target_type not in _values(condition):
            return None
        return set()

    if operator is RiskConditionOperator.QUALITY_IN:
        if ctx.quality_target is None or ctx.quality_target.value not in _values(condition):
            return None
        return set()

    return None


def evaluate_rule(
    rule: RiskRule,
    conditions: Sequence[RiskRuleCondition],
    ctx: RuleContext,
) -> tuple[uuid.UUID, ...] | None:
    """Return source finding ids when the rule fires, else None.

    All conditions must match (AND). The returned ids feed the source
    signature; the tuple is sorted for determinism.
    """
    source: set[uuid.UUID] = set()
    for condition in conditions:
        matched = _match_condition(condition, ctx)
        if matched is None:
            return None
        source.update(matched)
    return tuple(sorted(source, key=str))
