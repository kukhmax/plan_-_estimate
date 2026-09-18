/**
 * Exact decimal string arithmetic using BigInt.
 * No Number, parseFloat, toFixed, or Math.round anywhere in this file.
 * Inputs must be non-negative decimal strings (e.g. "12.500", "319.41", "0").
 */

function countDecimals(s: string): number {
  const idx = s.indexOf('.');
  return idx === -1 ? 0 : s.length - idx - 1;
}

function scaleToBigInt(s: string, scale: number): bigint {
  const idx = s.indexOf('.');
  if (idx === -1) {
    return BigInt(s) * (10n ** BigInt(scale));
  }
  const intPart = s.slice(0, idx) || '0';
  const fracPart = s.slice(idx + 1).padEnd(scale, '0').slice(0, scale);
  return BigInt(intPart) * (10n ** BigInt(scale)) + BigInt(fracPart);
}

function bigIntToDecimal(n: bigint, scale: number): string {
  if (scale === 0) return n.toString();
  const factor = 10n ** BigInt(scale);
  const intPart = n / factor;
  const fracPart = n % factor;
  return `${intPart}.${fracPart.toString().padStart(scale, '0')}`;
}

/** Adds two non-negative decimal strings exactly, preserving max input scale. */
export function addDecimalStrings(a: string, b: string): string {
  const scale = Math.max(countDecimals(a), countDecimals(b));
  return bigIntToDecimal(scaleToBigInt(a, scale) + scaleToBigInt(b, scale), scale);
}

/** Sums a non-empty array of non-negative decimal strings exactly. */
export function sumDecimalStrings(values: string[]): string {
  return values.reduce(addDecimalStrings);
}
