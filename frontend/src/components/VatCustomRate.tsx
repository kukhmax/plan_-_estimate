import { useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { parseCustomRate } from '../utils/vat';
import { Ico } from './Ico';

interface VatCustomRateProps {
  /** The own rate the setting has now (null while none). */
  value: number | null;
  disabled?: boolean;
  /** The screens that save later (the profile) take the rate while it is typed; the others wait for the button. */
  live?: boolean;
  idPrefix: string;
  onApply: (rate: number) => void;
}

/** An own VAT rate: a whole percent from 0 to 100 (owner 2026-10-30). The standard 8 % and 23 % stay in the select. */
export function VatCustomRate({ value, disabled, live, idPrefix, onApply }: VatCustomRateProps) {
  const { t } = useI18n();
  const [raw, setRaw] = useState(value === null ? '' : String(value));
  const [invalid, setInvalid] = useState(false);

  const apply = (text: string) => {
    const rate = parseCustomRate(text);
    setInvalid(text.trim() !== '' && rate === null);
    if (rate !== null) onApply(rate);
  };

  return (
    <div aria-label={`${idPrefix}-custom`} className="flex flex-col gap-1">
      <label htmlFor={`${idPrefix}-custom-input`} className="text-xs font-medium text-slate-500 break-words">{t.vat.custom_label}</label>
      <div className="flex items-center gap-2">
        <input
          id={`${idPrefix}-custom-input`}
          aria-label={`${idPrefix}-custom-input`}
          inputMode="numeric"
          autoComplete="off"
          maxLength={3}
          value={raw}
          disabled={disabled}
          placeholder="5"
          aria-invalid={invalid ? true : undefined}
          onChange={(event) => {
            setRaw(event.target.value);
            if (live) apply(event.target.value);
            else setInvalid(false);
          }}
          className="min-h-11 w-24 shrink-0 px-3 text-base text-center rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-control-bg-color)] text-[var(--tg-control-text-color)]"
        />
        <span className="text-sm text-slate-600">%</span>
        {!live && (
          <button
            type="button"
            aria-label={`${idPrefix}-custom-apply`}
            disabled={disabled}
            onClick={() => apply(raw)}
            className="min-h-11 flex-1 px-3 text-sm font-semibold rounded-xl bg-blue-600 text-white disabled:opacity-50 break-words"
          >
            <Ico>✔️</Ico>{t.vat.custom_apply}
          </button>
        )}
      </div>
      {invalid && <p role="alert" className="text-xs font-medium text-red-600 break-words">{t.vat.custom_invalid}</p>}
    </div>
  );
}
