export function formatMetric(
  value: string | number | null | undefined,
  decimals = 2,
): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = typeof value === 'number' ? value : Number(value);
  if (Number.isNaN(num)) return '—';
  return num.toFixed(decimals);
}

/**
 * Format a backend Decimal money string for display only.
 * Operates on the string representation without any floating-point arithmetic.
 * Pads or truncates fractional digits to exactly 2 for display.
 * "1234.5" → "1234.50"  "0" → "0.00"  null → "—"
 */
export function formatDecimalMoney(value: string | null): string {
  if (value === null) return '—';
  const dot = value.indexOf('.');
  if (dot === -1) return `${value}.00`;
  const intPart = value.slice(0, dot);
  const frac = value.slice(dot + 1);
  if (frac.length === 0) return `${intPart}.00`;
  if (frac.length === 1) return `${intPart}.${frac}0`;
  return `${intPart}.${frac.slice(0, 2)}`;
}
