/**
 * The look of a coefficient group: an icon and a soft colour of its own (the owner's request of 2026-10-18), so the groups are told apart by the
 * eye, not only by the name. The four groups that come with the application have fixed looks (by their code); a group the owner makes
 * (`CUSTOM_...`) gets one of the other colours, always the same for the same code. Pure decoration: nothing depends on it.
 */
export interface CoefficientLook {
  icon: string;
  /** The card of the group. */
  card: string;
  /** The toggle row inside the card (the hover and press states). */
  row: string;
  /** The square behind the icon. */
  badge: string;
}

// full class names are written out: Tailwind finds them by reading the source, not by running it
const SKY: CoefficientLook = { icon: '🪜', card: 'bg-sky-50 border-sky-200', row: 'hover:bg-sky-100 active:bg-sky-200', badge: 'bg-sky-100' };
const ORANGE: CoefficientLook = { icon: '🚧', card: 'bg-orange-50 border-orange-200', row: 'hover:bg-orange-100 active:bg-orange-200', badge: 'bg-orange-100' };
const VIOLET: CoefficientLook = { icon: '🧩', card: 'bg-violet-50 border-violet-200', row: 'hover:bg-violet-100 active:bg-violet-200', badge: 'bg-violet-100' };
const EMERALD: CoefficientLook = { icon: '🗓️', card: 'bg-emerald-50 border-emerald-200', row: 'hover:bg-emerald-100 active:bg-emerald-200', badge: 'bg-emerald-100' };

const KNOWN: Record<string, CoefficientLook> = {
  WYSOKOSC_PRACY: SKY,
  DOSTEP_DO_POWIERZCHNI: ORANGE,
  ZLOZONOSC_POWIERZCHNI: VIOLET,
  ORGANIZACJA_PRACY: EMERALD,
};

const CUSTOM: CoefficientLook[] = [
  { icon: '🏷️', card: 'bg-rose-50 border-rose-200', row: 'hover:bg-rose-100 active:bg-rose-200', badge: 'bg-rose-100' },
  { icon: '🔖', card: 'bg-indigo-50 border-indigo-200', row: 'hover:bg-indigo-100 active:bg-indigo-200', badge: 'bg-indigo-100' },
  { icon: '📐', card: 'bg-lime-50 border-lime-200', row: 'hover:bg-lime-100 active:bg-lime-200', badge: 'bg-lime-100' },
  { icon: '🔧', card: 'bg-cyan-50 border-cyan-200', row: 'hover:bg-cyan-100 active:bg-cyan-200', badge: 'bg-cyan-100' },
  { icon: '🎯', card: 'bg-fuchsia-50 border-fuchsia-200', row: 'hover:bg-fuchsia-100 active:bg-fuchsia-200', badge: 'bg-fuchsia-100' },
  { icon: '📌', card: 'bg-teal-50 border-teal-200', row: 'hover:bg-teal-100 active:bg-teal-200', badge: 'bg-teal-100' },
];

function hashOf(code: string): number {
  let hash = 0;
  for (let i = 0; i < code.length; i += 1) hash = (hash * 31 + code.charCodeAt(i)) >>> 0;
  return hash;
}

export function coefficientLook(code: string): CoefficientLook {
  return KNOWN[code] ?? CUSTOM[hashOf(code) % CUSTOM.length];
}
