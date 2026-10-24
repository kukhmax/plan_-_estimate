import { describe, expect, it } from 'vitest';
import en from './en.json';
import pl from './pl.json';
import ru from './ru.json';
import uk from './uk.json';
import { LOCALES } from '../utils/locale';

const DICTIONARIES = { pl, ru, uk, en } as const;

function flatten(node: unknown, prefix = ''): Map<string, string> {
  const result = new Map<string, string>();
  if (typeof node === 'string') {
    result.set(prefix, node);
  } else if (Array.isArray(node)) {
    node.forEach((item, index) => flatten(item, `${prefix}.${index}`).forEach((value, key) => result.set(key, value)));
  } else if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node)) {
      flatten(value, prefix ? `${prefix}.${key}` : key).forEach((text, path) => result.set(path, text));
    }
  }
  return result;
}

const placeholders = (text: string) => (text.match(/\{[^}]*\}/g) ?? []).sort();

const FLAT = Object.fromEntries(LOCALES.map((locale) => [locale, flatten(DICTIONARIES[locale])])) as Record<(typeof LOCALES)[number], Map<string, string>>;

describe('the four dictionaries of the screens (V2-7)', () => {
  it('has the four languages the application offers', () => {
    expect([...LOCALES].sort()).toEqual(Object.keys(DICTIONARIES).sort());
  });

  it.each(['ru', 'uk', 'en'] as const)('%s has exactly the keys of the Polish dictionary', (locale) => {
    const base = [...FLAT.pl.keys()].sort();
    const other = [...FLAT[locale].keys()].sort();
    expect(other.filter((key) => !FLAT.pl.has(key))).toEqual([]);
    expect(base.filter((key) => !FLAT[locale].has(key))).toEqual([]);
  });

  it.each(['ru', 'uk', 'en'] as const)('%s keeps the placeholders of every text and has no empty text', (locale) => {
    const mismatched: string[] = [];
    const empty: string[] = [];
    FLAT.pl.forEach((text, key) => {
      const translated = FLAT[locale].get(key) ?? '';
      if (placeholders(translated).join() !== placeholders(text).join()) mismatched.push(key);
      if (!translated.trim()) empty.push(key);
    });
    expect(mismatched).toEqual([]);
    expect(empty).toEqual([]);
  });

  it.each(['uk', 'en'] as const)('%s speaks its own language (letters of the alphabet)', (locale) => {
    const texts = [...FLAT[locale].values()].join(' ');
    if (locale === 'uk') {
      expect(texts).toMatch(/[іїєґ]/);
      expect(texts).not.toMatch(/[ыэъ]/);
    } else {
      expect(texts).not.toMatch(/[а-яА-Я]/);
    }
  });

  it('the plural forms exist for every language', () => {
    for (const locale of LOCALES) {
      for (const form of ['one', 'few', 'many', 'other']) {
        expect(FLAT[locale].has(`coefficients.option_count.${form}`)).toBe(true);
      }
    }
  });
});
