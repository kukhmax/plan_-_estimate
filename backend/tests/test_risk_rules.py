"""Unit tests for the pure deterministic risk rules engine (Stage 7B)."""

import uuid

from app.domain.rules.risk_rules import (
    RuleContext,
    compute_source_signature,
    derive_target_type,
    evaluate_rule,
)
from app.models.area_segment import AreaPlane
from app.models.checklist import QualityLevel, Substrate
from app.models.inspection import InspectionFinding
from app.models.risk import (
    RiskConditionOperator,
    RiskRule,
    RiskRuleCondition,
    RiskSeverity,
)


def _finding(
    key: str,
    *,
    number: str | None = None,
    fid: uuid.UUID | None = None,
) -> InspectionFinding:
    snapshot = {}
    if number is not None:
        snapshot["number"] = number
    return InspectionFinding(
        id=fid or uuid.uuid4(),
        finding_key=key,
        value_snapshot=snapshot or None,
    )


def _rule(code: str = "R1") -> RiskRule:
    return RiskRule(
        code=code,
        version=1,
        severity=RiskSeverity.MEDIUM,
        active=True,
    )


def _cond(
    operator: RiskConditionOperator,
    *,
    finding_key: str | None = None,
    value: dict | None = None,
) -> RiskRuleCondition:
    return RiskRuleCondition(
        operator=operator,
        finding_key=finding_key,
        value_json=value,
        position=0,
    )


def _present(key: str) -> RiskRuleCondition:
    return _cond(RiskConditionOperator.FINDING_PRESENT, finding_key=key)


def _absent(key: str) -> RiskRuleCondition:
    return _cond(RiskConditionOperator.FINDING_ABSENT, finding_key=key)


def _number(
    key: str,
    threshold: str,
    operator: RiskConditionOperator = RiskConditionOperator.NUMBER_AT_LEAST,
) -> RiskRuleCondition:
    return _cond(operator, finding_key=key, value={"value": threshold})


def _ctx(
    *,
    substrate: Substrate = Substrate.CONCRETE,
    quality_target: QualityLevel | None = None,
    target_type: str = "ROOM",
    findings: dict[str, tuple[InspectionFinding, ...]] | None = None,
) -> RuleContext:
    return RuleContext(
        substrate=substrate,
        quality_target=quality_target,
        target_type=target_type,
        findings=findings or {},
    )


def test_signature_is_order_independent() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert compute_source_signature([a, b, c]) == compute_source_signature([c, a, b])


def test_signature_changes_when_source_set_changes() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert compute_source_signature([a]) != compute_source_signature([a, b])


def test_signature_is_stable_for_empty_sources() -> None:
    assert compute_source_signature([]) == compute_source_signature([])


def test_derive_target_type() -> None:
    assert derive_target_type(surface_id=uuid.uuid4(), plane=None) == "WALL"
    assert derive_target_type(surface_id=None, plane=AreaPlane.FLOOR) == "FLOOR"
    assert derive_target_type(surface_id=None, plane=AreaPlane.CEILING) == "CEILING"
    assert derive_target_type(surface_id=None, plane=None) == "ROOM"


def test_finding_present_fires_with_source_ids() -> None:
    crack = _finding("CRACK")
    ctx = _ctx(findings={"CRACK": (crack,)})
    source = evaluate_rule(_rule(), [_present("CRACK")], ctx)
    assert source == (crack.id,)


def test_finding_present_requires_present_finding() -> None:
    ctx = _ctx(findings={})
    assert evaluate_rule(
        _rule(), [_cond(RiskConditionOperator.FINDING_PRESENT, finding_key="CRACK")], ctx
    ) is None


def test_finding_absent_fires_when_missing() -> None:
    ctx = _ctx(findings={})
    source = evaluate_rule(
        _rule(), [_absent("MOLD")], ctx
    )
    assert source == ()


def test_finding_absent_blocked_when_present() -> None:
    ctx = _ctx(findings={"MOLD": (_finding("MOLD"),)})
    assert evaluate_rule(
        _rule(), [_absent("MOLD")], ctx
    ) is None


def test_number_at_least_fires_at_threshold() -> None:
    uneven = _finding("UNEVENNESS", number="3.000")
    ctx = _ctx(findings={"UNEVENNESS": (uneven,)})
    source = evaluate_rule(
        _rule(),
        [_number("UNEVENNESS", "3.000")],
        ctx,
    )
    assert source == (uneven.id,)


def test_number_at_least_below_threshold_does_not_fire() -> None:
    uneven = _finding("UNEVENNESS", number="2.999")
    ctx = _ctx(findings={"UNEVENNESS": (uneven,)})
    assert evaluate_rule(
        _rule(),
        [_number("UNEVENNESS", "3.000")],
        ctx,
    ) is None


def test_number_at_most_fires_below_threshold() -> None:
    gap = _finding("JOINT_GAP", number="1.500")
    ctx = _ctx(findings={"JOINT_GAP": (gap,)})
    source = evaluate_rule(
        _rule(),
        [_number("JOINT_GAP", "2.000", RiskConditionOperator.NUMBER_AT_MOST)],
        ctx,
    )
    assert source == (gap.id,)


def test_malformed_numeric_snapshot_fails_safe() -> None:
    bad = _finding("UNEVENNESS", number="not-a-number")
    ctx = _ctx(findings={"UNEVENNESS": (bad,)})
    assert evaluate_rule(
        _rule(),
        [_number("UNEVENNESS", "3.000")],
        ctx,
    ) is None


def test_missing_numeric_snapshot_fails_safe() -> None:
    finding = _finding("UNEVENNESS")  # no numeric snapshot
    ctx = _ctx(findings={"UNEVENNESS": (finding,)})
    assert evaluate_rule(
        _rule(),
        [_number("UNEVENNESS", "3.000")],
        ctx,
    ) is None


def test_substrate_in_fires_when_matching() -> None:
    ctx = _ctx(substrate=Substrate.GYPSUM_BOARD)
    source = evaluate_rule(
        _rule(),
        [_cond(RiskConditionOperator.SUBSTRATE_IN, value={"values": ["GYPSUM_BOARD"]})],
        ctx,
    )
    assert source == ()


def test_substrate_in_blocked_when_not_matching() -> None:
    ctx = _ctx(substrate=Substrate.CONCRETE)
    assert evaluate_rule(
        _rule(),
        [_cond(RiskConditionOperator.SUBSTRATE_IN, value={"values": ["GYPSUM_BOARD"]})],
        ctx,
    ) is None


def test_substrate_not_in_fires_when_absent() -> None:
    ctx = _ctx(substrate=Substrate.CONCRETE)
    assert evaluate_rule(
        _rule(),
        [_cond(RiskConditionOperator.SUBSTRATE_NOT_IN, value={"values": ["GYPSUM_BOARD"]})],
        ctx,
    ) == ()


def test_substrate_not_in_blocked_when_present() -> None:
    ctx = _ctx(substrate=Substrate.GYPSUM_BOARD)
    assert evaluate_rule(
        _rule(),
        [_cond(RiskConditionOperator.SUBSTRATE_NOT_IN, value={"values": ["GYPSUM_BOARD"]})],
        ctx,
    ) is None


def test_target_in_fires_when_matching() -> None:
    ctx = _ctx(target_type="WALL")
    assert evaluate_rule(
        _rule(),
        [_cond(RiskConditionOperator.TARGET_IN, value={"values": ["WALL", "CEILING"]})],
        ctx,
    ) == ()


def test_target_in_blocked_when_not_matching() -> None:
    ctx = _ctx(target_type="ROOM")
    assert evaluate_rule(
        _rule(),
        [_cond(RiskConditionOperator.TARGET_IN, value={"values": ["WALL"]})],
        ctx,
    ) is None


def test_quality_in_fires_when_matching() -> None:
    ctx = _ctx(quality_target=QualityLevel.S2)
    assert evaluate_rule(
        _rule(),
        [_cond(RiskConditionOperator.QUALITY_IN, value={"values": ["S2", "S3"]})],
        ctx,
    ) == ()


def test_quality_in_blocked_when_target_unset() -> None:
    ctx = _ctx(quality_target=None)
    assert evaluate_rule(
        _rule(),
        [_cond(RiskConditionOperator.QUALITY_IN, value={"values": ["S2"]})],
        ctx,
    ) is None


def test_all_conditions_must_match_and_semantics() -> None:
    crack = _finding("CRACK")
    board = _finding("BOARD_MOVEMENT")
    ctx = _ctx(
        substrate=Substrate.GYPSUM_BOARD,
        findings={
            "CRACK": (crack,),
            "BOARD_MOVEMENT": (board,),
        },
    )
    conditions = [
        _cond(RiskConditionOperator.FINDING_PRESENT, finding_key="CRACK"),
        _cond(RiskConditionOperator.FINDING_PRESENT, finding_key="BOARD_MOVEMENT"),
    ]
    source = evaluate_rule(_rule("BOARD_MOVEMENT_CRACK"), conditions, ctx)
    assert set(source or ()) == {crack.id, board.id}

    # Dropping one source finding breaks the AND chain.
    partial = _ctx(
        substrate=Substrate.GYPSUM_BOARD,
        findings={"CRACK": (crack,)},
    )
    assert evaluate_rule(_rule("BOARD_MOVEMENT_CRACK"), conditions, partial) is None


def test_overlapping_rules_are_independent() -> None:
    """One finding may legitimately fire multiple rules (no suppression)."""
    crack = _finding("CRACK")
    ctx = _ctx(findings={"CRACK": (crack,)})
    single = evaluate_rule(
        _rule("CRACK_RECURRENCE"),
        [_cond(RiskConditionOperator.FINDING_PRESENT, finding_key="CRACK")],
        ctx,
    )
    combo = evaluate_rule(
        _rule("BOARD_MOVEMENT_CRACK"),
        [
            _cond(RiskConditionOperator.FINDING_PRESENT, finding_key="CRACK"),
            _cond(RiskConditionOperator.FINDING_PRESENT, finding_key="BOARD_MOVEMENT"),
        ],
        ctx,
    )
    # CRACK_RECURRENCE fires; BOARD_MOVEMENT_CRACK does not because the second
    # condition is unmet -- overlapping catalogs are evaluated independently.
    assert single is not None
    assert combo is None
