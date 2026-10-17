import { describe, expect, it } from 'vitest';
import { coefficientLook } from './coefficientLook';

describe('coefficientLook: an icon and a colour of its own for each group', () => {
  it('gives the four groups that come with the application four different looks with their own icons', () => {
    const codes = ['WYSOKOSC_PRACY', 'DOSTEP_DO_POWIERZCHNI', 'ZLOZONOSC_POWIERZCHNI', 'ORGANIZACJA_PRACY'];
    const looks = codes.map(coefficientLook);
    expect(looks.map((l) => l.icon)).toEqual(['🪜', '🚧', '🧩', '🗓️']);
    expect(new Set(looks.map((l) => l.card)).size).toBe(4);
    expect(new Set(looks.map((l) => l.badge)).size).toBe(4);
    expect(looks[0].card).toContain('sky');
    expect(looks[1].card).toContain('orange');
    expect(looks[2].card).toContain('violet');
    expect(looks[3].card).toContain('emerald');
  });

  it('gives a group of the owner the same look every time, from a colour the fixed groups do not use', () => {
    const fixed = new Set(['WYSOKOSC_PRACY', 'DOSTEP_DO_POWIERZCHNI', 'ZLOZONOSC_POWIERZCHNI', 'ORGANIZACJA_PRACY'].map((c) => coefficientLook(c).card));
    for (const code of ['CUSTOM_A1B2C3D4E5F6', 'CUSTOM_000000000000', 'CUSTOM_FFFFFFFFFFFF', 'x']) {
      expect(coefficientLook(code)).toBe(coefficientLook(code));
      expect(fixed.has(coefficientLook(code).card)).toBe(false);
    }
  });

  it('spreads the groups of the owner over several colours', () => {
    const cards = new Set(Array.from({ length: 60 }, (_, i) => coefficientLook(`CUSTOM_${(i * 2654435761).toString(16).toUpperCase().padStart(12, '0')}`).card));
    expect(cards.size).toBeGreaterThanOrEqual(4);
  });

  it('writes whole class names (Tailwind reads them from the source, not from a template)', () => {
    for (const code of ['WYSOKOSC_PRACY', 'CUSTOM_A1B2C3D4E5F6']) {
      const look = coefficientLook(code);
      expect(look.card).toMatch(/^bg-[a-z]+-50 border-[a-z]+-200$/);
      expect(look.badge).toMatch(/^bg-[a-z]+-100$/);
      expect(look.row).toMatch(/^hover:bg-[a-z]+-100 active:bg-[a-z]+-200$/);
    }
  });
});
