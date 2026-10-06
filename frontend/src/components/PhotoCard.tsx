import { useEffect } from 'react';
import { PhotoContext } from '../types/photo';
import { photoKey, useProjectPhotos } from '../hooks/ProjectPhotosContext';
import { useI18n } from '../hooks/useI18n';
import { photoCountFor, totalPhotoCount } from '../hooks/usePhotoCounts';
import { buildLocationPath } from '../utils/photoCaption';
import { PhotoEntryButton } from './PhotoEntryButton';
import { PhotoSection } from './PhotoSection';

// The two pieces a card adds for photos: the corner button (in its header) and the panel (directly under the header).
// They share state through the project context, so a card needs no hook and no wrapper — and outside a project
// context (existing tests, other screens) both render nothing.

interface PhotoCardTarget {
  context: PhotoContext;
  /** room / surface / opening id; omitted for the object itself. */
  targetId?: string;
}

interface PhotoCardButtonProps extends PhotoCardTarget {
  /** Puts the button on a row of its own (e.g. `flex justify-end` under a card header); no row without a provider. */
  rowClassName?: string;
}

export function PhotoCardButton({ context, targetId, rowClassName }: PhotoCardButtonProps) {
  const photos = useProjectPhotos();
  if (!photos) return null;
  // The object's own button shows every photo of the object: its section lists them all (C-3).
  const count = context === 'PROJECT' ? totalPhotoCount(photos.counts) : photoCountFor(photos.counts, context, targetId);
  const key = photoKey(context, targetId);
  const button = <PhotoEntryButton count={count} expanded={photos.isExpanded(key)} onToggle={() => photos.toggle(key)} />;
  return rowClassName ? <div className={rowClassName}>{button}</div> : button;
}

interface PhotoCardPanelProps extends PhotoCardTarget {
  /** Names the host already has, outermost first (room, surface, opening); ignored for the object. */
  locationSegments?: ReadonlyArray<string | null | undefined>;
}

export function PhotoCardPanel({ context, targetId, locationSegments = [] }: PhotoCardPanelProps) {
  const photos = useProjectPhotos();
  const { t } = useI18n();
  const open = photos?.isExpanded(photoKey(context, targetId)) ?? false;
  const projectWide = context === 'PROJECT';
  const ensureLocations = photos?.ensureLocations;

  useEffect(() => {
    if (open && projectWide) ensureLocations?.();
  }, [open, projectWide, ensureLocations]);

  if (!photos || !open) return null;
  return (
    <PhotoSection
      projectId={photos.projectId}
      context={context}
      targetId={targetId}
      locationLabel={
        projectWide ? photos.resolveLocation : buildLocationPath(locationSegments, t.photos.caption)
      }
      onCountAdjust={photos.adjust}
    />
  );
}
