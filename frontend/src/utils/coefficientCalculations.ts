/**
 * Exact decimal arithmetic for price coefficients using BigInt.
 * No Number, parseFloat, toFixed, or Math.round.
 */

export interface CoefficientSummaryItem {
  percentage: string;
  is_base: boolean;
}

function parseSignedDecimal(s: string, scale: number): bigint {
  const trimmed = s.trim();
  const isNegative = trimmed.startsWith('-');
  const unsigned = isNegative ? trimmed.slice(1) : (trimmed.startsWith('+') ? trimmed.slice(1) : trimmed);
  const dotIndex = unsigned.indexOf('.');
  let intPart = unsigned;
  let fracPart = '';
  if (dotIndex !== -1) {
    intPart = unsigned.slice(0, dotIndex);
    fracPart = unsigned.slice(dotIndex + 1);
  }
  const paddedFrac = fracPart.padEnd(scale, '0').slice(0, scale);
  const factor = 10n ** BigInt(scale);
  const val = (BigInt(intPart || '0') * factor) + BigInt(paddedFrac || '0');
  return isNegative ? -val : val;
}

function bigIntToSignedDecimal(n: bigint, scale: number, minDecimals = 2): string {
  const isNegative = n < 0n;
  const absN = isNegative ? -n : n;
  const factor = 10n ** BigInt(scale);
  const intPart = absN / factor;
  const fracPart = (absN % factor).toString().padStart(scale, '0');

  // Trim trailing zeros beyond minDecimals
  let end = fracPart.length;
  while (end > minDecimals && fracPart[end - 1] === '0') {
    end--;
  }
  const trimmedFrac = fracPart.slice(0, end);
  const result = trimmedFrac.length > 0 ? `${intPart}.${trimmedFrac}` : intPart.toString();
  return isNegative ? `-${result}` : result;
}

/**
 * Exact additive sum of percentage strings (e.g. ["20.00", "10", "-5"] -> "25.00").
 */
export function sumPercentages(percentages: string[]): string {
  if (percentages.length === 0) return '0.00';
  const scale = 4;
  let totalBigInt = 0n;
  for (const p of percentages) {
    totalBigInt += parseSignedDecimal(p, scale);
  }
  return bigIntToSignedDecimal(totalBigInt, scale, 2);
}

/**
 * Exact comparison of two percentage strings: true when `percentage` is
 * strictly greater than `threshold` (e.g. "50.01" vs "50" -> true, "50.00" vs
 * "50" -> false).
 */
export function isPercentageAbove(percentage: string, threshold: string): boolean {
  const scale = 4;
  return parseSignedDecimal(percentage, scale) > parseSignedDecimal(threshold, scale);
}

/**
 * Format a percentage for user display, e.g. "+20%", "-5%", "0%".
 */
export function formatPercentageDisplay(percentage: string): string {
  const scale = 4;
  const val = parseSignedDecimal(percentage, scale);
  if (val === 0n) return '0%';
  const isPositive = val > 0n;
  const absVal = isPositive ? val : -val;
  const factor = 10n ** BigInt(scale);
  const intPart = absVal / factor;
  const fracPart = (absVal % factor).toString().padStart(scale, '0');

  // Trim trailing zeros completely for display: 20.0000 -> 20, 20.5000 -> 20.5
  let end = fracPart.length;
  while (end > 0 && fracPart[end - 1] === '0') {
    end--;
  }
  const fracStr = end > 0 ? `.${fracPart.slice(0, end)}` : '';
  const numStr = `${intPart}${fracStr}`;
  return isPositive ? `+${numStr}%` : `-${numStr}%`;
}

/**
 * Calculate effective unit price from base price and total percentage adjustment.
 * Formula: base * (1 + total_percentage / 100)
 *
 * Rules:
 * - basePrice === null -> returns null ("Do ustalenia" invariant)
 * - Result is quantized to 2 decimal places using HALF_UP rounding
 * - Total percentage < -100% -> returns null (or invalid)
 */
export function calculateEffectivePrice(
  basePrice: string | null,
  totalPercentage: string,
): string | null {
  if (basePrice === null) return null;

  const scale = 6;
  const baseBigInt = parseSignedDecimal(basePrice, scale);
  if (baseBigInt < 0n) return null;

  // totalPercentage in percent: 30% -> 30 * 10^6
  const pctBigInt = parseSignedDecimal(totalPercentage, scale);
  const hundredPctBigInt = 100n * (10n ** BigInt(scale)); // 100%
  const multiplierNumerator = hundredPctBigInt + pctBigInt; // (100 + pct) * 10^scale

  if (multiplierNumerator < 0n) {
    // Below -100% is invalid
    return null;
  }

  // baseBigInt is base * 10^scale
  // multiplierNumerator is (100 + pct) * 10^scale
  // product is base * (100 + pct) * 10^(2*scale)
  // We need to divide by 100 * 10^(2*scale) to get real value.
  // We want result with 2 decimal places (scale 2), so we multiply by 100 (10^2) before dividing.
  // target = (base * (100 + pct) / 100) * 10^2 = base * (100 + pct)
  // product = baseBigInt * multiplierNumerator  [scale: 2 * scale]
  // divisor = 100n * (10n ** BigInt(2 * scale - 2)) = 10n ** BigInt(2 * scale)
  const product = baseBigInt * multiplierNumerator;
  // product is base * (100 + pct) * 10^(2 * scale)
  // real cents = base * (100 + pct)
  // Therefore divisor to reach cents is 10^(2 * scale):
  const centsDivisor = 10n ** BigInt(2 * scale);

  // HALF_UP rounding to cents:
  const cents = (product + (centsDivisor / 2n)) / centsDivisor;

  const factor = 100n;
  const intPart = cents / factor;
  const fracPart = (cents % factor).toString().padStart(2, '0');
  return `${intPart}.${fracPart}`;
}

/**
 * Returns a compact badge summary for an occurrence's coefficient options,
 * e.g. "+30%" if there is a net adjustment.
 * Returns null if no options or only 0% options selected.
 */
export function formatCoefficientSummary(
  options?: Array<{ percentage: string; is_base?: boolean }> | null,
): string | null {
  if (!options || options.length === 0) return null;
  const total = sumPercentages(options.map((o) => o.percentage));
  const scale = 4;
  const val = parseSignedDecimal(total, scale);
  if (val === 0n) {
    // If there is an explicit base option (is_base === true), return "0%" or "+0%"
    const hasExplicitBase = options.some((o) => o.is_base);
    return hasExplicitBase ? '0%' : null;
  }
  return formatPercentageDisplay(total);
}
