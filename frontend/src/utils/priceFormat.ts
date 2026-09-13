/** Price Book money formatting (Stage 9D).
 *
 * Backend prices arrive as Decimal strings such as "9.99" / "45.50" / "0".
 * All formatting below is pure string/decimal-style manipulation: no float
 * arithmetic, so the stored precision is never changed for display.
 */

const PRICE_PATTERN = /^\d+(\.\d{1,2})?$/;
const TOO_MANY_DECIMALS = /^\d+\.\d{3,}$/;

/** Render a canonical Decimal string to a PLN display string with exactly two
 * decimals and a comma decimal separator (PL/RU). */
export function formatPrice(value: string | null | undefined): string {
  const cleaned = (value ?? '').trim();
  if (!cleaned) return '—';
  const [whole, fracRaw = ''] = cleaned.split('.');
  const frac = `${fracRaw}00`.slice(0, 2);
  return `${whole},${frac}`;
}

export type PriceInputReason = 'empty' | 'format' | 'negative' | 'precision';

export interface PriceInputState {
  ok: boolean;
  reason: PriceInputReason | null;
  /** Canonical dot-decimal value for API submission (e.g. "45.5"), or null. */
  value: string | null;
}

/** Validate a raw price input while preserving exactly what the user typed.
 *
 * Accepts 45 / 45.5 / 45.50 / 45,5 / 0 / 0.00 and normalizes comma → dot.
 * Rejects negative, malformed text, and anything with more than 2 decimal
 * places — the raw value is never rounded or truncated.
 */
export function normalizePriceInput(raw: string): PriceInputState {
  const trimmed = raw.trim();
  if (trimmed === '') return { ok: false, reason: 'empty', value: null };
  if (trimmed.startsWith('-')) return { ok: false, reason: 'negative', value: null };

  const normalized = trimmed.replace(',', '.');
  if (!PRICE_PATTERN.test(normalized)) {
    if (TOO_MANY_DECIMALS.test(normalized)) {
      return { ok: false, reason: 'precision', value: null };
    }
    return { ok: false, reason: 'format', value: null };
  }
  return { ok: true, reason: null, value: normalized };
}