import { describe, expect, it } from 'vitest';
import { PHOTO_CATEGORIES } from '../types/photo';
import pl from './pl.json';
import ru from './ru.json';

type Dict = Record<string, unknown>;

function leaves(node: unknown, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node as Dict)) {
      const path = prefix ? `${prefix}.${key}` : key;
      if (typeof value === 'string') out.set(path, value);
      else for (const [childPath, text] of leaves(value, path)) out.set(childPath, text);
    }
  }
  return out;
}

const placeholders = (text: string) => (text.match(/\{[a-z_]+\}/g) ?? []).sort();

describe('photos locale namespace (PL / RU)', () => {
  const plLeaves = leaves(pl.photos);
  const ruLeaves = leaves(ru.photos);

  it('has identical keys in both languages', () => {
    expect([...ruLeaves.keys()].sort()).toEqual([...plLeaves.keys()].sort());
  });

  it('has no empty strings', () => {
    for (const [key, text] of [...plLeaves, ...ruLeaves]) expect(text.trim(), key).not.toBe('');
  });

  it('keeps the same {placeholders} in both languages', () => {
    for (const [key, text] of plLeaves) expect(placeholders(ruLeaves.get(key) ?? ''), key).toEqual(placeholders(text));
  });

  it('labels every backend photo category in both languages', () => {
    for (const category of PHOTO_CATEGORIES) {
      expect((pl.photos.category as Dict)[category], category).toBeTruthy();
      expect((ru.photos.category as Dict)[category], category).toBeTruthy();
    }
    expect(Object.keys(pl.photos.category).sort()).toEqual([...PHOTO_CATEGORIES].sort());
  });

  it('has every marker (Stage 14G) text and error in both languages', () => {
    const keys = ['add', 'add_done', 'count', 'hint_add', 'hint_view', 'limit_reached', 'marker_aria', 'marker_aria_labeled', 'popup_title', 'popup_label', 'popup_placeholder', 'popup_counter', 'popup_no_label', 'popup_save', 'popup_delete', 'popup_close', 'thumb_badge', 'fullscreen_hint_add', 'outline_draw', 'outline_redraw', 'outline_remove', 'outline_hint', 'outline_cancel', 'outline_too_short'];
    for (const key of keys) {
      expect((pl.photos.markers as Dict)[key], key).toBeTruthy();
      expect((ru.photos.markers as Dict)[key], key).toBeTruthy();
    }
    for (const key of ['marker_limit', 'marker_read_only', 'marker_invalid', 'marker_not_found']) {
      expect((pl.photos.errors as Dict)[key], key).toBeTruthy();
      expect((ru.photos.errors as Dict)[key], key).toBeTruthy();
    }
  });

  it('really is Polish and Russian (not copy-pasted across)', () => {
    expect(pl.photos.picker.take_photo).not.toBe(ru.photos.picker.take_photo);
    expect(ru.photos.picker.take_photo).toMatch(/[а-яА-Я]/);
    expect(pl.photos.picker.take_photo).not.toMatch(/[а-яА-Я]/);
  });

  it('contains no hardcoded price or legal text (rules A/B)', () => {
    for (const text of [...plLeaves.values(), ...ruLeaves.values()]) {
      expect(text).not.toMatch(/zł|PLN|руб|₽|art\.|Prawo budowlane|PN-/i);
    }
  });
});
