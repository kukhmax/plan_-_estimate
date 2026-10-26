import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as queueHook from '../hooks/usePhotoUploadQueue';
import * as storageHook from '../hooks/usePhotoStorage';
import { I18nProvider } from '../hooks/useI18n';
import type { QueueItem } from '../utils/photoUploadQueue';
import { PressurePhotoAdd } from './PressurePhotoAdd';

vi.mock('../hooks/usePhotoStorage', () => ({ usePhotoStorage: vi.fn() }));
vi.mock('../hooks/usePhotoUploadQueue', () => ({ usePhotoUploadQueue: vi.fn(), subscribePhotoUploadDone: vi.fn() }));
vi.mock('./PhotoPicker', () => ({
  PhotoPicker: ({ onFiles }: { onFiles: (files: File[], source: 'CAMERA' | 'GALLERY') => void }) => (
    <button type="button" aria-label="fake-picker" onClick={() => onFiles([new File(['x'], 'm.jpg', { type: 'image/jpeg' })], 'CAMERA')}>pick</button>
  ),
}));

const storage = (over = {}) => ({ status: 'ready', data: null, usable: true, uploadsEnabled: true, mediaAvailable: true, state: 'OK', refresh: vi.fn(), ...over });
const item = (over: Partial<QueueItem> = {}): QueueItem => ({
  id: 'q1', uploadId: 'u1', file: null, name: 'm.jpg', size: 1, target: { projectId: 'p1', context: 'PROJECT' }, source: 'CAMERA', state: 'uploading', progress: 0.4, attempt: 1,
  previewUrl: null, error: null, result: null, notBefore: 0, networkRetries: 0, busyRetried: false, verify: false, authRetried: false, saveFailed: false, refusedAtOnce: false, ...over,
});
let listener: ((i: QueueItem) => void) | null = null;
const enqueue = vi.fn(() => ({ accepted: 1, ignored: 0, rejected: 0 }));
const dismiss = vi.fn();
const view = (items: QueueItem[] = []) => ({ items, enqueue, cancel: vi.fn(), retry: vi.fn(), retryAsNew: vi.fn(), dismiss, dismissDone: vi.fn(), kick: vi.fn(), usedBytes: 0, limitBytes: 200 * 1024 * 1024, nearlyFull: false });

const renderAdd = (onUploaded = vi.fn()) => ({ onUploaded, ...render(<I18nProvider><PressurePhotoAdd projectId="p1" onUploaded={onUploaded} /></I18nProvider>) });

describe('PressurePhotoAdd (V2-12b follow-up)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listener = null;
    vi.mocked(storageHook.usePhotoStorage).mockReturnValue(storage() as never);
    vi.mocked(queueHook.usePhotoUploadQueue).mockReturnValue(view() as never);
    vi.mocked(queueHook.subscribePhotoUploadDone).mockImplementation((l) => { listener = l; return () => { listener = null; }; });
  });
  afterEach(cleanup);

  it('puts a photo taken here into the queue as a photo of the object', async () => {
    renderAdd();
    await act(async () => { fireEvent.click(screen.getByLabelText('fake-picker')); });
    expect(enqueue).toHaveBeenCalledWith([expect.any(File)], { projectId: 'p1', context: 'PROJECT' }, 'CAMERA');
  });

  it('hands the id of a photo that arrived to the form and clears its row; other uploads are none of its business', () => {
    const { onUploaded } = renderAdd();
    act(() => listener?.(item({ state: 'done', result: { asset: {} as never, attachment: { id: 'att1' } as never, thumbnailUrl: null, displayUrl: null, urlsExpireAt: null } })));
    expect(onUploaded).toHaveBeenCalledWith('att1');
    expect(dismiss).toHaveBeenCalledWith('q1');
    onUploaded.mockClear(); dismiss.mockClear();
    act(() => listener?.(item({ target: { projectId: 'p1', context: 'SURFACE', surfaceId: 's' }, state: 'done' })));
    act(() => listener?.(item({ target: { projectId: 'other', context: 'PROJECT' }, state: 'done' })));
    expect(onUploaded).not.toHaveBeenCalled();
    expect(dismiss).not.toHaveBeenCalled();
  });

  it('shows the rows of its own uploads only', () => {
    vi.mocked(queueHook.usePhotoUploadQueue).mockReturnValue(view([item(), item({ id: 'q2', target: { projectId: 'p1', context: 'SURFACE', surfaceId: 's' } })]) as never);
    renderAdd();
    expect(screen.getAllByText(/m\.jpg/)).toHaveLength(1);
  });

  it('offers no picker and says why when the uploads are off or the space is full', () => {
    vi.mocked(storageHook.usePhotoStorage).mockReturnValue(storage({ uploadsEnabled: false, state: 'FULL' }) as never);
    renderAdd();
    expect(screen.queryByLabelText('fake-picker')).toBeNull();
    expect(screen.getByText(/Limit miejsca na zdjęcia/)).toBeInTheDocument();
  });
});
