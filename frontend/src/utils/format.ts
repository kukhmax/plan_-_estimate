/** The decimal comma of PL and RU for DISPLAY only: "78.37" -> "78,37". The data, the API and the calculations keep the dot. */
export function commaDecimal(text: string): string {
  return text.replace('.', ',');
}

/** What a person typed ("12,5", " 12.5 ") as the dot text the API takes ("12.5"). */
export function dotDecimal(text: string): string {
  return text.trim().replace(',', '.');
}

export function formatMetric(
  value: string | number | null | undefined,
  decimals = 2,
): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = typeof value === 'number' ? value : Number(value);
  if (Number.isNaN(num)) return '—';
  return commaDecimal(num.toFixed(decimals));
}

/**
 * Format a backend Decimal money string for display only.
 * Operates on the string representation without any floating-point arithmetic.
 * Pads or truncates fractional digits to exactly 2 for display.
 * "1234.5" → "1234,50"  "0" → "0,00"  null → "—" (the decimal comma of PL and RU)
 */
export function formatDecimalMoney(value: string | null): string {
  if (value === null) return '—';
  const dot = value.indexOf('.');
  if (dot === -1) return `${value},00`;
  const intPart = value.slice(0, dot);
  const frac = value.slice(dot + 1);
  if (frac.length === 0) return `${intPart},00`;
  if (frac.length === 1) return `${intPart},${frac}0`;
  return `${intPart},${frac.slice(0, 2)}`;
}

// ---------------------------------------------------------------------------
// Usability U-8 / U-10 -- exact decimal display (no floats): quantities by unit, and the difference of two money strings.
// ---------------------------------------------------------------------------

/** Rounds a non-negative decimal string half-up to `decimals` digits, exactly (BigInt, no floating point). */
function roundDecimalString(value: string, decimals: number): string {
  const [intPart = '0', fracPart = ''] = value.split('.');
  const padded = fracPart.padEnd(decimals + 1, '0');
  const scaled = BigInt(intPart + padded.slice(0, decimals)) + (Number(padded[decimals]) >= 5 ? 1n : 0n);
  if (decimals === 0) return scaled.toString();
  const text = scaled.toString().padStart(decimals + 1, '0');
  return `${text.slice(0, -decimals)}.${text.slice(-decimals)}`;
}

/** How many decimals a quantity shows by unit: areas and lengths 2, hours and days 1, pieces and lump sums whole. */
const QUANTITY_DECIMALS: Record<string, number> = { M2: 2, LM: 2, HOUR: 1, DAY: 1, PCS: 0, FLAT: 0 };

/**
 * A quantity of an estimate line for DISPLAY ("78.374" m² → "78.37"). The server keeps its three decimals; the sum of a line is shown as
 * it arrives and is never recalculated from this text. An unknown unit keeps its digits (only the comma is applied); a value that is not a decimal is returned as it came.
 */
export function formatQuantity(value: string, unit: string | null): string {
  const decimals = unit !== null ? QUANTITY_DECIMALS[unit] : undefined;
  if (decimals === undefined || !/^\d+(\.\d+)?$/.test(value)) return /^-?\d+\.\d+$/.test(value) ? commaDecimal(value) : value;
  return commaDecimal(roundDecimalString(value, decimals));
}

function toCents(value: string): bigint {
  const negative = value.startsWith('-');
  const [intPart, fracPart = ''] = value.replace('-', '').split('.');
  const cents = BigInt(intPart + fracPart.padEnd(2, '0').slice(0, 2));
  return negative ? -cents : cents;
}

/** `to - from` of two money strings as a signed two-decimal string ("+1183.59", "-12.00", "0.00"): the change a regeneration would bring. */
export function signedMoneyDifference(from: string, to: string): string {
  const cents = toCents(to) - toCents(from);
  const sign = cents > 0n ? '+' : cents < 0n ? '-' : '';
  const abs = cents < 0n ? -cents : cents;
  const text = abs.toString().padStart(3, '0');
  return `${sign}${text.slice(0, -2)},${text.slice(-2)}`;
}
