import { useEffect, useRef, useState } from 'react';
import { subscribePhotoUploadDone, usePhotoUploadQueue } from '../hooks/usePhotoUploadQueue';
import { usePhotoStorage } from '../hooks/usePhotoStorage';
import { useI18n } from '../hooks/useI18n';
import type { PhotoCaptureSource } from '../types/photo';
import { MAX_FILES_PER_SELECTION } from '../utils/photoUploadQueue';
import { PhotoPicker } from './PhotoPicker';
import { PhotoUploadQueueList } from './PhotoUploadQueueList';

const MB = 1024 * 1024;

interface PressurePhotoAddProps {
  projectId: string;
  /** The id of a photo the phone has just finished sending: the form ticks it (it belongs to the object, like any photo of it). */
  onUploaded: (attachmentId: string) => void;
}

/**
 * V2-12b follow-up: the manometer is photographed on the spot -- the camera and the gallery buttons of every photo of the app, the same upload queue (it waits for the signal in a
 * basement and sends when it is back), and a photo that arrived is ticked in the list below at once. The photo is a photo of the OBJECT (the object's own list shows it).
 */
export function PressurePhotoAdd({ projectId, onUploaded }: PressurePhotoAddProps) {
  const { t } = useI18n();
  const storage = usePhotoStorage();
  const queue = usePhotoUploadQueue(projectId);
  const [note, setNote] = useState<string | null>(null);
  const uploaded = useRef(onUploaded);
  uploaded.current = onUploaded;
  const { dismiss } = queue;

  useEffect(
    () =>
      subscribePhotoUploadDone((item) => {
        if (item.target.projectId !== projectId || item.target.context !== 'PROJECT') return;
        const id = item.result?.attachment?.id;
        if (id) uploaded.current(id);
        dismiss(item.id);
      }),
    [projectId, dismiss],
  );

  const mine = queue.items.filter((item) => item.target.projectId === projectId && item.target.context === 'PROJECT');
  const canUpload = storage.usable && storage.uploadsEnabled && storage.mediaAvailable;
  const offNote =
    storage.usable && storage.mediaAvailable && !storage.uploadsEnabled
      ? storage.state === 'FULL'
        ? t.photos.storage.full
        : t.photos.section.uploads_off_note
      : null;

  const handleFiles = (files: File[], source: PhotoCaptureSource) => {
    const result = queue.enqueue(files, { projectId, context: 'PROJECT' }, source);
    const notes: string[] = [];
    if (result.ignored > 0) notes.push(t.photos.picker.too_many_selected.replace('{count}', String(MAX_FILES_PER_SELECTION)));
    if (result.rejected > 0) notes.push(t.photos.picker.queue_full.replace('{limit}', String(Math.round(queue.limitBytes / MB))));
    setNote(notes.length > 0 ? notes.join(' ') : null);
  };

  return (
    <div aria-label="pressure-photo-add" className="space-y-2">
      {canUpload && <PhotoPicker onFiles={handleFiles} />}
      {offNote && <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">{offNote}</p>}
      {note && <p role="status" className="break-words text-xs text-[var(--tg-theme-hint-color)]">{note}</p>}
      <PhotoUploadQueueList items={mine} onCancel={queue.cancel} onRetry={queue.retry} onRetryAsNew={queue.retryAsNew} onDismiss={queue.dismiss} />
    </div>
  );
}
