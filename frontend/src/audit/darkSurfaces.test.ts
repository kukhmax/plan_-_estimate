/**
 * Usability U-1 -- the dark Telegram theme has no white cards:
 *  - no component paints `bg-white` (a card is `pe-card`, any other white surface `pe-surface`; both follow the theme),
 *  - every light colour class the sources use has its dark rule in `darkTheme.generated.css` (the file is made by `scripts/genDarkCss.ts`),
 *  - the tinted cards of the surfaces keep only a stripe of the colour in the dark scheme.
 */
import { describe, expect, it } from 'vitest';
import { buildDarkCss, colourClassesIn } from '../theme/darkMap';
import { surfaceCardTint } from '../utils/surfaceColorTint';
import { surfaceTypeTint } from '../utils/surfaceTypeTint';
import generatedCss from '../darkTheme.generated.css?raw';
import indexCss from '../index.css?raw';

const raw = import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

const sources = Object.entries(raw)
  .filter(([path]) => !/\.test\.(ts|tsx)$/.test(path) && !path.includes('/src/test/') && !path.includes('/src/audit/') && !path.includes('/src/theme/'))
  .map(([path, text]) => ({ path: path.replace('/src/', ''), text }));

// The white of a white surface that is white in every theme: the button of the photo in a photo editor over a dark overlay.
const WHITE_ALLOWED = new Set(['components/PhotoFullscreen.tsx']);

describe('the dark theme surfaces (usability U-1)', () => {
  it('reads the whole source (the guard is not empty)', () => {
    expect(sources.length).toBeGreaterThan(90);
  });

  it('has no component with a hard-coded white background', () => {
    const found: string[] = [];
    for (const { path, text } of sources) {
      if (WHITE_ALLOWED.has(path)) continue;
      text.split('\n').forEach((line, index) => {
        if (/(?<![\w:/-])bg-white(?![\w/-])/.test(line.replace(/\/\/.*$/, ''))) found.push(`${path}:${index + 1}: ${line.trim().slice(0, 100)}`);
      });
    }
    expect(found).toEqual([]);
  });

  it('has a dark rule for every colour class the sources use (run scripts/genDarkCss.ts after adding one)', () => {
    const classes = sources.flatMap(({ text }) => colourClassesIn(text));
    expect(classes.length).toBeGreaterThan(200);
    expect(generatedCss).toBe(buildDarkCss(classes));
  });

  it('turns a pastel fill, a dark text and a light border of the light theme into their dark counterparts', () => {
    expect(generatedCss).toMatch(/\.bg-emerald-50 \{\s*background-color: rgba\(16, 185, 129, 0\.12\)/);
    expect(generatedCss).toMatch(/\.text-slate-900 \{\s*color: var\(--tg-theme-text-color\)/);
    expect(generatedCss).toMatch(/\.border-slate-200 \{\s*border-color: rgba\(148, 163, 184, 0\.3\)/);
    expect(generatedCss).toMatch(/\.text-red-700 \{\s*color: #fca5a5/);
    // a saturated fill (a button) is not touched
    expect(generatedCss).not.toMatch(/\.bg-blue-600 \{/);
  });

  it('keeps the card surface on the Telegram theme in the dark scheme and the white card in the light one', () => {
    expect(indexCss).toMatch(/--pe-surface: #ffffff;/);
    expect(indexCss).toMatch(/html\[data-color-scheme='dark'\] \{[^}]*--pe-surface: var\(--tg-theme-secondary-bg-color\)/s);
    expect(indexCss).toMatch(/\.pe-card \{[^}]*background-color: var\(--pe-surface\)/s);
  });

  it('leaves only a stripe of colour on a tinted card in the dark scheme', () => {
    expect(indexCss).toMatch(/html\[data-color-scheme='dark'\] \.pe-tinted \{[^}]*border-left-width: 4px/s);
    for (const id of ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']) {
      const tint = surfaceCardTint(id);
      expect(tint.extra).toMatch(/^pe-tinted pe-accent-[a-z]+$/);
      expect(indexCss).toContain(`.${tint.extra.split(' ')[1]} {`);
    }
    expect(surfaceCardTint(null).extra).toBe('');
    for (const type of ['WALL', 'FLOOR', 'CEILING'] as const) {
      expect(surfaceTypeTint(type).extra).toMatch(/^pe-tinted pe-accent-/);
    }
  });
});
