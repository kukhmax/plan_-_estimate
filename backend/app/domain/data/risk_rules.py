"""Idempotent bootstrap data for the deterministic risk rules engine (Stage 7).

Rules are versioned immutable reference data materialized by the risk service
bootstrap, never seeded via Alembic, mirroring the checklist template catalog.
Thresholds (mm values, etc.) are initial domain defaults stored in condition
value_json so they can be tuned as reference data without a code change.
"""
from dataclasses import dataclass

from app.models.checklist import QualityLevel, Substrate
from app.models.risk import RiskConditionOperator, RiskSeverity


@dataclass(frozen=True)
class RiskRuleConditionData:
    operator: RiskConditionOperator
    finding_key: str | None = None
    value: dict | None = None


@dataclass(frozen=True)
class RiskRuleData:
    code: str
    version: int
    severity: RiskSeverity
    conditions: tuple[RiskRuleConditionData, ...]
    blocks_finishing: bool = False
    warranty_exclusion_candidate: bool = False
    substrate: Substrate | None = None


def build_baseline_risk_rules() -> list[RiskRuleData]:
    """Return the initial deterministic rule catalog served by bootstrap.

    All conditions within a rule must match for the rule to fire. Rules whose
    conditions reference only context (substrate/target/quality) or an absent
    finding contribute no source findings; their signature is constant.
    """
    rules = [
        RiskRuleData(
            code="CRACK_RECURRENCE",
            version=1,
            severity=RiskSeverity.MEDIUM,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="CRACK"
                ),
            ),
        ),
        RiskRuleData(
            code="BOARD_MOVEMENT_CRACK",
            version=1,
            severity=RiskSeverity.HIGH,
            blocks_finishing=True,
            warranty_exclusion_candidate=True,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="CRACK"
                ),
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="BOARD_MOVEMENT"
                ),
            ),
        ),
        RiskRuleData(
            code="MOISTURE_BLOCK_FINISHING",
            version=1,
            severity=RiskSeverity.CRITICAL,
            blocks_finishing=True,
            warranty_exclusion_candidate=True,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="HIGH_MOISTURE"
                ),
            ),
        ),
        RiskRuleData(
            code="WEAK_ADHESION_PREP",
            version=1,
            severity=RiskSeverity.HIGH,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="WEAK_ADHESION"
                ),
            ),
        ),
        RiskRuleData(
            code="LOOSE_SUBSTRATE_REMOVAL",
            version=1,
            severity=RiskSeverity.HIGH,
            blocks_finishing=True,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="LOOSE_SUBSTRATE"
                ),
            ),
        ),
        RiskRuleData(
            code="DUSTY_SUBSTRATE_PRIME",
            version=1,
            severity=RiskSeverity.LOW,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="DUSTY_SUBSTRATE"
                ),
            ),
        ),
        RiskRuleData(
            code="OILY_SUBSTRATE_DEGREASE",
            version=1,
            severity=RiskSeverity.MEDIUM,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="OILY_SUBSTRATE"
                ),
            ),
        ),
        RiskRuleData(
            code="MOLD_TREATMENT_BEFORE_FINISH",
            version=1,
            severity=RiskSeverity.HIGH,
            blocks_finishing=True,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="MOLD"
                ),
            ),
        ),
        RiskRuleData(
            code="DELAMINATION_REPAIR",
            version=1,
            severity=RiskSeverity.HIGH,
            blocks_finishing=True,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="DELAMINATION"
                ),
            ),
        ),
        RiskRuleData(
            code="UNEVENNESS_PREP_INCREASED",
            version=1,
            severity=RiskSeverity.MEDIUM,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.NUMBER_AT_LEAST,
                    finding_key="UNEVENNESS",
                    value={"value": "3.000"},
                ),
            ),
        ),
        RiskRuleData(
            code="JOINT_TAPE_MISSING_REWORK",
            version=1,
            severity=RiskSeverity.MEDIUM,
            substrate=Substrate.GYPSUM_BOARD,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT,
                    finding_key="JOINT_TAPE_MISSING",
                ),
                RiskRuleConditionData(
                    RiskConditionOperator.SUBSTRATE_IN,
                    value={"values": ["GYPSUM_BOARD"]},
                ),
            ),
        ),
        RiskRuleData(
            code="FASTENER_CORROSION_FIX",
            version=1,
            severity=RiskSeverity.MEDIUM,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT,
                    finding_key="FASTENER_CORROSION",
                ),
            ),
        ),
        RiskRuleData(
            code="JOINT_GAP_FILLING",
            version=1,
            severity=RiskSeverity.MEDIUM,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.NUMBER_AT_LEAST,
                    finding_key="JOINT_GAP",
                    value={"value": "2.000"},
                ),
            ),
        ),
        RiskRuleData(
            code="EFFLORESCENCE_CAUSE_CHECK",
            version=1,
            severity=RiskSeverity.MEDIUM,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT,
                    finding_key="EFFLORESCENCE",
                ),
            ),
        ),
        RiskRuleData(
            code="BLOW_HOLES_FILLING",
            version=1,
            severity=RiskSeverity.LOW,
            conditions=(
                RiskRuleConditionData(
                    RiskConditionOperator.FINDING_PRESENT, finding_key="BLOW_HOLES"
                ),
            ),
        ),
    ]
    return rules
