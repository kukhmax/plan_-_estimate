/**
 * The dark scheme of the Tailwind colour classes (usability phase U-1).
 *
 * The components keep their light-theme colour classes (`text-slate-900`, `bg-emerald-50`, `border-amber-200` ...). In the dark Telegram
 * theme `html[data-color-scheme='dark']` remaps each of them here: light pastel fills become a soft translucent tint of the same hue,
 * dark text becomes light, light borders become a faint line. Saturated fills (buttons, accent tiles) stay as they are. The light theme is
 * not touched. `scripts/genDarkCss.ts` writes `darkTheme.generated.css` from the classes the sources use; `audit/darkSurfaces.test.ts`
 * fails when the file is stale, so a class added later cannot be left light-only.
 */

const NEUTRALS = ['slate', 'gray', 'zinc', 'neutral', 'stone'] as const;

// Tailwind v3 palette: the 500 (tint base) and the 300 (readable text on a dark surface) of every hue the sources use.
const HUES: Record<string, { c500: string; c300: string; c500rgb: string }> = {
  red: { c500: '#ef4444', c300: '#fca5a5', c500rgb: '239, 68, 68' },
  orange: { c500: '#f97316', c300: '#fdba74', c500rgb: '249, 115, 22' },
  amber: { c500: '#f59e0b', c300: '#fcd34d', c500rgb: '245, 158, 11' },
  yellow: { c500: '#eab308', c300: '#fde047', c500rgb: '234, 179, 8' },
  lime: { c500: '#84cc16', c300: '#bef264', c500rgb: '132, 204, 22' },
  green: { c500: '#22c55e', c300: '#86efac', c500rgb: '34, 197, 94' },
  emerald: { c500: '#10b981', c300: '#6ee7b7', c500rgb: '16, 185, 129' },
  teal: { c500: '#14b8a6', c300: '#5eead4', c500rgb: '20, 184, 166' },
  cyan: { c500: '#06b6d4', c300: '#67e8f9', c500rgb: '6, 182, 212' },
  sky: { c500: '#0ea5e9', c300: '#7dd3fc', c500rgb: '14, 165, 233' },
  blue: { c500: '#3b82f6', c300: '#93c5fd', c500rgb: '59, 130, 246' },
  indigo: { c500: '#6366f1', c300: '#a5b4fc', c500rgb: '99, 102, 241' },
  violet: { c500: '#8b5cf6', c300: '#c4b5fd', c500rgb: '139, 92, 246' },
  purple: { c500: '#a855f7', c300: '#d8b4fe', c500rgb: '168, 85, 247' },
  fuchsia: { c500: '#d946ef', c300: '#f0abfc', c500rgb: '217, 70, 239' },
  pink: { c500: '#ec4899', c300: '#f9a8d4', c500rgb: '236, 72, 153' },
  rose: { c500: '#f43f5e', c300: '#fda4af', c500rgb: '244, 63, 94' },
};

const COLOUR_NAMES = ['white', 'black', ...NEUTRALS, ...Object.keys(HUES)];
const CLASS_PATTERN = new RegExp(
  `(?<![\\w:/-])((?:[a-z]+:)*)(bg|text|border|ring)-(${COLOUR_NAMES.join('|')})(?:-(\\d{2,3}))?(?:/(\\d{1,3}))?(?![\\w-])`,
  'g',
);

export interface ColourClass {
  /** The whole class as it is written in the source: `hover:bg-slate-50`. */
  name: string;
  variant: '' | 'hover' | 'active' | 'focus';
  property: 'bg' | 'text' | 'border' | 'ring';
  colour: string;
  shade: number | null;
  alpha: number | null;
}

const SUPPORTED_VARIANTS = new Set(['', 'hover', 'active', 'focus']);

/** Every colour utility class written in a source text (classes built from parts are not found: the sources write them whole). */
export function colourClassesIn(source: string): ColourClass[] {
  const found: ColourClass[] = [];
  for (const match of source.matchAll(CLASS_PATTERN)) {
    const [name, variantText, property, colour, shade, alpha] = match;
    const variant = variantText.replace(/:$/, '');
    if (!SUPPORTED_VARIANTS.has(variant)) throw new Error(`variant "${variant}" of ${name} has no dark rule`);
    found.push({
      name,
      variant: variant as ColourClass['variant'],
      property: property as ColourClass['property'],
      colour,
      shade: shade ? Number(shade) : null,
      alpha: alpha ? Number(alpha) : null,
    });
  }
  return found;
}

const isNeutral = (colour: string) => (NEUTRALS as readonly string[]).includes(colour);

/** What the class becomes in the dark scheme (`property: value`), or null when it stays as it is. */
export function darkDeclaration(cls: ColourClass): string | null {
  const { property, colour, shade, alpha } = cls;
  const a = alpha === null ? 1 : alpha / 100;
  const num = (value: number) => Number((value * a).toFixed(3));

  if (property === 'bg') {
    if (colour === 'white') return alpha === null ? 'background-color: var(--pe-surface)' : null; // a translucent white sits on a colour, as it is
    if (colour === 'black' || shade === null) return null;
    if (isNeutral(colour)) {
      if (shade === 900) return 'background-color: var(--tg-theme-button-color)';
      const level: Record<number, number> = { 50: 0.1, 100: 0.16, 200: 0.24, 300: 0.32 };
      return level[shade] === undefined ? null : `background-color: rgba(148, 163, 184, ${num(level[shade])})`;
    }
    const level: Record<number, number> = { 50: 0.12, 100: 0.18, 200: 0.26, 300: 0.35 };
    const hue = HUES[colour];
    return hue && level[shade] !== undefined ? `background-color: rgba(${hue.c500rgb}, ${num(level[shade])})` : null;
  }

  if (property === 'text') {
    if (colour === 'white') return null;
    if (colour === 'black') return 'color: var(--tg-theme-text-color)';
    if (shade === null) return null;
    if (isNeutral(colour)) {
      if (shade >= 700) return 'color: var(--tg-theme-text-color)';
      if (shade >= 500) return 'color: var(--pe-text-muted)';
      if (shade >= 300) return 'color: var(--pe-text-faint)';
      return null;
    }
    const hue = HUES[colour];
    if (!hue) return null;
    if (colour === 'blue' && shade >= 600) return 'color: var(--tg-theme-link-color)';
    if (shade >= 600) return `color: ${hue.c300}`;
    if (shade === 500) return `color: ${hue.c300}`;
    return null;
  }

  if (property === 'border') {
    if (colour === 'white' || colour === 'black' || shade === null) return null;
    if (isNeutral(colour)) return shade <= 300 ? `border-color: rgba(148, 163, 184, ${num(0.3)})` : null;
    const hue = HUES[colour];
    return hue && shade >= 100 && shade <= 400 ? `border-color: rgba(${hue.c500rgb}, ${num(0.45)})` : null;
  }

  return null; // rings (focus rings of the controls) stay
}

/** The CSS selector of the class, with the variant's pseudo-class. */
function selectorOf(cls: ColourClass): string {
  const escaped = cls.name.replace(/[:/.]/g, (ch) => `\\${ch}`);
  const pseudo = cls.variant ? `:${cls.variant}` : '';
  return `html[data-color-scheme='dark'] .${escaped}${pseudo}`;
}

/** The generated stylesheet: one rule per class used, sorted so that the file does not change from run to run. */
export function buildDarkCss(classes: ColourClass[]): string {
  const rules = new Map<string, string>();
  for (const cls of classes) {
    const declaration = darkDeclaration(cls);
    if (declaration) rules.set(cls.name, `${selectorOf(cls)} {\n  ${declaration};\n}`);
  }
  const body = [...rules.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([, rule]) => rule);
  return [
    '/* GENERATED by scripts/genDarkCss.ts from the colour classes the sources use (src/theme/darkMap.ts). Do not edit by hand. */',
    ...body,
    '',
  ].join('\n');
}
