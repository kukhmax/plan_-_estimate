import type { MaterialCalc, MaterialLine } from '../types/materials';
import { formatPlain } from './paymentFormat';

interface UnitWords {
  unit_pcs: string;
  unit_lm: string;
}

interface LineWords extends UnitWords {
  unit_m2: string;
  pack_of: string;
  tiles_n: string;
  need: string;
}

/** A positive decimal of a form field with at most `places` places ("12,5" -> "12.5"); `null` when it is not one. The server checks the same limits. */
export function positiveDecimal(raw: string, places: number, max: number): string | null {
  const text = raw.trim().replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(text)) return null;
  const [, fraction = ''] = text.split('.');
  if (fraction.length > places) return null;
  const value = Number(text);
  return value > 0 && value <= max ? text : null;
}

/** The unit of the server's text ("m²", "kg", "pcs", "m") in the words of the screen; the weight stays kg. */
export function unitWord(unitText: string, words: UnitWords & { unit_m2: string }): string {
  if (unitText === 'pcs') return words.unit_pcs;
  if (unitText === 'm') return words.unit_lm;
  if (unitText === 'm²') return words.unit_m2;
  return unitText;
}

/** What to buy: the whole packs or the area, as the big number of a row. */
export function buyWord(line: MaterialLine, words: LineWords): string {
  return `${formatPlain(line.billing_quantity)} ${line.billing_unit === 'M2' ? words.unit_m2 : words.unit_pcs}`;
}

/** The small line under it: the exact need, the size of a pack, the number of tiles. Nothing is counted here: the server sent the numbers. */
export function needWord(line: MaterialLine, words: LineWords): string {
  const unit = unitWord(line.unit_text, words);
  const parts = [words.need.replace('{q}', formatPlain(line.quantity)).replace('{unit}', unit)];
  if (line.pack_size !== null && line.pack_size !== '1') parts.push(words.pack_of.replace('{size}', formatPlain(line.pack_size)).replace('{unit}', unit));
  if (line.pieces !== null) parts.push(words.tiles_n.replace('{n}', String(line.pieces)));
  return parts.join(' · ');
}

interface SummaryWords {
  summary_tile: string;
  summary_wall: string;
  summary_ceiling: string;
}

/** One line about the data of a calculation: its area and what it is made of. */
export function calcSummary(calc: MaterialCalc, words: SummaryWords): string {
  const p = calc.params;
  if (calc.package === 'TILE') {
    return words.summary_tile.replace('{area}', formatPlain(p.area_m2)).replace('{l}', formatPlain(p.length_cm)).replace('{w}', formatPlain(p.width_cm));
  }
  return (p.kind === 'CEILING' ? words.summary_ceiling : words.summary_wall).replace('{area}', formatPlain(p.area_m2)).replace('{n}', String(p.layers ?? 1));
}
