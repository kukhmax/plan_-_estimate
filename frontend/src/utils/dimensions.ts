/**
 * Dimensions are typed in centimetres (no decimal point to hunt for on a phone) and travel everywhere else in metres.
 * The conversion shifts the decimal point of the TEXT, so it never goes through floating point: "250" -> "2.5", "25.5" -> "0.255".
 */

const CM_PATTERN = /^-?\d*\.?\d*$/;

/** What the owner typed (centimetres, "," or "." for the fraction) as a text of metres; '' when empty; the raw text when it is no number. */
export function cmToMeters(typed: string): string {
  const text = typed.trim().replace(',', '.');
  if (text === '') return '';
  if (!CM_PATTERN.test(text) || text === '-' || text === '.' || text === '-.') return typed;
  const negative = text.startsWith('-');
  const [rawInt, rawFrac = ''] = text.replace('-', '').split('.');
  const digits = (rawInt === '' ? '0' : rawInt).padStart(3, '0');
  const whole = digits.slice(0, -2).replace(/^0+(?=\d)/, '');
  const fraction = (digits.slice(-2) + rawFrac).replace(/0+$/, '');
  const meters = fraction === '' ? whole : `${whole}.${fraction}`;
  return negative && meters !== '0' ? `-${meters}` : meters;
}

/** A text of metres ("2.500", 2.5) as the centimetres shown in the field: "250". */
export function metersToCm(meters: string | number | null | undefined): string {
  if (meters === null || meters === undefined) return '';
  const text = String(meters).trim();
  if (text === '' || !/^-?\d*\.?\d*$/.test(text) || text === '-' || text === '.') return text;
  const negative = text.startsWith('-');
  const [rawInt, rawFrac = ''] = text.replace('-', '').split('.');
  const frac = rawFrac.padEnd(2, '0');
  const whole = ((rawInt === '' ? '0' : rawInt) + frac.slice(0, 2)).replace(/^0+(?=\d)/, '');
  const rest = frac.slice(2).replace(/0+$/, '');
  const cm = rest === '' ? whole : `${whole}.${rest}`;
  return negative && cm !== '0' ? `-${cm}` : cm;
}

/** At most one digit after the point (a millimetre): the backend keeps three decimals of a metre. */
export function sanitizeCm(typed: string): string {
  const text = typed.replace(',', '.');
  const point = text.indexOf('.');
  return point === -1 ? text : text.slice(0, point + 2);
}
