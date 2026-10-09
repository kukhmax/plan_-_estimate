import type { AnswerValue, RequirementAnswer } from '../types/contract';
import type { ContractQuestion, PremisesRequirement } from '../types/contractCatalog';

/** What a field of the questionnaire holds while it is edited: text for the simple kinds, a tri-state for yes/no, the chosen
 * persons, and one small entry per requirement. */
export interface RequirementField {
  yesNo: '' | 'yes' | 'no';
  value: string;
  min: string;
  max: string;
}
export type FieldValue = string | string[] | Record<string, RequirementField>;

const NUMERIC = new Set(['NUMBER', 'PERCENT', 'DAYS', 'MONTHS']);
const emptyRequirement = (): RequirementField => ({ yesNo: '', value: '', min: '', max: '' });

function numberText(value: unknown): string {
  return typeof value === 'number' ? String(value) : '';
}

export function toField(question: ContractQuestion, answer: AnswerValue | undefined, requirements: PremisesRequirement[]): FieldValue {
  switch (question.kind) {
    case 'PERSON_LIST':
      return Array.isArray(answer) ? answer : [];
    case 'YES_NO':
      return typeof answer === 'boolean' ? (answer ? 'yes' : 'no') : '';
    case 'REQUIREMENT_VALUES': {
      const stored = (answer && typeof answer === 'object' && !Array.isArray(answer) ? answer : {}) as Record<string, RequirementAnswer>;
      return Object.fromEntries(
        requirements.map((requirement) => {
          const entry = stored[requirement.key];
          const field = emptyRequirement();
          if (typeof entry === 'boolean') field.yesNo = entry ? 'yes' : 'no';
          else if (typeof entry === 'number') field.value = String(entry);
          else if (entry && typeof entry === 'object') {
            field.min = numberText(entry.min);
            field.max = numberText(entry.max);
          }
          return [requirement.key, field];
        }),
      );
    }
    default:
      if (typeof answer === 'string') return answer;
      return numberText(answer);
  }
}

/** A decimal typed on a phone: "3,5" and "3.5" are the same number; anything else is not a number. */
function parseNumber(text: string): number | null {
  const clean = text.trim().replace(',', '.');
  if (clean === '' || !/^-?\d+(\.\d+)?$/.test(clean)) return null;
  return Number(clean);
}

/** The answer a field stands for, or null when it is empty. An entry that is not a number is passed on as typed, so the server
 * names the question instead of the screen guessing. */
export function toAnswer(question: ContractQuestion, field: FieldValue, requirements: PremisesRequirement[]): AnswerValue | null {
  if (question.kind === 'PERSON_LIST') return (field as string[]).length > 0 ? (field as string[]) : null;
  if (question.kind === 'YES_NO') return field === 'yes' ? true : field === 'no' ? false : null;
  if (question.kind === 'REQUIREMENT_VALUES') {
    const fields = field as Record<string, RequirementField>;
    const result: Record<string, RequirementAnswer> = {};
    for (const requirement of requirements) {
      const entry = fields[requirement.key];
      if (!entry) continue;
      if (requirement.value_kind === 'YES_NO') {
        if (entry.yesNo) result[requirement.key] = entry.yesNo === 'yes';
      } else if (requirement.value_kind === 'NUMBER') {
        if (entry.value.trim() !== '') result[requirement.key] = parseNumber(entry.value) ?? (entry.value as unknown as number);
      } else if (entry.min.trim() !== '' || entry.max.trim() !== '') {
        result[requirement.key] = {
          min: parseNumber(entry.min) ?? (entry.min as unknown as number),
          max: parseNumber(entry.max) ?? (entry.max as unknown as number),
        };
      }
    }
    return Object.keys(result).length > 0 ? result : null;
  }
  const text = (field as string).trim();
  if (text === '') return null;
  if (NUMERIC.has(question.kind)) return parseNumber(text) ?? (text as unknown as number);
  return text;
}

export function sameAnswer(a: AnswerValue | null | undefined, b: AnswerValue | null | undefined): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}
