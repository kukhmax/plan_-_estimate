import { useI18n } from '../hooks/useI18n';
import type { ContractQuestion, PremisesRequirement } from '../types/contractCatalog';
import type { ProjectRepresentative } from '../types/representative';
import { FieldValue, RequirementField } from '../utils/contractAnswers';

const FIELD = 'w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-base pe-surface text-slate-900';
const NUMERIC_KINDS = new Set(['NUMBER', 'PERCENT', 'DAYS', 'MONTHS']);

interface ContractQuestionInputProps {
  question: ContractQuestion;
  value: FieldValue | undefined;
  requirements: PremisesRequirement[];
  /** The persons of the object who may accept the work and sign (a PERSON_LIST question only). */
  authorised?: ProjectRepresentative[];
  onChange: (value: FieldValue) => void;
}

/** One question of the contract's questionnaire, drawn by its kind: the contract (16E.1) and "Moje standardowe warunki umowy" (B2). */
export function ContractQuestionInput({ question, value, requirements, authorised = [], onChange }: ContractQuestionInputProps) {
  const { t } = useI18n();
  const text = t.contract;
  const catalogText = t.contractCatalog;
  const unit = (u: string | null) => (u ? catalogText.units[u as keyof typeof catalogText.units] ?? u : null);
  const patchRequirement = (requirement: string, patch: Partial<RequirementField>) => {
    const all = (value ?? {}) as Record<string, RequirementField>;
    onChange({ ...all, [requirement]: { ...all[requirement], ...patch } });
  };
  const aria = `contract-q-${question.key}`;
  switch (question.kind) {
    case 'PERSON_LIST': {
      const chosen = (value as string[]) ?? [];
      return authorised.length === 0 ? (
        <p className="text-sm text-amber-800 break-words">{text.persons_none}</p>
      ) : (
        <div className="space-y-1">
          {authorised.map((person) => (
            <label key={person.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
              <input
                type="checkbox"
                aria-label={`${aria}-${person.id}`}
                className="h-5 w-5 shrink-0"
                checked={chosen.includes(person.id)}
                onChange={() => onChange(chosen.includes(person.id) ? chosen.filter((x) => x !== person.id) : [...chosen, person.id])}
              />
              <span className="min-w-0 break-words">
                {person.name}
                {person.role_title ? ` · ${person.role_title}` : ''}
              </span>
            </label>
          ))}
        </div>
      );
    }
    case 'YES_NO':
      return (
        <select aria-label={aria} value={value as string} onChange={(e) => onChange(e.target.value)} className={FIELD}>
          <option value="">{text.not_set}</option>
          <option value="yes">{text.yes}</option>
          <option value="no">{text.no}</option>
        </select>
      );
    case 'CHOICE':
      return (
        <select aria-label={aria} value={value as string} onChange={(e) => onChange(e.target.value)} className={FIELD}>
          <option value="">{text.not_set}</option>
          {(question.options ?? []).map((option) => (
            <option key={option} value={option}>
              {catalogText.choices[option as keyof typeof catalogText.choices] ?? option}
            </option>
          ))}
        </select>
      );
    case 'REQUIREMENT_VALUES':
      return (
        <div className="space-y-3">
          {requirements.map((requirement) => {
            const entry = ((value as Record<string, RequirementField>) ?? {})[requirement.key];
            const requirementLabel = catalogText.requirements[requirement.key as keyof typeof catalogText.requirements] ?? requirement.key;
            const suffix = unit(requirement.unit);
            return (
              <div key={requirement.key} className="space-y-1">
                <span className="block text-xs font-medium text-slate-700 break-words">{requirementLabel}{suffix ? ` (${suffix})` : ''}</span>
                {requirement.value_kind === 'YES_NO' && (
                  <select aria-label={`contract-r-${requirement.key}`} value={entry?.yesNo ?? ''} onChange={(e) => patchRequirement(requirement.key, { yesNo: e.target.value as RequirementField['yesNo'] })} className={FIELD}>
                    <option value="">{text.not_set}</option>
                    <option value="yes">{text.yes}</option>
                    <option value="no">{text.no}</option>
                  </select>
                )}
                {requirement.value_kind === 'NUMBER' && (
                  <input aria-label={`contract-r-${requirement.key}`} inputMode="decimal" value={entry?.value ?? ''} onChange={(e) => patchRequirement(requirement.key, { value: e.target.value })} className={FIELD} />
                )}
                {requirement.value_kind === 'NUMBER_RANGE' && (
                  <div className="grid grid-cols-2 gap-2">
                    <input aria-label={`contract-r-${requirement.key}-min`} placeholder={text.range_min} inputMode="decimal" value={entry?.min ?? ''} onChange={(e) => patchRequirement(requirement.key, { min: e.target.value })} className={FIELD} />
                    <input aria-label={`contract-r-${requirement.key}-max`} placeholder={text.range_max} inputMode="decimal" value={entry?.max ?? ''} onChange={(e) => patchRequirement(requirement.key, { max: e.target.value })} className={FIELD} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      );
    case 'DATE':
      return <input aria-label={aria} type="date" value={value as string} onChange={(e) => onChange(e.target.value)} className={FIELD} />;
    default: {
      const suffix = unit(question.unit);
      return (
        <div className="flex items-center gap-2">
          <input
            aria-label={aria}
            value={value as string}
            inputMode={question.kind === 'MONEY_PLN' ? 'decimal' : NUMERIC_KINDS.has(question.kind) ? 'numeric' : 'text'}
            onChange={(e) => onChange(e.target.value)}
            className={FIELD}
          />
          {suffix && <span className="shrink-0 text-sm text-slate-600">{suffix}</span>}
        </div>
      );
    }
  }
}
