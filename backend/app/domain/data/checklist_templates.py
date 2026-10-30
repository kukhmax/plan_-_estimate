"""Idempotent bootstrap data for the inspection checklist engine (Stage 6).

Templates are versioned immutable reference data. They are materialized into the
database by the checklist service bootstrap, never seeded via Alembic, so a
template revision ships as a new (code, version) row while existing inspections
keep pointing at their immutable snapshot.
"""
from dataclasses import dataclass, field

from app.models.checklist import AnswerType, Substrate


@dataclass(frozen=True)
class TemplateOptionData:
    key: str
    label_key: str
    finding_key: str | None = None


@dataclass(frozen=True)
class TemplateQuestionData:
    key: str
    text_key: str
    answer_type: AnswerType
    hint_key: str | None = None
    unit_key: str | None = None
    finding_key: str | None = None
    options: tuple[TemplateOptionData, ...] = ()


@dataclass(frozen=True)
class TemplateSectionData:
    key: str
    title_key: str
    description_key: str | None = None
    questions: tuple[TemplateQuestionData, ...] = ()


@dataclass(frozen=True)
class ChecklistTemplateData:
    code: str
    version: int
    substrate: Substrate | None
    title_key: str
    sections: tuple[TemplateSectionData, ...] = ()


def _generic_questions() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="cracks_present",
            text_key="checklist.question.cracks_present",
            hint_key="checklist.hint.cracks_present",
            answer_type=AnswerType.BOOLEAN,
            finding_key="CRACK",
        ),
        TemplateQuestionData(
            key="unevenness_mm",
            text_key="checklist.question.unevenness_mm",
            hint_key="checklist.hint.unevenness_mm",
            unit_key="mm",
            answer_type=AnswerType.NUMBER,
            finding_key="UNEVENNESS",
        ),
        TemplateQuestionData(
            key="substrate_condition",
            text_key="checklist.question.substrate_condition",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("SOLID", "checklist.option.substrate_solid"),
                TemplateOptionData(
                    "LOOSE",
                    "checklist.option.substrate_loose",
                    finding_key="LOOSE_SUBSTRATE",
                ),
                TemplateOptionData(
                    "DUSTY",
                    "checklist.option.substrate_dusty",
                    finding_key="DUSTY_SUBSTRATE",
                ),
                TemplateOptionData(
                    "OILY",
                    "checklist.option.substrate_oily",
                    finding_key="OILY_SUBSTRATE",
                ),
            ),
        ),
        TemplateQuestionData(
            key="present_defects",
            text_key="checklist.question.present_defects",
            answer_type=AnswerType.MULTI_CHOICE,
            options=(
                TemplateOptionData(
                    "DELAMINATION",
                    "checklist.option.defect_delamination",
                    finding_key="DELAMINATION",
                ),
                TemplateOptionData(
                    "BLOW_HOLES",
                    "checklist.option.defect_blow_holes",
                    finding_key="BLOW_HOLES",
                ),
                TemplateOptionData(
                    "EFFLORESCENCE",
                    "checklist.option.defect_efflorescence",
                    finding_key="EFFLORESCENCE",
                ),
                TemplateOptionData(
                    "MOLD",
                    "checklist.option.defect_mold",
                    finding_key="MOLD",
                ),
            ),
        ),
        TemplateQuestionData(
            key="moisture_high",
            text_key="checklist.question.moisture_high",
            hint_key="checklist.hint.moisture_high",
            answer_type=AnswerType.BOOLEAN,
            finding_key="HIGH_MOISTURE",
        ),
        TemplateQuestionData(
            key="adhesion_weak",
            text_key="checklist.question.adhesion_weak",
            hint_key="checklist.hint.adhesion_weak",
            answer_type=AnswerType.BOOLEAN,
            finding_key="WEAK_ADHESION",
        ),
        TemplateQuestionData(
            key="notes",
            text_key="checklist.question.notes",
            answer_type=AnswerType.TEXT,
        ),
    )


def _drywall_questions() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="joint_tape_missing",
            text_key="checklist.question.joint_tape_missing",
            answer_type=AnswerType.BOOLEAN,
            finding_key="JOINT_TAPE_MISSING",
        ),
        TemplateQuestionData(
            key="board_movement",
            text_key="checklist.question.board_movement",
            hint_key="checklist.hint.board_movement",
            answer_type=AnswerType.BOOLEAN,
            finding_key="BOARD_MOVEMENT",
        ),
        TemplateQuestionData(
            key="fastener_corrosion",
            text_key="checklist.question.fastener_corrosion",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FASTENER_CORROSION",
        ),
        TemplateQuestionData(
            key="joint_gap_mm",
            text_key="checklist.question.joint_gap_mm",
            unit_key="mm",
            answer_type=AnswerType.NUMBER,
            finding_key="JOINT_GAP",
        ),
    )


def _floor_questions() -> tuple[TemplateQuestionData, ...]:
    """The common floor checks (UX walk B4): moisture, cracks, expansion joints, flatness, level, the state of the surface.

    Findings reuse the keys the risk engine already knows (CRACK, HIGH_MOISTURE, UNEVENNESS, LOOSE / DUSTY / OILY_SUBSTRATE) and add
    the facts only a floor has (EXPANSION_JOINT_MISSING, FLOOR_LEVEL_DEVIATION), recorded as findings of the inspection.
    """
    return (
        TemplateQuestionData(
            key="floor_moisture_measured",
            text_key="checklist.question.floor_moisture_measured",
            hint_key="checklist.hint.floor_moisture_measured",
            unit_key="checklist.unit.percent",
            answer_type=AnswerType.NUMBER,
        ),
        TemplateQuestionData(
            key="floor_moisture_high",
            text_key="checklist.question.floor_moisture_high",
            hint_key="checklist.hint.floor_moisture_high",
            answer_type=AnswerType.BOOLEAN,
            finding_key="HIGH_MOISTURE",
        ),
        TemplateQuestionData(
            key="cracks_present",
            text_key="checklist.question.floor_cracks_present",
            hint_key="checklist.hint.floor_cracks_present",
            answer_type=AnswerType.BOOLEAN,
            finding_key="CRACK",
        ),
        TemplateQuestionData(
            key="expansion_joints_missing",
            text_key="checklist.question.expansion_joints_missing",
            hint_key="checklist.hint.expansion_joints_missing",
            answer_type=AnswerType.BOOLEAN,
            finding_key="EXPANSION_JOINT_MISSING",
        ),
        TemplateQuestionData(
            key="floor_flatness_mm",
            text_key="checklist.question.floor_flatness_mm",
            hint_key="checklist.hint.floor_flatness_mm",
            unit_key="mm",
            answer_type=AnswerType.NUMBER,
            finding_key="UNEVENNESS",
        ),
        TemplateQuestionData(
            key="floor_level_deviation_mm",
            text_key="checklist.question.floor_level_deviation_mm",
            hint_key="checklist.hint.floor_level_deviation_mm",
            unit_key="mm",
            answer_type=AnswerType.NUMBER,
            finding_key="FLOOR_LEVEL_DEVIATION",
        ),
        TemplateQuestionData(
            key="substrate_condition",
            text_key="checklist.question.floor_surface_condition",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("SOLID", "checklist.option.substrate_solid"),
                TemplateOptionData("LOOSE", "checklist.option.substrate_loose", finding_key="LOOSE_SUBSTRATE"),
                TemplateOptionData("DUSTY", "checklist.option.substrate_dusty", finding_key="DUSTY_SUBSTRATE"),
                TemplateOptionData("OILY", "checklist.option.substrate_oily", finding_key="OILY_SUBSTRATE"),
            ),
        ),
        TemplateQuestionData(
            key="notes",
            text_key="checklist.question.notes",
            answer_type=AnswerType.TEXT,
        ),
    )


def _screed_questions() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="screed_type",
            text_key="checklist.question.screed_type",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("CEMENT", "checklist.option.screed_cement"),
                TemplateOptionData("ANHYDRITE", "checklist.option.screed_anhydrite"),
                TemplateOptionData("OTHER", "checklist.option.screed_other"),
            ),
        ),
        TemplateQuestionData(
            key="underfloor_heating",
            text_key="checklist.question.underfloor_heating",
            hint_key="checklist.hint.underfloor_heating",
            answer_type=AnswerType.BOOLEAN,
        ),
        TemplateQuestionData(
            key="screed_hollow",
            text_key="checklist.question.screed_hollow",
            hint_key="checklist.hint.screed_hollow",
            answer_type=AnswerType.BOOLEAN,
            finding_key="DELAMINATION",
        ),
        TemplateQuestionData(
            key="screed_weak_surface",
            text_key="checklist.question.screed_weak_surface",
            hint_key="checklist.hint.screed_weak_surface",
            answer_type=AnswerType.BOOLEAN,
            finding_key="WEAK_ADHESION",
        ),
    )


def _old_tile_questions() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="tiles_hollow",
            text_key="checklist.question.tiles_hollow",
            hint_key="checklist.hint.tiles_hollow",
            answer_type=AnswerType.BOOLEAN,
            finding_key="DELAMINATION",
        ),
        TemplateQuestionData(
            key="tiles_glazed",
            text_key="checklist.question.tiles_glazed",
            hint_key="checklist.hint.tiles_glazed",
            answer_type=AnswerType.BOOLEAN,
        ),
        TemplateQuestionData(
            key="tiles_layers",
            text_key="checklist.question.tiles_layers",
            hint_key="checklist.hint.tiles_layers",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("ONE", "checklist.option.tiles_one_layer"),
                TemplateOptionData("TWO", "checklist.option.tiles_two_layers"),
            ),
        ),
    )


def _wood_boards_questions() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="boards_flex",
            text_key="checklist.question.boards_flex",
            hint_key="checklist.hint.boards_flex",
            answer_type=AnswerType.BOOLEAN,
            finding_key="BOARDS_FLEX",
        ),
        TemplateQuestionData(
            key="wood_decay",
            text_key="checklist.question.wood_decay",
            hint_key="checklist.hint.wood_decay",
            answer_type=AnswerType.BOOLEAN,
            finding_key="WOOD_DECAY",
        ),
        TemplateQuestionData(
            key="boards_coating",
            text_key="checklist.question.boards_coating",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("NONE", "checklist.option.coating_none"),
                TemplateOptionData("VARNISH_OIL", "checklist.option.coating_varnish_oil"),
                TemplateOptionData("PAINT", "checklist.option.coating_paint"),
            ),
        ),
    )


# --- Floor checklists, version 2 (owner 2026-10-30: "for the floor the technology differs from walls and ceilings") ---------------------------
#
# Version 1 (UX walk B4) reused the finding keys of the walls, so a floor got the wall risks, their technical basis and their phrases. Version 2
# asks what the floor is prepared FOR (the covering decides the limits: moisture CM, flatness on a 2 m straightedge, waterproofing, vapour
# barrier) and records floor-only findings (`FLOOR_*`), which only the floor risk rules read. Version 1 stays for the inspections made with it.


def _floor_target_questions() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="planned_finish",
            text_key="checklist.question.planned_finish",
            hint_key="checklist.hint.planned_finish",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("TILES", "checklist.option.finish_tiles", finding_key="FLOOR_FINISH_TILES"),
                TemplateOptionData("LARGE_TILES", "checklist.option.finish_large_tiles", finding_key="FLOOR_FINISH_LARGE_TILES"),
                TemplateOptionData("MICROCEMENT", "checklist.option.finish_microcement", finding_key="FLOOR_FINISH_MICROCEMENT"),
                TemplateOptionData("LAMINATE", "checklist.option.finish_laminate", finding_key="FLOOR_FINISH_LAMINATE"),
                TemplateOptionData("WOOD", "checklist.option.finish_wood", finding_key="FLOOR_FINISH_WOOD"),
                TemplateOptionData("VINYL", "checklist.option.finish_vinyl", finding_key="FLOOR_FINISH_VINYL"),
                TemplateOptionData("UNKNOWN", "checklist.option.finish_unknown"),
            ),
        ),
        TemplateQuestionData(
            key="wet_zone",
            text_key="checklist.question.wet_zone",
            hint_key="checklist.hint.wet_zone",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FLOOR_WET_ZONE",
        ),
        TemplateQuestionData(
            key="underfloor_heating",
            text_key="checklist.question.underfloor_heating",
            hint_key="checklist.hint.underfloor_heating",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FLOOR_HEATING",
        ),
    )


def _floor_questions_v2() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="floor_moisture_measured",
            text_key="checklist.question.floor_moisture_measured",
            hint_key="checklist.hint.floor_moisture_measured_v2",
            unit_key="checklist.unit.percent",
            answer_type=AnswerType.NUMBER,
            finding_key="FLOOR_MOISTURE_CM",
        ),
        TemplateQuestionData(
            key="floor_moisture_high",
            text_key="checklist.question.floor_moisture_suspected",
            hint_key="checklist.hint.floor_moisture_suspected",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FLOOR_MOISTURE_SUSPECTED",
        ),
        TemplateQuestionData(
            key="cracks_present",
            text_key="checklist.question.floor_cracks_present",
            hint_key="checklist.hint.floor_cracks_present",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FLOOR_CRACK",
        ),
        TemplateQuestionData(
            key="expansion_joints_missing",
            text_key="checklist.question.expansion_joints_missing",
            hint_key="checklist.hint.expansion_joints_missing",
            answer_type=AnswerType.BOOLEAN,
            finding_key="EXPANSION_JOINT_MISSING",
        ),
        TemplateQuestionData(
            key="floor_flatness_mm",
            text_key="checklist.question.floor_flatness_mm",
            hint_key="checklist.hint.floor_flatness_mm",
            unit_key="mm",
            answer_type=AnswerType.NUMBER,
            finding_key="FLOOR_FLATNESS_MM",
        ),
        TemplateQuestionData(
            key="floor_level_deviation_mm",
            text_key="checklist.question.floor_level_deviation_mm",
            hint_key="checklist.hint.floor_level_deviation_mm",
            unit_key="mm",
            answer_type=AnswerType.NUMBER,
            finding_key="FLOOR_LEVEL_DEVIATION",
        ),
        TemplateQuestionData(
            key="floor_weak_surface",
            text_key="checklist.question.floor_weak_surface",
            hint_key="checklist.hint.floor_weak_surface",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FLOOR_SURFACE_WEAK",
        ),
        TemplateQuestionData(
            key="substrate_condition",
            text_key="checklist.question.floor_surface_condition",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("SOLID", "checklist.option.substrate_solid"),
                TemplateOptionData("LOOSE", "checklist.option.substrate_loose", finding_key="FLOOR_SURFACE_LOOSE"),
                TemplateOptionData("DUSTY", "checklist.option.substrate_dusty", finding_key="FLOOR_SURFACE_DUSTY"),
                TemplateOptionData("OILY", "checklist.option.substrate_oily", finding_key="FLOOR_SURFACE_OILY"),
            ),
        ),
        TemplateQuestionData(
            key="notes",
            text_key="checklist.question.notes",
            answer_type=AnswerType.TEXT,
        ),
    )


def _screed_questions_v2() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="screed_type",
            text_key="checklist.question.screed_type",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("CEMENT", "checklist.option.screed_cement"),
                TemplateOptionData("ANHYDRITE", "checklist.option.screed_anhydrite", finding_key="FLOOR_SCREED_ANHYDRITE"),
                TemplateOptionData("OTHER", "checklist.option.screed_other"),
            ),
        ),
        TemplateQuestionData(
            key="screed_hollow",
            text_key="checklist.question.screed_hollow",
            hint_key="checklist.hint.screed_hollow",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FLOOR_SCREED_HOLLOW",
        ),
    )


def _old_tile_questions_v2() -> tuple[TemplateQuestionData, ...]:
    return (
        TemplateQuestionData(
            key="tiles_hollow",
            text_key="checklist.question.tiles_hollow",
            hint_key="checklist.hint.tiles_hollow",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FLOOR_TILES_HOLLOW",
        ),
        TemplateQuestionData(
            key="tiles_glazed",
            text_key="checklist.question.tiles_glazed",
            hint_key="checklist.hint.tiles_glazed",
            answer_type=AnswerType.BOOLEAN,
            finding_key="FLOOR_TILES_GLAZED",
        ),
        TemplateQuestionData(
            key="tiles_layers",
            text_key="checklist.question.tiles_layers",
            hint_key="checklist.hint.tiles_layers",
            answer_type=AnswerType.SINGLE_CHOICE,
            options=(
                TemplateOptionData("ONE", "checklist.option.tiles_one_layer"),
                TemplateOptionData("TWO", "checklist.option.tiles_two_layers", finding_key="FLOOR_TILES_TWO_LAYERS"),
            ),
        ),
    )


_GENERIC_SECTION = TemplateSectionData(
    key="general_conditions",
    title_key="checklist.section.general_conditions",
    description_key="checklist.section.general_conditions_desc",
    questions=_generic_questions(),
)

_DRYWALL_SECTION = TemplateSectionData(
    key="drywall_joints",
    title_key="checklist.section.drywall_joints",
    description_key="checklist.section.drywall_joints_desc",
    questions=_drywall_questions(),
)

_FLOOR_SECTION = TemplateSectionData(
    key="floor_conditions",
    title_key="checklist.section.floor_conditions",
    description_key="checklist.section.floor_conditions_desc",
    questions=_floor_questions(),
)

_SCREED_SECTION = TemplateSectionData(
    key="screed_specific",
    title_key="checklist.section.screed_specific",
    description_key="checklist.section.screed_specific_desc",
    questions=_screed_questions(),
)

_OLD_TILE_SECTION = TemplateSectionData(
    key="old_tile_specific",
    title_key="checklist.section.old_tile_specific",
    description_key="checklist.section.old_tile_specific_desc",
    questions=_old_tile_questions(),
)

_WOOD_BOARDS_SECTION = TemplateSectionData(
    key="wood_boards_specific",
    title_key="checklist.section.wood_boards_specific",
    description_key="checklist.section.wood_boards_specific_desc",
    questions=_wood_boards_questions(),
)

_FLOOR_TARGET_SECTION = TemplateSectionData(
    key="floor_target",
    title_key="checklist.section.floor_target",
    description_key="checklist.section.floor_target_desc",
    questions=_floor_target_questions(),
)

_FLOOR_SECTION_V2 = TemplateSectionData(
    key="floor_conditions",
    title_key="checklist.section.floor_conditions",
    description_key="checklist.section.floor_conditions_desc",
    questions=_floor_questions_v2(),
)

_SCREED_SECTION_V2 = TemplateSectionData(
    key="screed_specific",
    title_key="checklist.section.screed_specific",
    description_key="checklist.section.screed_specific_desc",
    questions=_screed_questions_v2(),
)

_OLD_TILE_SECTION_V2 = TemplateSectionData(
    key="old_tile_specific",
    title_key="checklist.section.old_tile_specific",
    description_key="checklist.section.old_tile_specific_desc",
    questions=_old_tile_questions_v2(),
)


def _floor_v2(code: str, substrate: Substrate, title_key: str, *specific: TemplateSectionData) -> ChecklistTemplateData:
    return ChecklistTemplateData(
        code=code,
        version=2,
        substrate=substrate,
        title_key=title_key,
        sections=(_FLOOR_TARGET_SECTION, _FLOOR_SECTION_V2, *specific),
    )


def build_baseline_templates() -> list[ChecklistTemplateData]:
    """Return the full immutable template catalog served by bootstrap."""
    return [
        ChecklistTemplateData(
            code="substrate-concrete",
            version=1,
            substrate=Substrate.CONCRETE,
            title_key="checklist.template.concrete.title",
            sections=(_GENERIC_SECTION,),
        ),
        ChecklistTemplateData(
            code="substrate-gypsum-plaster",
            version=1,
            substrate=Substrate.GYPSUM_PLASTER,
            title_key="checklist.template.gypsum_plaster.title",
            sections=(_GENERIC_SECTION,),
        ),
        ChecklistTemplateData(
            code="substrate-cement-lime-plaster",
            version=1,
            substrate=Substrate.CEMENT_LIME_PLASTER,
            title_key="checklist.template.cement_lime_plaster.title",
            sections=(_GENERIC_SECTION,),
        ),
        ChecklistTemplateData(
            code="substrate-gypsum-board",
            version=1,
            substrate=Substrate.GYPSUM_BOARD,
            title_key="checklist.template.gypsum_board.title",
            sections=(_GENERIC_SECTION, _DRYWALL_SECTION),
        ),
        ChecklistTemplateData(
            code="substrate-painted",
            version=1,
            substrate=Substrate.PAINTED,
            title_key="checklist.template.painted.title",
            sections=(_GENERIC_SECTION,),
        ),
        ChecklistTemplateData(
            code="substrate-other",
            version=1,
            substrate=Substrate.OTHER,
            title_key="checklist.template.other.title",
            sections=(_GENERIC_SECTION,),
        ),
        ChecklistTemplateData(
            code="substrate-screed",
            version=1,
            substrate=Substrate.SCREED,
            title_key="checklist.template.screed.title",
            sections=(_FLOOR_SECTION, _SCREED_SECTION),
        ),
        ChecklistTemplateData(
            code="substrate-old-tile",
            version=1,
            substrate=Substrate.OLD_TILE,
            title_key="checklist.template.old_tile.title",
            sections=(_FLOOR_SECTION, _OLD_TILE_SECTION),
        ),
        ChecklistTemplateData(
            code="substrate-wood-boards",
            version=1,
            substrate=Substrate.WOOD_BOARDS,
            title_key="checklist.template.wood_boards.title",
            sections=(_FLOOR_SECTION, _WOOD_BOARDS_SECTION),
        ),
        # A floor on a substrate the walls know as well (concrete, other) asks the floor questions, not the wall ones.
        # The code prefix `floor-` is the contract: a floor inspection takes the template that has it, a wall / ceiling one the other.
        ChecklistTemplateData(
            code="floor-concrete",
            version=1,
            substrate=Substrate.CONCRETE,
            title_key="checklist.template.floor_concrete.title",
            sections=(_FLOOR_SECTION,),
        ),
        ChecklistTemplateData(
            code="floor-other",
            version=1,
            substrate=Substrate.OTHER,
            title_key="checklist.template.floor_other.title",
            sections=(_FLOOR_SECTION,),
        ),
        # version 2 of the five floor checklists: the covering the floor is prepared for, and floor-only findings
        _floor_v2("substrate-screed", Substrate.SCREED, "checklist.template.screed.title", _SCREED_SECTION_V2),
        _floor_v2("substrate-old-tile", Substrate.OLD_TILE, "checklist.template.old_tile.title", _OLD_TILE_SECTION_V2),
        _floor_v2("substrate-wood-boards", Substrate.WOOD_BOARDS, "checklist.template.wood_boards.title", _WOOD_BOARDS_SECTION),
        _floor_v2("floor-concrete", Substrate.CONCRETE, "checklist.template.floor_concrete.title"),
        _floor_v2("floor-other", Substrate.OTHER, "checklist.template.floor_other.title"),
    ]