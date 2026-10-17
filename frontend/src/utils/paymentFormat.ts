import type { PaymentKind } from '../types/payment';
import { formatPrice, normalizePriceInput } from './priceFormat';

/** The three tabs of the screen: invoices issued, money taken from the client, expenses on materials. */
export type PaymentTab = 'invoices' | 'client' | 'materials';

export function tabOf(kind: PaymentKind): PaymentTab {
  if (kind === 'INVOICE') return 'invoices';
  if (kind === 'EXPENSE') return 'materials';
  return 'client';
}

/** "1234,50 zł": the string the server sent, never counted on the phone. */
export function formatMoney(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : `${formatPrice(value)} zł`;
}

/** "17.10.2026" from "2026-10-17" without going through a Date (no shift of the day by a time zone). */
export function formatDay(iso: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  return match ? `${match[3]}.${match[2]}.${match[1]}` : '—';
}

/** Today in Poland as "YYYY-MM-DD": the default date of a new record. */
export function todayInPoland(now: Date = new Date()): string {
  return now.toLocaleDateString('sv-SE', { timeZone: 'Europe/Warsaw' });
}

/** The money field of a form: a positive amount with at most two places ("12,5" → "12.5"); `null` when it is not one. */
export function positiveAmount(raw: string): string | null {
  const state = normalizePriceInput(raw);
  return state.ok && state.value !== null && /[1-9]/.test(state.value) ? state.value : null;
}

/** An optional money field: empty is fine (`''`), otherwise a non-negative amount; `null` when it is filled badly. */
export function optionalAmount(raw: string): string | '' | null {
  if (raw.trim() === '') return '';
  const state = normalizePriceInput(raw);
  return state.ok ? state.value : null;
}

/** An optional VAT rate in percent, 0–100; the same shape as `optionalAmount`. */
export function optionalRate(raw: string): string | '' | null {
  const amount = optionalAmount(raw);
  if (amount === null || amount === '') return amount;
  return Number(amount) <= 100 ? amount : null;
}

/** A value for an input from a server money string ("1000.00" → "1000,00"). */
export function toInput(value: string | null | undefined): string {
  return (value ?? '').replace('.', ',');
}
