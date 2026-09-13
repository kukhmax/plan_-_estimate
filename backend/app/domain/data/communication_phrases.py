"""Idempotent bootstrap data for the deterministic communication engine (Stage 8).

Phrases are versioned immutable reference data materialized by the communication
service bootstrap, never seeded via Alembic, mirroring the checklist and risk
catalogs. Released versions are never edited; a revision ships as a new
(code, version) row while materialized applications keep their snapshot.

Phrase selection is exact-key equality against already-materialized facts — it
deliberately reuses no Stage 7 condition engine. Three deterministic sources:

A. RISK-derived  — one phrase per baseline risk code, whose content key is the
   Stage 7 seed ``risk.<slug>.communication`` (reused, never duplicated).
B. FINDING-only  — phrases for findings NOT already covered by an active risk,
   matched by exact finding_key with optional substrate/quality refinements.
C. QUALITY       — explicit substrate + quality_target expectation phrases.
"""
from dataclasses import dataclass

from app.models.checklist import QualityLevel, Substrate
from app.models.communication import CommunicationCategory

_RISK_PRIORITY = 0
_FINDING_PRIORITY = 10
_QUALITY_PRIORITY = 20


@dataclass(frozen=True)
class CommunicationPhraseData:
    code: str
    version: int
    category: CommunicationCategory
    priority: int
    phrase_key: str
    why_key: str | None = None
    seed_key: str | None = None
    risk_code: str | None = None
    finding_key: str | None = None
    substrate: Substrate | None = None
    quality_level: QualityLevel | None = None


def risk_phrase_code(risk_code: str) -> str:
    return f"COMM_RISK_{risk_code}"


def risk_phrase_key(risk_code: str) -> str:
    return f"risk.{risk_code.lower()}.communication"


def _finding(category: CommunicationCategory, **data) -> CommunicationPhraseData:
    return CommunicationPhraseData(
        version=1,
        category=category,
        priority=_FINDING_PRIORITY,
        **data,
    )


def _risk(
    risk_code: str,
    category: CommunicationCategory,
) -> CommunicationPhraseData:
    key = risk_phrase_key(risk_code)
    return CommunicationPhraseData(
        code=risk_phrase_code(risk_code),
        version=1,
        category=category,
        priority=_RISK_PRIORITY,
        phrase_key=key,
        seed_key=key,
        risk_code=risk_code,
    )


def _quality(
    substrate: Substrate,
    quality_level: QualityLevel,
) -> CommunicationPhraseData:
    slug = f"{substrate.value.lower()}_{quality_level.value.lower()}"
    return CommunicationPhraseData(
        code=f"COMM_QUALITY_{substrate.value}_{quality_level.value}",
        version=1,
        category=CommunicationCategory.QUALITY_EXPECTATION,
        priority=_QUALITY_PRIORITY,
        phrase_key=f"communication.comm_quality_{slug}.phrase",
        why_key=f"communication.comm_quality_{slug}.why",
        substrate=substrate,
        quality_level=quality_level,
    )


def build_baseline_communication_phrases() -> list[CommunicationPhraseData]:
    """Return the initial communication phrase catalog served by bootstrap.

    Risk-derived phrases cover every baseline risk code (seed keys point at the
    existing Stage 7 ``risk.<slug>.communication`` locale entries). Finding-only
    phrases exist only for the sub-risk / subset cases that are NOT already
    covered by an active risk, so a covered finding never double-emits noise.
    Quality phrases are explicit substrate->quality expectation statements only.
    """
    phrases = [
        _risk("CRACK_RECURRENCE", CommunicationCategory.EXPLAIN_CONDITION),
        _risk("BOARD_MOVEMENT_CRACK", CommunicationCategory.EXPLAIN_CONSEQUENCE),
        _risk(
            "MOISTURE_BLOCK_FINISHING",
            CommunicationCategory.REQUIRE_CLIENT_DECISION,
        ),
        _risk("WEAK_ADHESION_PREP", CommunicationCategory.RECOMMEND_PREPARATION),
        _risk("LOOSE_SUBSTRATE_REMOVAL", CommunicationCategory.SCOPE_CLARIFICATION),
        _risk("DUSTY_SUBSTRATE_PRIME", CommunicationCategory.RECOMMEND_PREPARATION),
        _risk("OILY_SUBSTRATE_DEGREASE", CommunicationCategory.RECOMMEND_PREPARATION),
        _risk(
            "MOLD_TREATMENT_BEFORE_FINISH",
            CommunicationCategory.REQUIRE_CLIENT_DECISION,
        ),
        _risk("DELAMINATION_REPAIR", CommunicationCategory.SCOPE_CLARIFICATION),
        _risk(
            "UNEVENNESS_PREP_INCREASED",
            CommunicationCategory.SCOPE_CLARIFICATION,
        ),
        _risk(
            "JOINT_TAPE_MISSING_REWORK",
            CommunicationCategory.REQUIRE_CLIENT_DECISION,
        ),
        _risk("FASTENER_CORROSION_FIX", CommunicationCategory.RECOMMEND_PREPARATION),
        _risk("JOINT_GAP_FILLING", CommunicationCategory.RECOMMEND_PREPARATION),
        _risk("EFFLORESCENCE_CAUSE_CHECK", CommunicationCategory.EXPLAIN_CONDITION),
        _risk("BLOW_HOLES_FILLING", CommunicationCategory.RECOMMEND_PREPARATION),
        # Finding-only: UNEVENNESS below the Stage 7 risk threshold exercises the
        # specificity precedence: finding > finding+substrate > finding+substrate+quality.
        _finding(
            CommunicationCategory.EXPLAIN_CONDITION,
            code="COMM_FIND_UNEVENNESS",
            phrase_key="communication.comm_find_unevenness.phrase",
            why_key="communication.comm_find_unevenness.why",
            finding_key="UNEVENNESS",
        ),
        _finding(
            CommunicationCategory.EXPLAIN_CONDITION,
            code="COMM_FIND_UNEVENNESS_GYPSUM_PLASTER",
            phrase_key="communication.comm_find_unevenness_gypsum_plaster.phrase",
            why_key="communication.comm_find_unevenness_gypsum_plaster.why",
            finding_key="UNEVENNESS",
            substrate=Substrate.GYPSUM_PLASTER,
        ),
        _finding(
            CommunicationCategory.EXPLAIN_CONDITION,
            code="COMM_FIND_UNEVENNESS_GYPSUM_PLASTER_S3",
            phrase_key="communication.comm_find_unevenness_gypsum_plaster_s3.phrase",
            why_key="communication.comm_find_unevenness_gypsum_plaster_s3.why",
            finding_key="UNEVENNESS",
            substrate=Substrate.GYPSUM_PLASTER,
            quality_level=QualityLevel.S3,
        ),
        # Finding-only: BOARD_MOVEMENT without CRACK never fires the compounded
        # Stage 7 rule, so the isolated finding is worth a phrase of its own.
        _finding(
            CommunicationCategory.EXPLAIN_CONDITION,
            code="COMM_FIND_BOARD_MOVEMENT",
            phrase_key="communication.comm_find_board_movement.phrase",
            why_key="communication.comm_find_board_movement.why",
            finding_key="BOARD_MOVEMENT",
        ),
        # Finding-only: JOINT_GAP below the 2 mm risk threshold.
        _finding(
            CommunicationCategory.EXPLAIN_CONDITION,
            code="COMM_FIND_JOINT_GAP",
            phrase_key="communication.comm_find_joint_gap.phrase",
            why_key="communication.comm_find_joint_gap.why",
            finding_key="JOINT_GAP",
        ),
        # Quality expectations: explicit substrate + quality_target mappings only.
        _quality(Substrate.GYPSUM_PLASTER, QualityLevel.S3),
        _quality(Substrate.GYPSUM_BOARD, QualityLevel.Q2),
        _quality(Substrate.CONCRETE, QualityLevel.S4),
        _quality(Substrate.PAINTED, QualityLevel.S2),
    ]
    return phrases