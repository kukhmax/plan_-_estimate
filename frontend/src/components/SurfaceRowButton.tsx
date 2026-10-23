import { useRef } from 'react';
import { photoCountFor } from '../hooks/usePhotoCounts';
import { useProjectPhotos } from '../hooks/ProjectPhotosContext';
import { useI18n } from '../hooks/useI18n';
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
  /** How many works its plan holds; shown only when there are some (usability U-7). */
  workCount?: number;
  /** The wall exists only on the phone (Stage 19E). */
  pending?: boolean;
  /** A merged wall: how many parts it has (a badge); a wall that was joined into another one shows `mergedLabel`. */
  partsLabel?: string | null;
  mergedLabel?: string | null;
  /** Merge selection (backlog "Объединить стены"): when `selecting`, a tap marks the wall (`selectedOrder` = 1 for the wall that stays, 2... for the others). */
  selecting?: boolean;
  selectedOrder?: number | null;
  /** In the selection a wall that cannot be merged (merged already, archived, no size) is dimmed and does nothing. */
  disabled?: boolean;
  stayLabel?: string;
  className: string;
  onOpen: () => void;
  /** A long press (about half a second) starts the selection. */
  onLongPress?: () => void;
  /** A pencil beside the row (an icon only): the name is edited without opening the card. Not shown while walls are being selected. */
  onEdit?: () => void;
  editLabel?: string;
}

const LONG_PRESS_MS = 500;

/**
 * A collapsed wall: one line "Ściana 1 [Ściana] [📷 3] 8.62 m²". A tap opens the full card (Stage 18G: the list of walls stays short
 * so the owner finds a wall at a glance and opens only the one being worked on).
 */
export function SurfaceRowButton({
  surfaceId, rowKey, name, typeLabel, area, archivedLabel, workCount, pending, partsLabel, mergedLabel, selecting = false, selectedOrder = null,
  disabled = false, stayLabel, className, onOpen, onLongPress, onEdit, editLabel,
}: SurfaceRowButtonProps) {
  const { t } = useI18n();
  const photos = useProjectPhotos();
  const count = photos && surfaceId ? photoCountFor(photos.counts, 'SURFACE', surfaceId) : null;
  const key = rowKey ?? surfaceId ?? name;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fired = useRef(false);
  const start = useRef({ x: 0, y: 0 });
  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  const press = onLongPress && !selecting
    ? {
        onPointerDown: (event: { clientX: number; clientY: number }) => {
          fired.current = false;
          start.current = { x: event.clientX, y: event.clientY };
          clear();
          timer.current = setTimeout(() => {
            fired.current = true;
            onLongPress();
          }, LONG_PRESS_MS);
        },
        onPointerUp: clear,
        onPointerLeave: clear,
        onPointerCancel: clear,
        // a finger always shakes a little: only a real move (scrolling) cancels the press
        onPointerMove: (event: { clientX: number; clientY: number }) => {
          if (Math.hypot(event.clientX - start.current.x, event.clientY - start.current.y) > 10) clear();
        },
        // the browser's own menu on a long press must not open over the selection
        onContextMenu: (event: { preventDefault: () => void }) => event.preventDefault(),
      }
    : {};
  const handleClick = () => {
    if (fired.current) {
      fired.current = false; // the press that started the selection is not a tap
      return;
    }
    if (disabled) return;
    onOpen();
  };
  const row = (
    <button
      type="button"
      aria-label={`surface-row-${key}`}
      aria-expanded={selecting ? undefined : false}
      aria-pressed={selecting ? selectedOrder !== null : undefined}
      aria-disabled={disabled || undefined}
      onClick={handleClick}
      className={`${className} select-none touch-manipulation ${disabled ? 'opacity-50' : ''} ${selectedOrder !== null ? 'ring-2 ring-blue-500' : ''}`}
      {...press}
    >
      {selecting && (
        <span
          aria-label={`surface-row-mark-${key}`}
          className={`shrink-0 inline-flex min-w-7 h-7 items-center justify-center rounded-full border text-xs font-bold ${
            selectedOrder !== null ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-400 text-transparent'
          }`}
        >
          {selectedOrder ?? '·'}
        </span>
      )}
      <span className="min-w-0 flex-1 flex items-center gap-2 flex-wrap text-left">
        <span className="font-semibold text-slate-900 text-sm break-words">{name}</span>
        {typeLabel && <span className="text-xs px-2 py-0.5 rounded-full pe-pill font-medium">{typeLabel}</span>}
        {archivedLabel && <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">{archivedLabel}</span>}
        <PendingMark record={{ _pending: pending }} id={key} />
        {partsLabel && <span aria-label={`surface-row-parts-${key}`} className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 font-medium">🔗 {partsLabel}</span>}
        {mergedLabel && <span aria-label={`surface-row-merged-${key}`} className="text-xs px-2 py-0.5 rounded-full pe-pill font-medium">{mergedLabel}</span>}
        {selecting && selectedOrder === 1 && stayLabel && <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-medium">{stayLabel}</span>}
      </span>
      {workCount !== undefined && workCount > 0 && (
        <span aria-label={`surface-row-works-${key}`} title={t.surfaces.works_in_plan} className="shrink-0 text-xs px-2 py-0.5 rounded-full pe-pill font-semibold">
          <span aria-hidden="true">🛠️ </span>
          {workCount}
        </span>
      )}
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
  if (!onEdit || selecting) return row;
  return (
    <div className="flex items-stretch gap-1.5">
      <div className="min-w-0 flex-1 flex">{row}</div>
      <button
        type="button"
        aria-label={`edit-surface-${key}`}
        title={editLabel}
        onClick={onEdit}
        className="shrink-0 min-h-11 min-w-11 flex items-center justify-center rounded-xl border border-slate-200 pe-pill text-base"
      >
        <span aria-hidden="true">✏️</span>
      </button>
    </div>
  );
}
