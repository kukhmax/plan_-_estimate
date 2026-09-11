"""Unit tests for the pure inspection checklist rules (Stage 6)."""

import uuid

import pytest

from app.domain.exceptions import QualityScaleMismatchError
from app.domain.rules.inspection_rules import (
    assert_quality_scale_valid,
    build_finding_specs,
)
from app.models.checklist import (
    AnswerType,
    ChecklistOption,
    ChecklistQuestion,
    QualityLevel,
    Substrate,
)
from app.models.inspection import InspectionAnswer


def _question(
    answer_type: AnswerType,
    *,
    finding_key: str | None = None,
    options: list[ChecklistOption] | None = None,
) -> ChecklistQuestion:
    question = ChecklistQuestion(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        section_id=None,
        position=0,
        key="q",
        text_key="checklist.question.q",
        answer_type=answer_type,
        finding_key=finding_key,
    )
    question.options = options or []
    return question


def _answer(**kwargs) -> InspectionAnswer:
    defaults = {
        "id": uuid.uuid4(),
        "inspection_id": uuid.uuid4(),
        "question_id": uuid.uuid4(),
    }
    defaults.update(kwargs)
    return InspectionAnswer(**defaults)


def _option(key: str, finding_key: str | None = None) -> ChecklistOption:
    return ChecklistOption(
        id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        position=0,
        key=key,
        label_key=f"checklist.option.{key.lower()}",
        finding_key=finding_key,
    )


class TestQualityScaleValidation:
    def test_gypsum_board_requires_q_scale(self) -> None:
        assert_quality_scale_valid(Substrate.GYPSUM_BOARD, QualityLevel.Q1)
        assert_quality_scale_valid(Substrate.GYPSUM_BOARD, QualityLevel.Q4)

    def test_gypsum_board_rejects_s_scale(self) -> None:
        with pytest.raises(QualityScaleMismatchError):
            assert_quality_scale_valid(Substrate.GYPSUM_BOARD, QualityLevel.S1)

    def test_plaster_substrates_require_s_scale(self) -> None:
        for substrate in (
            Substrate.CONCRETE,
            Substrate.GYPSUM_PLASTER,
            Substrate.CEMENT_LIME_PLASTER,
        ):
            assert_quality_scale_valid(substrate, QualityLevel.S2)
            with pytest.raises(QualityScaleMismatchError):
                assert_quality_scale_valid(substrate, QualityLevel.Q2)

    def test_none_target_is_always_allowed(self) -> None:
        assert_quality_scale_valid(Substrate.GYPSUM_BOARD, None)
        assert_quality_scale_valid(Substrate.CONCRETE, None)
        assert_quality_scale_valid(Substrate.PAINTED, None)

    def test_unrestricted_substrates_accept_both_scales(self) -> None:
        assert_quality_scale_valid(Substrate.PAINTED, QualityLevel.S3)
        assert_quality_scale_valid(Substrate.PAINTED, QualityLevel.Q3)
        assert_quality_scale_valid(Substrate.OTHER, QualityLevel.S1)
        assert_quality_scale_valid(Substrate.OTHER, QualityLevel.Q1)


class TestBuildFindingSpecs:
    def test_boolean_true_with_finding_key_materializes(self) -> None:
        question = _question(AnswerType.BOOLEAN, finding_key="CRACK")
        answer = _answer(value_bool=True)
        rows = [(answer, question, [])]
        specs = build_finding_specs(rows)
        assert len(specs) == 1
        assert specs[0].finding_key == "CRACK"
        assert specs[0].value_snapshot == {"bool": True}
        assert specs[0].answer_id == answer.id
        assert specs[0].question_id == question.id

    def test_boolean_false_never_materializes(self) -> None:
        question = _question(AnswerType.BOOLEAN, finding_key="CRACK")
        rows = [(_answer(value_bool=False), question, [])]
        assert build_finding_specs(rows) == []

    def test_boolean_without_finding_key_never_materializes(self) -> None:
        question = _question(AnswerType.BOOLEAN)
        rows = [(_answer(value_bool=True), question, [])]
        assert build_finding_specs(rows) == []

    def test_number_with_finding_key_materializes_snapshot(self) -> None:
        question = _question(AnswerType.NUMBER, finding_key="UNEVENNESS")
        answer = _answer(value_number="3.500")
        specs = build_finding_specs([(answer, question, [])])
        assert len(specs) == 1
        assert specs[0].value_snapshot == {"number": "3.500"}

    def test_number_without_finding_key_is_never_a_generic_finding(self) -> None:
        # A positive number alone must never become a finding.
        question = _question(AnswerType.NUMBER)
        answer = _answer(value_number="5.000")
        assert build_finding_specs([(answer, question, [])]) == []

    def test_text_with_finding_key_materializes(self) -> None:
        question = _question(AnswerType.TEXT, finding_key="NOTE")
        answer = _answer(value_text="spalling detected")
        specs = build_finding_specs([(answer, question, [])])
        assert len(specs) == 1
        assert specs[0].value_snapshot == {"text": "spalling detected"}

    def test_empty_text_never_materializes(self) -> None:
        question = _question(AnswerType.TEXT, finding_key="NOTE")
        answer = _answer(value_text="")
        assert build_finding_specs([(answer, question, [])]) == []

    def test_single_choice_selected_option_with_finding_key(self) -> None:
        options = [
            _option("SOLID"),
            _option("LOOSE", finding_key="LOOSE_SUBSTRATE"),
        ]
        question = _question(AnswerType.SINGLE_CHOICE, options=options)
        answer = _answer(option_key="LOOSE")
        specs = build_finding_specs([(answer, question, options)])
        assert len(specs) == 1
        assert specs[0].finding_key == "LOOSE_SUBSTRATE"
        assert specs[0].value_snapshot == {"option": "LOOSE"}

    def test_single_choice_option_without_finding_key_never_materializes(self) -> None:
        options = [_option("SOLID")]
        question = _question(AnswerType.SINGLE_CHOICE, options=options)
        answer = _answer(option_key="SOLID")
        assert build_finding_specs([(answer, question, options)]) == []

    def test_multi_choice_materializes_one_finding_per_selected_keyed_option(self) -> None:
        options = [
            _option("DELAMINATION", finding_key="DELAMINATION"),
            _option("BLOW_HOLES", finding_key="BLOW_HOLES"),
            _option("SOLID"),
        ]
        question = _question(AnswerType.MULTI_CHOICE, options=options)
        answer = _answer(option_keys=["DELAMINATION", "SOLID"])
        specs = build_finding_specs([(answer, question, options)])
        assert [spec.finding_key for spec in specs] == ["DELAMINATION"]

    def test_unanswered_question_produces_nothing(self) -> None:
        question = _question(AnswerType.BOOLEAN, finding_key="CRACK")
        answer = _answer(value_bool=None)
        assert build_finding_specs([(answer, question, [])]) == []

    def test_two_questions_share_a_finding_key_but_keep_distinct_sources(self) -> None:
        first = _question(AnswerType.BOOLEAN, finding_key="CRACK")
        second = _question(AnswerType.BOOLEAN, finding_key="CRACK")
        rows = [
            (_answer(value_bool=True), first, []),
            (_answer(value_bool=True), second, []),
        ]
        specs = build_finding_specs(rows)
        assert len(specs) == 2
        assert all(spec.finding_key == "CRACK" for spec in specs)
        assert len({spec.question_id for spec in specs}) == 2
