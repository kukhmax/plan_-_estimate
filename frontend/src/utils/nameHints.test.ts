/** UX walk: the Polish names of the typical items and of the materials show their meaning on a Russian / Ukrainian / English screen. */
import { describe, expect, it } from 'vitest';
import en from '../locales/en.json';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import uk from '../locales/uk.json';
import type { PriceItem } from '../types/priceItem';
import { materialNameHint, packNameHint, withPackHint } from './nameHints';
import { priceItemMatches } from './priceItemName';

describe('the meaning of a Polish name', () => {
  it('is given in Russian, Ukrainian and English and never in Polish', () => {
    expect(packNameHint(ru, 'Punkt wodny')).toBe('Точка водоснабжения');
    expect(packNameHint(uk, 'Punkt wodny')).toBe('Точка водопостачання');
    expect(packNameHint(en, 'Punkt wodny')).toBe('Water point');
    expect(packNameHint(pl, 'Punkt wodny')).toBeNull();
    expect(withPackHint(ru, 'Trasa rurowa')).toBe('Trasa rurowa (Трасса труб)');
    expect(withPackHint(pl, 'Trasa rurowa')).toBe('Trasa rurowa');
  });

  it('is not invented for a name the owner typed', () => {
    expect(packNameHint(ru, 'Moja pozycja')).toBeNull();
    expect(withPackHint(ru, 'Moja pozycja')).toBe('Moja pozycja');
    expect(packNameHint(ru, null)).toBeNull();
  });

  it('is given for the materials by their code', () => {
    expect(materialNameHint(ru, 'TILE_ADHESIVE', 'Klej do płytek (worek)')).toBe('Плиточный клей (мешок)');
    expect(materialNameHint(pl, 'TILE_ADHESIVE', 'Klej do płytek (worek)')).toBeNull();
    expect(materialNameHint(ru, 'UNKNOWN', 'Coś')).toBeNull();
  });

  it('lets the search of the price book find a typical item by its meaning', () => {
    const item = { id: 'i1', code: 'CUSTOM_1', name_key: null, display_name: 'Punkt wodny' } as unknown as PriceItem;
    expect(priceItemMatches(item, 'точка водо', [ru, pl])).toBe(true);
    expect(priceItemMatches(item, 'kanalizac', [ru, pl])).toBe(false);
  });
});
