import { describe, expect, it } from 'vitest';
import type { PriceItem } from '../types/priceItem';
import { foldForSearch, priceItemMatches, priceItemRank } from './priceItemName';

const ITEM = (over: Partial<PriceItem> = {}): PriceItem => ({
  id: 'i', code: 'CENNIK_SKIM_2L-01', name_key: 'pricebook.seed.skim_2l', display_name: null, category: 'SKIM_COAT', unit: 'M2', price: null, currency: 'PLN',
  price_scope: 'LABOR', quality_level: null, is_archived: false, created_at: '', updated_at: '', ...over,
});
const PL = { pricebook: { seed: { skim_2l: 'Gładź szpachlowa — 2 warstwy (pakiet)' } } };
const RU = { pricebook: { seed: { skim_2l: 'Шпаклёвка — 2 слоя (пакет)' } } };

describe('the search of the price book (UX walk A1)', () => {
  it('folds case and accents, ł as l and ё as е', () => {
    expect(foldForSearch('Gładź ŚCIAN')).toBe('gladz scian');
    expect(foldForSearch('Шпаклёвка')).toBe('шпаклевка');
  });

  it('matches the translated names, the own name, the code and the extra words; every word must be found', () => {
    expect(priceItemMatches(ITEM(), 'шпаклевка 2', [RU, PL]), `ITEM(), 'шпаклевка 2', [RU, PL]`).toBe(true);
    expect(priceItemMatches(ITEM(), 'gladz', [RU, PL]), `ITEM(), 'gladz', [RU, PL]`).toBe(true);
    expect(priceItemMatches(ITEM(), 'skim_2l', [RU]), `ITEM(), 'skim_2l', [RU]`).toBe(true);
    expect(priceItemMatches(ITEM(), 'шпаклевка покраска', [RU, PL]), `ITEM(), 'шпаклевка покраска', [RU, PL]`).toBe(false);
    expect(priceItemMatches(ITEM({ name_key: null, display_name: 'Punkt wodny' }), 'wodny', [RU]), `ITEM({ name_key: null, display_name: 'Punkt wodny' }), 'wodny', [RU]`).toBe(true);
    expect(priceItemMatches(ITEM(), 'gipsow', [RU], ['Gładzie gipsowe']), 'the category words count').toBe(true);
    expect(priceItemMatches(ITEM(), '   ', [RU]), `ITEM(), '   ', [RU]`).toBe(true);
  });

  it('ranks a name that starts with the query first', () => {
    const prep = ITEM({ name_key: null, display_name: 'Grunt pod szpachlowanie' });
    expect(priceItemRank(ITEM(), 'шпаклевка', RU)).toBe(0);
    expect(priceItemRank(prep, 'szpachl', RU)).toBe(1);
    expect(priceItemRank(ITEM(), 'skim', RU)).toBe(2);
  });
});
