import { describe, expect, it } from 'vitest';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import type { MaterialCalc, MaterialLine } from '../types/materials';
import { areaFromSides, buyWord, calcSummary, needWord, positiveDecimal, unitWord } from './materialsFormat';

const line = (over: Partial<MaterialLine>): MaterialLine => ({
  code: 'TILE_ADHESIVE', name: 'Klej', quantity: '50.00', unit_text: 'kg', pack_size: '25', packs: 2, pieces: null, billing_unit: 'PCS', billing_quantity: '2.00', ...over,
});

describe('positiveDecimal', () => {
  it('takes a comma, limits the places and the size', () => {
    expect(positiveDecimal('12,5', 2, 100)).toBe('12.5');
    expect(positiveDecimal(' 30 ', 1, 1000)).toBe('30');
    expect(positiveDecimal('30,15', 1, 1000)).toBeNull();
    for (const bad of ['', '0', '-1', 'x', '1e3', '1.2.3', '101']) expect(positiveDecimal(bad, 2, 100)).toBeNull();
  });
});

describe('the words of a material line', () => {
  it('shows the packs to buy and the exact need with the size of a pack', () => {
    expect(buyWord(line({}), pl.materials)).toBe('2 szt.');
    expect(needWord(line({}), pl.materials)).toBe('potrzeba 50 kg · opak. 25 kg');
    expect(buyWord(line({}), ru.materials)).toBe('2 шт.');
    expect(needWord(line({}), ru.materials)).toBe('нужно 50 kg · упак. 25 kg');
  });

  it('shows the tile in square metres with the number of tiles, and no pack', () => {
    const tile = line({ code: 'TILE_TILES', quantity: '11.00', unit_text: 'm²', pack_size: null, packs: null, pieces: 62, billing_unit: 'M2', billing_quantity: '11.00' });
    expect(buyWord(tile, pl.materials)).toBe('11 m²');
    expect(needWord(tile, pl.materials)).toBe('potrzeba 11 m² · 62 płytek');
  });

  it('writes the pieces and the metres in the words of the screen, and the hangers (a pack of one) without a pack', () => {
    expect(unitWord('pcs', pl.materials)).toBe('szt.');
    expect(unitWord('m', ru.materials)).toBe('мп');
    expect(needWord(line({ code: 'GK_HANGERS', quantity: '15.00', unit_text: 'pcs', pack_size: '1', packs: 15 }), pl.materials)).toBe('potrzeba 15 szt.');
  });
});

describe('calcSummary', () => {
  const calc = (over: Partial<MaterialCalc>): MaterialCalc => ({
    id: 'c', room_id: 'r', package: 'TILE', title: null, params: { area_m2: '10.00', length_cm: '30.0', width_cm: '60.0' }, materials: [], created_at: '', updated_at: '', ...over,
  });
  it('tells the area and the size or the layers', () => {
    expect(calcSummary(calc({}), pl.materials)).toBe('10 m² · 30×60 cm');
    expect(calcSummary(calc({ package: 'DRYWALL', params: { kind: 'CEILING', area_m2: '8.50', layers: 2 } }), pl.materials)).toBe('sufit 8,5 m² · 2 warstw(y)');
    expect(calcSummary(calc({ package: 'DRYWALL', params: { kind: 'WALL', area_m2: '13.00', layers: 1 } }), ru.materials)).toBe('стена 13 м² · слоёв: 1');
  });
});

describe('areaFromSides', () => {
  it('multiplies in whole hundredths and rounds half up', () => {
    expect(areaFromSides('3,2', '4,5')).toBe('14.40');
    expect(areaFromSides('0,1', '0,1')).toBe('0.01');
    expect(areaFromSides('2.35', '1.1')).toBe('2.59'); // 2.585 -> 2.59, no float noise
    expect(areaFromSides('1000', '100')).toBe('100000.00');
  });
  it('is null for a side that is not a positive number, a third place, or an area over the limit', () => {
    expect(areaFromSides('', '3')).toBeNull();
    expect(areaFromSides('3', '0')).toBeNull();
    expect(areaFromSides('3', '2,555')).toBeNull();
    expect(areaFromSides('1000', '101')).toBeNull();
    expect(areaFromSides('0,01', '0,01')).toBeNull(); // 0.0001 rounds to zero
  });
});
