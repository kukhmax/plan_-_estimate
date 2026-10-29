/** V2-6 — the VAT setting of the executor profile and of an estimate. The backend owns the rule and the amounts. */
export type VatMode = 'EXEMPT' | 'RATE';

export interface VatSetting {
  vat_mode: VatMode | null;
  vat_rate_percent: number | null;
  /** only with a rate: the prices already include the VAT (it is taken out of the sum instead of being added on top) */
  vat_included?: boolean;
}

/** What a select shows: '' = not set, 'EXEMPT' = zw., '8' / '23' = the rate. */
export type VatChoice = '' | 'EXEMPT' | '8' | '23';

export const VAT_CHOICES: VatChoice[] = ['', 'EXEMPT', '8', '23'];

export function vatChoiceOf(setting: VatSetting): VatChoice {
  if (setting.vat_mode === 'EXEMPT') return 'EXEMPT';
  if (setting.vat_mode === 'RATE' && (setting.vat_rate_percent === 8 || setting.vat_rate_percent === 23)) {
    return String(setting.vat_rate_percent) as VatChoice;
  }
  return '';
}

export function vatSettingOf(choice: VatChoice, included = false): VatSetting {
  if (choice === 'EXEMPT') return { vat_mode: 'EXEMPT', vat_rate_percent: null };
  if (choice === '8' || choice === '23') return { vat_mode: 'RATE', vat_rate_percent: Number(choice), vat_included: included };
  return { vat_mode: null, vat_rate_percent: null };
}
