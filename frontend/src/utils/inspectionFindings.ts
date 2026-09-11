import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { InspectionAnswerPayload } from '../types/inspection';

const Q_LEVELS: QualityLevelValue[] = ['Q1', 'Q2', 'Q3', 'Q4'];
const S_LEVELS: QualityLevelValue[] = ['S1', 'S2', 'S3', 'S4'];

/**
 * Quality levels offered for a substrate, mirroring the backend scale rule.
 * PAINTED/OTHER have no forced family (undefined = quality target is optional).
 */
export function qualityLevelsForSubstrate(
  substrate: SubstrateValue,
): QualityLevelValue[] | undefined {
  if (substrate === 'GYPSUM_BOARD') return Q_LEVELS;
  if (
    substrate === 'CONCRETE' ||
    substrate === 'GYPSUM_PLASTER' ||
    substrate === 'CEMENT_LIME_PLASTER'
  ) {
    return S_LEVELS;
  }
  return undefined;
}

/** Count of answered questions, used for the review/complete step. */
export function answeredQuestionCount(answers: InspectionAnswerPayload[]): number {
  return answers.filter((a) => {
    if (a.value_bool !== undefined && a.value_bool !== null) return true;
    if (a.value_number !== undefined && a.value_number !== null) return true;
    if (a.value_text) return true;
    if (a.option_key) return true;
    if (a.option_keys && a.option_keys.length > 0) return true;
    return false;
  }).length;
}