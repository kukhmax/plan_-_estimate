"""Pure domain rules for the inspection checklist engine (Stage 6).

Stage 6 records facts only. These rules decide which factual observations are
materialized as findings and which quality targets are valid for a substrate.
Risk interpretation is deliberately out of scope (Stage 7).
"""
from dataclasses import dataclass
import uuid

from app.domain.exceptions import QualityScaleMismatchError
from app.models.checklist import (
    AnswerType,
    ChecklistOption,
    ChecklistQuestion,
    QualityLevel,
    Substrate,
)
from app.models.inspection import InspectionAnswer

S_LEVELS: frozenset[QualityLevel] = frozenset(
    {QualityLevel.S1, QualityLevel.S2, QualityLevel.S3, QualityLevel.S4}
)
Q_LEVELS: frozenset[QualityLevel] = frozenset(
    {QualityLevel.Q1, QualityLevel.Q2, QualityLevel.Q3, QualityLevel.Q4}
)

# Substrates whose agreed quality target must use the S scale (plasters/concrete).
_S_SCALE_SUBSTRATES: frozenset[Substrate] = frozenset(
    {
        Substrate.CONCRETE,
        Substrate.GYPSUM_PLASTER,
        Substrate.CEMENT_LIME_PLASTER,
    }
)
# Substrates whose agreed quality target must use the Q scale (drywall).
_Q_SCALE_SUBSTRATES: frozenset[Substrate] = frozenset({Substrate.GYPSUM_BOARD})


def assert_quality_scale_valid(
    substrate: Substrate,
    quality_target: QualityLevel | None,
) -> None:
    """Validate the agreed quality target against the substrate's quality family.

    GYPSUM_BOARD -> Q scale only; concrete/gypsum/cement-lime plaster -> S scale
    only. PAINTED and OTHER are not yet restricted to a family. None is always
    allowed (no target agreed yet).
    """
    if quality_target is None:
        return
    if substrate in _Q_SCALE_SUBSTRATES:
        if quality_target not in Q_LEVELS:
            raise QualityScaleMismatchError(
                f"Substrate {substrate.value} requires a Q-scale quality target, "
                f"got {quality_target.value}"
            )
        return
    if substrate in _S_SCALE_SUBSTRATES:
        if quality_target not in S_LEVELS:
            raise QualityScaleMismatchError(
                f"Substrate {substrate.value} requires an S-scale quality target, "
                f"got {quality_target.value}"
            )


@dataclass(frozen=True)
class FindingSpec:
    """A factual finding to create or reconcile on inspection completion."""

    finding_key: str
    label_key: str
    value_snapshot: dict
    answer_id: uuid.UUID | None
    question_id: uuid.UUID | None


def _choice_option(
    options: list[ChecklistOption],
    option_key: str | None,
) -> ChecklistOption | None:
    if option_key is None:
        return None
    return next((opt for opt in options if opt.key == option_key), None)


def build_finding_specs(
    rows: list[tuple[InspectionAnswer, ChecklistQuestion, list[ChecklistOption]]],
) -> list[FindingSpec]:
    """Materialize findings only from explicitly configured finding keys.

    A NUMBER question without a finding_key never yields a finding, and a
    positive number alone is never a generic finding. Facts become findings only
    when the question or the selected option carries a finding_key.
    """
    specs: list[FindingSpec] = []
    for answer, question, options in rows:
        if question.answer_type == AnswerType.BOOLEAN:
            if answer.value_bool is True and question.finding_key:
                specs.append(
                    FindingSpec(
                        finding_key=question.finding_key,
                        label_key=question.text_key,
                        value_snapshot={"bool": True},
                        answer_id=answer.id,
                        question_id=question.id,
                    )
                )

        elif question.answer_type == AnswerType.NUMBER:
            if answer.value_number is not None and question.finding_key:
                specs.append(
                    FindingSpec(
                        finding_key=question.finding_key,
                        label_key=question.text_key,
                        value_snapshot={"number": str(answer.value_number)},
                        answer_id=answer.id,
                        question_id=question.id,
                    )
                )

        elif question.answer_type == AnswerType.TEXT:
            if answer.value_text and question.finding_key:
                specs.append(
                    FindingSpec(
                        finding_key=question.finding_key,
                        label_key=question.text_key,
                        value_snapshot={"text": answer.value_text},
                        answer_id=answer.id,
                        question_id=question.id,
                    )
                )

        elif question.answer_type == AnswerType.SINGLE_CHOICE:
            option = _choice_option(options, answer.option_key)
            if option and option.finding_key:
                specs.append(
                    FindingSpec(
                        finding_key=option.finding_key,
                        label_key=option.label_key,
                        value_snapshot={"option": option.key},
                        answer_id=answer.id,
                        question_id=question.id,
                    )
                )

        elif question.answer_type == AnswerType.MULTI_CHOICE:
            selected_keys = answer.option_keys or []
            for option in options:
                if option.key in selected_keys and option.finding_key:
                    specs.append(
                        FindingSpec(
                            finding_key=option.finding_key,
                            label_key=option.label_key,
                            value_snapshot={"option": option.key},
                            answer_id=answer.id,
                            question_id=question.id,
                        )
                    )

    return specs