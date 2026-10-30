/** V2-6 — the VAT setting of the executor profile and of an estimate. The backend owns the rule and the amounts. */
export type VatMode = 'EXEMPT' | 'RATE';

export interface VatSetting {
  vat_mode: VatMode | null;
  vat_rate_percent: number | null;
  /** only with a rate: the prices already include the VAT (it is taken out of the sum instead of being added on top) */
  vat_included?: boolean;
}

/** What a select shows: '' = not set, 'EXEMPT' = zw., '8' / '23' = the usual rates, 'CUSTOM' = an own rate (owner 2026-10-30). */
export type VatChoice = '' | 'EXEMPT' | '8' | '23' | 'CUSTOM';

export const VAT_CHOICES: VatChoice[] = ['', 'EXEMPT', '8', '23', 'CUSTOM'];

export function vatChoiceOf(setting: VatSetting): VatChoice {
  if (setting.vat_mode === 'EXEMPT') return 'EXEMPT';
  if (setting.vat_mode === 'RATE' && (setting.vat_rate_percent === 8 || setting.vat_rate_percent === 23)) {
    return String(setting.vat_rate_percent) as VatChoice;
  }
  if (setting.vat_mode === 'RATE' && setting.vat_rate_percent !== null) return 'CUSTOM';
  return '';
}

/** The own rate typed by the owner: a whole percent from 0 to 100 (the backend takes no other); `null` when it is not one. */
export function parseCustomRate(raw: string): number | null {
  const text = raw.trim();
  if (!/^\d{1,3}$/.test(text)) return null;
  const value = Number(text);
  return value >= 0 && value <= 100 ? value : null;
}

export function customVatSetting(rate: number, included = false): VatSetting {
  return { vat_mode: 'RATE', vat_rate_percent: rate, vat_included: included };
}

export function vatSettingOf(choice: VatChoice, included = false): VatSetting {
  if (choice === 'EXEMPT') return { vat_mode: 'EXEMPT', vat_rate_percent: null };
  if (choice === '8' || choice === '23') return { vat_mode: 'RATE', vat_rate_percent: Number(choice), vat_included: included };
  return { vat_mode: null, vat_rate_percent: null };
}
