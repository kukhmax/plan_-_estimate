/** The soft colours of the tiles of the object (the owner's choice, 2026-10-18): a tile of its own colour is found by the eye before it is read. */
export type HubTileTone = 'green' | 'sky' | 'pink' | 'slate' | 'yellow';

const TONES: Record<HubTileTone, string> = {
  green: 'border-[3px] bg-green-100 border-green-800 hover:bg-green-200 active:bg-green-300', // the rooms: first on the hub, with a wide dark-green border (the owner's choice of 2026-10-19)
  sky: 'border bg-sky-100 border-sky-300 hover:bg-sky-200 active:bg-sky-300',
  pink: 'border bg-pink-100 border-pink-300 hover:bg-pink-200 active:bg-pink-300',
  slate: 'border bg-slate-200 border-slate-300 hover:bg-slate-300 active:bg-slate-400',
  yellow: 'border bg-yellow-100 border-yellow-300 hover:bg-yellow-200 active:bg-yellow-300',
};

interface HubTileProps {
  label: string;
  ariaLabel: string;
  onOpen: () => void;
  /** A small number on the right (photos). */
  count?: number;
  accent?: boolean;
  /** A soft background colour; without it the tile is white. `accent` (the estimate) wins. */
  tone?: HubTileTone;
  /** A decorative emoji before the label. */
  icon?: string;
}

/** One large full-width tile of a hub (the object, the price, the documents, the agreement and protocols): 56 px, wraps long names. */
export function HubTile({ label, ariaLabel, onOpen, count, accent = false, tone, icon }: HubTileProps) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      data-tone={accent ? 'accent' : (tone ?? 'white')}
      onClick={onOpen}
      className={
        accent
          ? 'w-full min-h-14 bg-amber-500 border border-amber-600 rounded-2xl px-4 py-3 shadow-md flex items-center justify-between gap-3 text-left hover:bg-amber-400 active:bg-amber-600 transition'
          : `w-full min-h-14 rounded-2xl px-4 py-3 shadow-sm flex items-center justify-between gap-3 text-left transition ${
              tone ? TONES[tone] : 'border bg-white border-slate-200 hover:bg-slate-50'
            }`
      }
    >
      <span className={`font-bold text-sm break-words min-w-0 flex items-center gap-2.5 ${accent ? 'text-slate-950' : 'text-slate-900'}`}>
        {icon && <span aria-hidden="true" className="text-xl leading-none shrink-0 select-none">{icon}</span>}
        <span className="min-w-0">{label}</span>
      </span>
      <span className="flex items-center gap-2 shrink-0">
        {count !== undefined && (
          <span aria-label={`${ariaLabel}-count`} className={`text-xs px-2 py-0.5 rounded-full font-semibold ${tone ? 'bg-white/70 text-slate-700' : 'bg-slate-100 text-slate-600'}`}>
            {count}
          </span>
        )}
        <span aria-hidden="true" className={`text-lg leading-none ${accent ? 'text-slate-950' : 'text-slate-400'}`}>›</span>
      </span>
    </button>
  );
}
