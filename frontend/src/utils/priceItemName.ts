import { PriceItem } from '../types/priceItem';
import { resolveKey } from './i18nKeys';

/** display_name > localized name_key > em-dash. Never the machine code. */
export function resolveDisplayName(item: PriceItem, t: Record<string, unknown>): string {
  if (item.display_name) return item.display_name;
  if (item.name_key) {
    const resolved = resolveKey(t, item.name_key);
    if (resolved !== item.name_key) return resolved;
  }
  return '—';
}

/** Lower case without accents (ł counts as l): "Gładź" matches "gladz", "Шпаклёвка" matches "шпаклевка". */
export function foldForSearch(text: string): string {
  return text
    .toLowerCase()
    .replace(/ł/g, 'l')
    .replace(/ё/g, 'е')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}

/**
 * UX walk A1: the search of the price book looks at what the owner SEES -- the name in the language of the screen and in Polish (the catalogue rows have
 * no stored name, only a key), his own name, the code and the category -- every word of the query must be found somewhere.
 */
export function priceItemMatches(item: PriceItem, query: string, dictionaries: Record<string, unknown>[], extra: string[] = []): boolean {
  const words = foldForSearch(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const names = dictionaries.map((dictionary) => resolveDisplayName(item, dictionary));
  const haystack = foldForSearch([...names, item.display_name ?? '', item.code, ...extra].join(' '));
  return words.every((word) => haystack.includes(word));
}

/** The order of the found rows: the name on the screen starts with the query (0), contains it (1), the rest matched elsewhere (2). */
export function priceItemRank(item: PriceItem, query: string, dictionary: Record<string, unknown>): number {
  const name = foldForSearch(resolveDisplayName(item, dictionary));
  const folded = foldForSearch(query.trim());
  if (name.startsWith(folded)) return 0;
  return name.includes(folded) ? 1 : 2;
}
