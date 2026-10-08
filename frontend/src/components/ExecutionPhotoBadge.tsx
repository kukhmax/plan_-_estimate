import { useProjectPhotos } from '../hooks/ProjectPhotosContext';
import { useI18n } from '../hooks/useI18n';
import { inspectionPlaneCount, inspectionSurfaceCount, photoCountFor } from '../hooks/usePhotoCounts';
import { CameraIcon } from './PhotoIcons';

// Small indicators on the rows that lead to photos nobody sees in the object's and the room's photo lists: execution photos
// ("Realizacja / Выполнение") and inspection photos ("Badanie ściany / Обследование стены"). Both kinds live only inside
// their own screens on purpose, so without a mark the row gives no hint that anything was photographed.
// An indicator is a mark, not a control: it is part of the row's content, to the right of the label (the whole row keeps its
// job) and takes no taps. The row is a flex line, so a long label (a long Russian one on a 320 px phone) wraps in the room that
// is left and can never run under the mark. Nothing is drawn for no photos or outside a project photo context.

/** Classes of the full-width "Realizacja" row: the label and the mark side by side, centred. */
export const EXECUTION_ROW_WITH_BADGE = 'flex flex-wrap items-center justify-center gap-x-2 gap-y-1 px-3';
/** Classes of the narrow "Badanie …" buttons (two to a row): the same, with a tighter gap. */
export const INSPECT_BUTTON_WITH_BADGE = 'flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1 px-2';

interface CountBadgeProps {
  count: number;
  label: string;
  testId: string;
}

/** The mark shows at most this many; more is "99+" so its width stays bounded and never runs under a label. */
export const BADGE_MAX_COUNT = 99;

function CountBadge({ count, label, testId }: CountBadgeProps) {
  return (
    <span
      data-testid={testId}
      role="img"
      aria-label={label}
      title={label}
      className="pointer-events-none inline-flex shrink-0 items-center gap-0.5 rounded-full border border-slate-300 bg-white px-1.5 py-0.5 text-xs font-semibold text-slate-700"
    >
      <CameraIcon size={14} />
      <span aria-hidden="true">{count > BADGE_MAX_COUNT ? `${BADGE_MAX_COUNT}+` : count}</span>
    </span>
  );
}

export function ExecutionPhotoBadge({ surfaceId }: { surfaceId: string }) {
  const photos = useProjectPhotos();
  const { t } = useI18n();
  if (!photos) return null;
  const count = photoCountFor(photos.counts, 'WORK', surfaceId);
  if (count <= 0) return null;
  return (
    <CountBadge
      count={count}
      label={t.photos.execution_badge.replace('{count}', String(count))}
      testId="execution-photo-badge"
    />
  );
}

interface InspectionPhotoBadgeProps {
  /** A wall's (or any surface's) inspections. */
  surfaceId?: string | null;
  /** The floor / ceiling inspections of a room: they target the plane of the room, not a surface, so both are summed. */
  roomId?: string;
  plane?: 'FLOOR' | 'CEILING';
}

export function InspectionPhotoBadge({ surfaceId = null, roomId, plane }: InspectionPhotoBadgeProps) {
  const photos = useProjectPhotos();
  const { t } = useI18n();
  if (!photos) return null;
  const count =
    (surfaceId ? inspectionSurfaceCount(photos.counts, surfaceId) : 0) +
    (roomId && plane ? inspectionPlaneCount(photos.counts, roomId, plane) : 0);
  if (count <= 0) return null;
  return (
    <CountBadge
      count={count}
      label={t.photos.inspection_badge.replace('{count}', String(count))}
      testId="inspection-photo-badge"
    />
  );
}
