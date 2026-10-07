import { useEffect } from 'react';
import { PhotoAttachmentRead, PhotoContext } from '../types/photo';
import { photoKey, useProjectPhotos } from '../hooks/ProjectPhotosContext';
import { useI18n } from '../hooks/useI18n';
import { photoCountFor, roomPhotoTotal, totalPhotoCount } from '../hooks/usePhotoCounts';
import { buildLocationPath } from '../utils/photoCaption';
import { PhotoEntryButton } from './PhotoEntryButton';
import { PhotoSection } from './PhotoSection';

// The two pieces a card adds for photos: the corner button (in its header) and the panel (directly under the header).
// They share state through the project context, so a card needs no hook and no wrapper — and outside a project
// context (existing tests, other screens) both render nothing.

interface PhotoCardTarget {
  context: PhotoContext;
  /** room / surface / opening id; the inspection for INSPECTION, the finding row for FINDING; omitted for the object itself. */
  targetId?: string;
  /** INSPECTION: the checklist question of a question-level button / panel (without it: the whole inspection's). */
  questionId?: string;
  /** FINDING: the lineage whose photos the button counts and the panel lists. */
  lineageId?: string;
}

export function PhotoCardButton({ context, targetId, questionId, lineageId }: PhotoCardTarget) {
  const photos = useProjectPhotos();
  if (!photos) return null;
  // The object's button shows every photo of the object, a room's button every photo of the room (its surfaces and
  // openings included): their sections list them all. A surface's button shows its own photos.
  const count =
    context === 'PROJECT'
      ? totalPhotoCount(photos.counts)
      : context === 'ROOM' && targetId
        ? roomPhotoTotal(photos.counts, targetId)
        : photoCountFor(photos.counts, context, targetId, { questionId, lineageId });
  const key = photoKey(context, targetId, questionId);
  return <PhotoEntryButton count={count} expanded={photos.isExpanded(key)} onToggle={() => photos.toggle(key)} />;
}

interface PhotoCardPanelProps extends PhotoCardTarget {
  /** Names the host already has, outermost first (room, surface); used by a surface section, ignored by aggregated ones. */
  locationSegments?: ReadonlyArray<string | null | undefined>;
  /** The room a SURFACE belongs to (keeps the room's total in step when a photo is added or archived there). */
  roomId?: string;
  /** Overrides the caption location with a resolver (an inspection's panel names each photo's question). */
  locationLabel?: (attachment: PhotoAttachmentRead) => string;
}

export function PhotoCardPanel({
  context,
  targetId,
  questionId,
  lineageId,
  locationSegments = [],
  roomId,
  locationLabel,
}: PhotoCardPanelProps) {
  const photos = useProjectPhotos();
  const { t } = useI18n();
  const open = photos?.isExpanded(photoKey(context, targetId, questionId)) ?? false;
  // The object and a room show EVERY photo below them (view / edit); photos are ADDED on surfaces and as inspection evidence.
  const aggregated = context === 'PROJECT' || context === 'ROOM';
  const ensureLocations = photos?.ensureLocations;

  useEffect(() => {
    if (open && aggregated) ensureLocations?.(context === 'ROOM' ? targetId : undefined);
  }, [open, aggregated, context, targetId, ensureLocations]);

  if (!photos || !open) return null;
  return (
    <PhotoSection
      projectId={photos.projectId}
      context={context}
      targetId={targetId}
      questionId={questionId}
      lineageId={lineageId}
      roomId={roomId}
      allowUpload={context === 'SURFACE' || context === 'INSPECTION' || context === 'FINDING'}
      locationLabel={
        locationLabel ?? (aggregated ? photos.resolveLocation : buildLocationPath(locationSegments, t.photos.caption))
      }
      onCountAdjust={photos.adjust}
    />
  );
}
