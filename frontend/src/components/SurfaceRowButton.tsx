import { photoCountFor } from '../hooks/usePhotoCounts';
import { useProjectPhotos } from '../hooks/ProjectPhotosContext';

interface SurfaceRowButtonProps {
  surfaceId: string;
  name: string;
  typeLabel: string;
  /** Already formatted ("8.62 m²"); '—' when the wall has no dimensions yet. */
  area: string;
  archivedLabel?: string | null;
  className: string;
  onOpen: () => void;
}

/**
 * A collapsed wall: one line "Ściana 1 [Ściana] [📷 3] 8.62 m²". A tap opens the full card (Stage 18G: the list of walls stays short
 * so the owner finds a wall at a glance and opens only the one being worked on).
 */
export function SurfaceRowButton({ surfaceId, name, typeLabel, area, archivedLabel, className, onOpen }: SurfaceRowButtonProps) {
  const photos = useProjectPhotos();
  const count = photos ? photoCountFor(photos.counts, 'SURFACE', surfaceId) : null;
  return (
    <button type="button" aria-label={`surface-row-${surfaceId}`} aria-expanded={false} onClick={onOpen} className={className}>
      <span className="min-w-0 flex-1 flex items-center gap-2 flex-wrap text-left">
        <span className="font-semibold text-slate-900 text-sm break-words">{name}</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-white/80 text-slate-700 font-medium">{typeLabel}</span>
        {archivedLabel && <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">{archivedLabel}</span>}
      </span>
      {count !== null && (
        <span aria-label={`surface-row-photos-${surfaceId}`} className="shrink-0 text-xs px-2 py-0.5 rounded-full bg-slate-900 text-white font-semibold">
          <span aria-hidden="true">📷 </span>
          {count}
        </span>
      )}
      <span aria-label={`surface-row-area-${surfaceId}`} className="shrink-0 text-sm font-bold text-emerald-800">{area}</span>
      <span aria-hidden="true" className="shrink-0 text-slate-500">▾</span>
    </button>
  );
}
