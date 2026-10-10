interface HubTileProps {
  label: string;
  ariaLabel: string;
  onOpen: () => void;
  /** A small number on the right (photos). */
  count?: number;
  accent?: boolean;
}

/** One large full-width tile of a hub (the object, the price, the documents, the agreement and protocols): 56 px, wraps long names. */
export function HubTile({ label, ariaLabel, onOpen, count, accent = false }: HubTileProps) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onOpen}
      className={
        accent
          ? 'w-full min-h-14 bg-amber-500 border border-amber-600 rounded-2xl px-4 py-3 shadow-md flex items-center justify-between gap-3 text-left hover:bg-amber-400 active:bg-amber-600 transition'
          : 'w-full min-h-14 bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm flex items-center justify-between gap-3 text-left hover:bg-slate-50 transition'
      }
    >
      <span className={`font-bold text-sm break-words min-w-0 ${accent ? 'text-slate-950' : 'text-slate-900'}`}>{label}</span>
      <span className="flex items-center gap-2 shrink-0">
        {count !== undefined && (
          <span aria-label={`${ariaLabel}-count`} className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold">
            {count}
          </span>
        )}
        <span aria-hidden="true" className={`text-lg leading-none ${accent ? 'text-slate-950' : 'text-slate-400'}`}>›</span>
      </span>
    </button>
  );
}
