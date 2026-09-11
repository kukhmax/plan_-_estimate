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
    ]