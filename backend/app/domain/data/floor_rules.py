"""The deterministic rules of a FLOOR (owner 2026-10-30: "for the floor the technology differs from walls and ceilings").

A floor inspection (checklist version 2) records floor-only findings (`FLOOR_*`) and the covering the floor is prepared for
(`FLOOR_FINISH_*`). These rules read only those findings, so a floor never gets a wall risk (plaster deviation, glass fleece, skim
coat) and a wall never gets a floor one. Each rule says which communication category its phrase for the client has and which works
of the price book it recommends (`CENNIK_FLOOR_*`, the floor works of the catalogue).

The limits come from the research in `docs/FLOOR_TECH_RESEARCH_RU.md` (manufacturers' cards and Polish guidance found on the web;
DRAFT, to be checked by the owner): moisture CM of a cement screed 2.0 % (with underfloor heating 1.8 %), of an anhydrite screed
0.5 % (0.3 %), of a wooden substrate 12 %; flatness on a 2 m straightedge by covering (tiles, microcement, laminate, wood 3 mm,
large-format tiles and glued vinyl 2 mm, unknown covering 5 mm); the level of the whole room 5 mm. A measured value is compared with
the first value above the limit at the precision it is read (0.1 % CM, 0.1 mm), so the limit itself passes. The numbers are reference
data: a change of a limit ships as a new version of the rule.
"""
from dataclasses import dataclass

from app.domain.data.risk_rules import RiskRuleConditionData, RiskRuleData
from app.models.checklist import Substrate
from app.models.communication import CommunicationCategory
from app.models.risk import RiskConditionOperator, RiskSeverity

_O = RiskConditionOperator
_C = CommunicationCategory

FINISHES = ("TILES", "LARGE_TILES", "MICROCEMENT", "LAMINATE", "WOOD", "VINYL")
MINERAL = ("SCREED", "CONCRETE", "OTHER")  # a mineral substrate whose moisture is measured with the CM method

# the floor works of the catalogue (`price_book_seed.py`, `CENNIK_FLOOR_*`)
CM_MEASURE = "CENNIK_FLOOR_CM-01"
PRIMER = "CENNIK_FLOOR_PRIM-01"
EPOXY_PRIMER = "CENNIK_FLOOR_PRIM_EPOXY-01"
CONTACT_PRIMER = "CENNIK_FLOOR_CONTACT-01"
SELF_LEVELLING = "CENNIK_FLOOR_LEVEL-01"
GRINDING = "CENNIK_FLOOR_GRIND-01"
CRACK_STITCHING = "CENNIK_FLOOR_CRACK-01"
HOLLOW_REPAIR = "CENNIK_FLOOR_HOLLOW-01"
EXPANSION_JOINT = "CENNIK_FLOOR_JOINT-01"
WATERPROOFING = "CENNIK_FLOOR_WATERPROOF-01"
TILE_REMOVAL = "CENNIK_FLOOR_TILE_REMOVE-01"
BOARD_FIXING = "CENNIK_FLOOR_BOARD_FIX-01"
BOARD_OVERLAY = "CENNIK_FLOOR_OSB-01"
VAPOUR_BARRIER = "CENNIK_FLOOR_VAPOUR-01"

FLOOR_WORK_CODES = (
    CM_MEASURE, PRIMER, EPOXY_PRIMER, CONTACT_PRIMER, SELF_LEVELLING, GRINDING, CRACK_STITCHING, HOLLOW_REPAIR, EXPANSION_JOINT,
    WATERPROOFING, TILE_REMOVAL, BOARD_FIXING, BOARD_OVERLAY, VAPOUR_BARRIER,
)


@dataclass(frozen=True)
class FloorRule:
    rule: RiskRuleData
    category: CommunicationCategory
    works: tuple[str, ...] = ()


def _present(key: str) -> RiskRuleConditionData:
    return RiskRuleConditionData(_O.FINDING_PRESENT, finding_key=key)


def _absent(key: str) -> RiskRuleConditionData:
    return RiskRuleConditionData(_O.FINDING_ABSENT, finding_key=key)


def _above(key: str, value: str) -> RiskRuleConditionData:
    return RiskRuleConditionData(_O.NUMBER_AT_LEAST, finding_key=key, value={"value": value})


def _substrate(*values: str) -> RiskRuleConditionData:
    return RiskRuleConditionData(_O.SUBSTRATE_IN, value={"values": list(values)})


_FLOOR = RiskRuleConditionData(_O.TARGET_IN, value={"values": ["FLOOR"]})


def _rule(
    code: str,
    severity: RiskSeverity,
    category: CommunicationCategory,
    *conditions: RiskRuleConditionData,
    works: tuple[str, ...] = (),
    blocks: bool = False,
    warranty: bool = False,
    substrate: Substrate | None = None,
) -> FloorRule:
    return FloorRule(
        rule=RiskRuleData(
            code=code,
            version=1,
            severity=severity,
            conditions=(_FLOOR, *conditions),
            blocks_finishing=blocks,
            warranty_exclusion_candidate=warranty,
            substrate=substrate,
        ),
        category=category,
        works=works,
    )


def build_floor_rules() -> list[FloorRule]:
    S = RiskSeverity
    rules = [
        # ---- moisture (CM) of a mineral substrate: the limit depends on the screed and on underfloor heating ----
        _rule("FLOOR_MOISTURE_CEMENT", S.CRITICAL, _C.REQUIRE_CLIENT_DECISION, _substrate(*MINERAL), _absent("FLOOR_SCREED_ANHYDRITE"),
              _absent("FLOOR_HEATING"), _above("FLOOR_MOISTURE_CM", "2.1"), works=(CM_MEASURE,), blocks=True, warranty=True),
        _rule("FLOOR_MOISTURE_CEMENT_HEATED", S.CRITICAL, _C.REQUIRE_CLIENT_DECISION, _substrate(*MINERAL), _absent("FLOOR_SCREED_ANHYDRITE"),
              _present("FLOOR_HEATING"), _above("FLOOR_MOISTURE_CM", "1.9"), works=(CM_MEASURE,), blocks=True, warranty=True),
        _rule("FLOOR_MOISTURE_ANHYDRITE", S.CRITICAL, _C.REQUIRE_CLIENT_DECISION, _present("FLOOR_SCREED_ANHYDRITE"),
              _absent("FLOOR_HEATING"), _above("FLOOR_MOISTURE_CM", "0.6"), works=(CM_MEASURE,), blocks=True, warranty=True),
        _rule("FLOOR_MOISTURE_ANHYDRITE_HEATED", S.CRITICAL, _C.REQUIRE_CLIENT_DECISION, _present("FLOOR_SCREED_ANHYDRITE"),
              _present("FLOOR_HEATING"), _above("FLOOR_MOISTURE_CM", "0.4"), works=(CM_MEASURE,), blocks=True, warranty=True),
        _rule("FLOOR_MOISTURE_SUSPECTED", S.HIGH, _C.REQUIRE_CLIENT_DECISION, _present("FLOOR_MOISTURE_SUSPECTED"),
              works=(CM_MEASURE,), blocks=True),
        _rule("FLOOR_WOOD_MOISTURE", S.HIGH, _C.REQUIRE_CLIENT_DECISION, _substrate("WOOD_BOARDS"), _above("FLOOR_MOISTURE_CM", "12.1"),
              blocks=True, warranty=True, substrate=Substrate.WOOD_BOARDS),
        # ---- flatness on a 2 m straightedge: the covering decides the limit ----
        _rule("FLOOR_FLATNESS_TILES", S.MEDIUM, _C.SCOPE_CLARIFICATION, _present("FLOOR_FINISH_TILES"),
              _above("FLOOR_FLATNESS_MM", "3.1"), works=(SELF_LEVELLING,)),
        _rule("FLOOR_FLATNESS_LARGE_TILES", S.HIGH, _C.SCOPE_CLARIFICATION, _present("FLOOR_FINISH_LARGE_TILES"),
              _above("FLOOR_FLATNESS_MM", "2.1"), works=(SELF_LEVELLING,)),
        _rule("FLOOR_FLATNESS_MICROCEMENT", S.HIGH, _C.SCOPE_CLARIFICATION, _present("FLOOR_FINISH_MICROCEMENT"),
              _above("FLOOR_FLATNESS_MM", "3.1"), works=(SELF_LEVELLING,)),
        _rule("FLOOR_FLATNESS_LAMINATE", S.MEDIUM, _C.SCOPE_CLARIFICATION, _present("FLOOR_FINISH_LAMINATE"),
              _above("FLOOR_FLATNESS_MM", "3.1"), works=(SELF_LEVELLING,)),
        _rule("FLOOR_FLATNESS_WOOD", S.MEDIUM, _C.SCOPE_CLARIFICATION, _present("FLOOR_FINISH_WOOD"),
              _above("FLOOR_FLATNESS_MM", "3.1"), works=(SELF_LEVELLING,)),
        _rule("FLOOR_FLATNESS_VINYL", S.HIGH, _C.SCOPE_CLARIFICATION, _present("FLOOR_FINISH_VINYL"),
              _above("FLOOR_FLATNESS_MM", "2.1"), works=(SELF_LEVELLING,)),
        _rule("FLOOR_FLATNESS_GENERAL", S.MEDIUM, _C.SCOPE_CLARIFICATION, *(_absent(f"FLOOR_FINISH_{f}") for f in FINISHES),
              _above("FLOOR_FLATNESS_MM", "5.1"), works=(SELF_LEVELLING,)),
        _rule("FLOOR_LEVEL_OUT", S.MEDIUM, _C.SCOPE_CLARIFICATION, _above("FLOOR_LEVEL_DEVIATION", "5.1"), works=(SELF_LEVELLING,)),
        # ---- cracks, hollow screed, weak / loose / dusty / oily surface ----
        _rule("FLOOR_CRACK_REPAIR", S.MEDIUM, _C.RECOMMEND_PREPARATION, _present("FLOOR_CRACK"), _absent("FLOOR_FINISH_MICROCEMENT"),
              works=(CRACK_STITCHING,)),
        _rule("FLOOR_CRACK_MICROCEMENT", S.HIGH, _C.EXPLAIN_CONSEQUENCE, _present("FLOOR_CRACK"), _present("FLOOR_FINISH_MICROCEMENT"),
              works=(CRACK_STITCHING, EPOXY_PRIMER), blocks=True, warranty=True),
        _rule("FLOOR_SCREED_HOLLOW", S.HIGH, _C.SCOPE_CLARIFICATION, _present("FLOOR_SCREED_HOLLOW"), works=(HOLLOW_REPAIR,), blocks=True),
        _rule("FLOOR_SURFACE_WEAK", S.HIGH, _C.RECOMMEND_PREPARATION, _present("FLOOR_SURFACE_WEAK"), _absent("FLOOR_FINISH_LAMINATE"),
              works=(GRINDING, PRIMER), blocks=True),
        _rule("FLOOR_SURFACE_LOOSE", S.HIGH, _C.SCOPE_CLARIFICATION, _present("FLOOR_SURFACE_LOOSE"), works=(GRINDING,), blocks=True),
        _rule("FLOOR_SURFACE_DUSTY", S.LOW, _C.RECOMMEND_PREPARATION, _present("FLOOR_SURFACE_DUSTY"), works=(PRIMER,)),
        _rule("FLOOR_SURFACE_OILY", S.MEDIUM, _C.RECOMMEND_PREPARATION, _present("FLOOR_SURFACE_OILY"), works=(GRINDING,)),
        # ---- expansion joints ----
        _rule("FLOOR_EXPANSION_JOINTS", S.MEDIUM, _C.EXPLAIN_CONSEQUENCE, _present("EXPANSION_JOINT_MISSING"), _absent("FLOOR_HEATING"),
              works=(EXPANSION_JOINT,)),
        _rule("FLOOR_EXPANSION_JOINTS_HEATED", S.HIGH, _C.EXPLAIN_CONSEQUENCE, _present("EXPANSION_JOINT_MISSING"), _present("FLOOR_HEATING"),
              works=(EXPANSION_JOINT,), warranty=True),
        # ---- old tiles ----
        _rule("FLOOR_OLD_TILES_HOLLOW", S.HIGH, _C.SCOPE_CLARIFICATION, _present("FLOOR_TILES_HOLLOW"), works=(TILE_REMOVAL,), blocks=True),
        _rule("FLOOR_OLD_TILES_BOND", S.MEDIUM, _C.RECOMMEND_PREPARATION, _present("FLOOR_TILES_GLAZED"), _absent("FLOOR_FINISH_LAMINATE"),
              works=(CONTACT_PRIMER,)),
        _rule("FLOOR_OLD_TILES_LAYERS", S.HIGH, _C.SCOPE_CLARIFICATION, _present("FLOOR_TILES_TWO_LAYERS"), works=(TILE_REMOVAL,)),
        # ---- wooden boards ----
        _rule("FLOOR_BOARDS_FLEX", S.HIGH, _C.SCOPE_CLARIFICATION, _present("BOARDS_FLEX"), works=(BOARD_FIXING,), blocks=True),
        _rule("FLOOR_WOOD_DECAY", S.CRITICAL, _C.REQUIRE_CLIENT_DECISION, _present("WOOD_DECAY"), blocks=True, warranty=True),
        _rule("FLOOR_BOARDS_UNDER_TILES", S.HIGH, _C.EXPLAIN_CONSEQUENCE, _substrate("WOOD_BOARDS"), _present("FLOOR_FINISH_TILES"),
              works=(BOARD_OVERLAY,), warranty=True, substrate=Substrate.WOOD_BOARDS),
        _rule("FLOOR_BOARDS_UNDER_LARGE_TILES", S.HIGH, _C.EXPLAIN_CONSEQUENCE, _substrate("WOOD_BOARDS"), _present("FLOOR_FINISH_LARGE_TILES"),
              works=(BOARD_OVERLAY,), warranty=True, substrate=Substrate.WOOD_BOARDS),
        _rule("FLOOR_BOARDS_UNDER_MICROCEMENT", S.HIGH, _C.EXPLAIN_CONSEQUENCE, _substrate("WOOD_BOARDS"), _present("FLOOR_FINISH_MICROCEMENT"),
              works=(BOARD_OVERLAY,), warranty=True, substrate=Substrate.WOOD_BOARDS),
        # ---- wet zone ----
        _rule("FLOOR_WET_ZONE_TILES", S.HIGH, _C.RECOMMEND_PREPARATION, _present("FLOOR_WET_ZONE"), _present("FLOOR_FINISH_TILES"),
              works=(WATERPROOFING,)),
        _rule("FLOOR_WET_ZONE_LARGE_TILES", S.HIGH, _C.RECOMMEND_PREPARATION, _present("FLOOR_WET_ZONE"), _present("FLOOR_FINISH_LARGE_TILES"),
              works=(WATERPROOFING,)),
        _rule("FLOOR_WET_ZONE_MICROCEMENT", S.HIGH, _C.RECOMMEND_PREPARATION, _present("FLOOR_WET_ZONE"), _present("FLOOR_FINISH_MICROCEMENT"),
              works=(WATERPROOFING,)),
        _rule("FLOOR_WET_ZONE_LAMINATE", S.MEDIUM, _C.REQUIRE_CLIENT_DECISION, _present("FLOOR_WET_ZONE"), _present("FLOOR_FINISH_LAMINATE"),
              warranty=True),
        _rule("FLOOR_WET_ZONE_WOOD", S.MEDIUM, _C.REQUIRE_CLIENT_DECISION, _present("FLOOR_WET_ZONE"), _present("FLOOR_FINISH_WOOD"),
              warranty=True),
        # ---- what each covering needs from a mineral substrate ----
        _rule("FLOOR_LAMINATE_VAPOUR", S.LOW, _C.RECOMMEND_PREPARATION, _present("FLOOR_FINISH_LAMINATE"),
              _substrate("SCREED", "CONCRETE", "OLD_TILE", "OTHER"), works=(VAPOUR_BARRIER,)),
        _rule("FLOOR_MICROCEMENT_PREP", S.LOW, _C.RECOMMEND_PREPARATION, _present("FLOOR_FINISH_MICROCEMENT"), works=(EPOXY_PRIMER,)),
        _rule("FLOOR_LARGE_TILES_BED", S.LOW, _C.EXPLAIN_CONDITION, _present("FLOOR_FINISH_LARGE_TILES")),
        _rule("FLOOR_VINYL_SMOOTHING", S.LOW, _C.RECOMMEND_PREPARATION, _present("FLOOR_FINISH_VINYL"),
              _substrate("SCREED", "CONCRETE", "OLD_TILE", "OTHER"), works=(PRIMER, SELF_LEVELLING)),
    ]
    return rules


FLOOR_RULE_CODES = tuple(r.rule.code for r in build_floor_rules())
