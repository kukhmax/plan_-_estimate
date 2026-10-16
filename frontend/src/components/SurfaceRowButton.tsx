import { photoCountFor } from '../hooks/usePhotoCounts';
import { useProjectPhotos } from '../hooks/ProjectPhotosContext';
import { PendingMark } from './PendingMark';

interface SurfaceRowButtonProps {
  /** The surface whose photos are counted; null when it is not known (the count is then left out). */
  surfaceId: string | null;
  /** The key of the aria-labels (`surface-row-<key>`); the surface id by default. */
  rowKey?: string;
  name: string;
  /** The small badge after the name; a plane (floor, ceiling) has none: its name says it. */
  typeLabel?: string;
  /** Already formatted ("8.62 m²"); '—' when the wall has no dimensions yet. */
  area: string;
  archivedLabel?: string | null;
  /** The wall exists only on the phone (Stage 19E). */
  pending?: boolean;
  className: string;
  onOpen: () => void;
}

/**
 * A collapsed wall: one line "Ściana 1 [Ściana] [📷 3] 8.62 m²". A tap opens the full card (Stage 18G: the list of walls stays short
 * so the owner finds a wall at a glance and opens only the one being worked on).
 */
export function SurfaceRowButton({ surfaceId, rowKey, name, typeLabel, area, archivedLabel, pending, className, onOpen }: SurfaceRowButtonProps) {
  const photos = useProjectPhotos();
  const count = photos && surfaceId ? photoCountFor(photos.counts, 'SURFACE', surfaceId) : null;
  const key = rowKey ?? surfaceId ?? name;
  return (
    <button type="button" aria-label={`surface-row-${key}`} aria-expanded={false} onClick={onOpen} className={className}>
      <span className="min-w-0 flex-1 flex items-center gap-2 flex-wrap text-left">
        <span className="font-semibold text-slate-900 text-sm break-words">{name}</span>
        {typeLabel && <span className="text-xs px-2 py-0.5 rounded-full bg-white/80 text-slate-700 font-medium">{typeLabel}</span>}
        {archivedLabel && <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">{archivedLabel}</span>}
        <PendingMark record={{ _pending: pending }} id={key} />
      </span>
      {count !== null && (
        <span aria-label={`surface-row-photos-${key}`} className="shrink-0 text-xs px-2 py-0.5 rounded-full bg-slate-900 text-white font-semibold">
          <span aria-hidden="true">📷 </span>
          {count}
        </span>
      )}
      <span aria-label={`surface-row-area-${key}`} className="shrink-0 text-sm font-bold text-emerald-800">{area}</span>
      <span aria-hidden="true" className="shrink-0 text-slate-500">▾</span>
    </button>
  );
}
