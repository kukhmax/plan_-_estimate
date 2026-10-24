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
