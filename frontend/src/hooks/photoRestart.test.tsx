import { act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoUploadResponse } from '../types/photo';
import { freshIndexedDb } from '../test/fakeIdb';
import { reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from '../offline/connection';
import { resetSyncStateForTests, setOutboxCounts } from '../offline/outboxState';
import { loadStoredPhotos } from '../offline/photoStore';
import { setOfflineOwner } from '../offline/readCache';
import { getPhotoUploadQueue, resetPhotoUploadQueue, restorePhotoQueue } from './usePhotoUploadQueue';

vi.mock('../api/photos', async () => {
  const actual = await vi.importActual<typeof import('../api/photos')>('../api/photos');
  return { ...actual, uploadPhoto: vi.fn(), fetchPhoto: vi.fn() };
});
vi.mock('./usePhotoStorage', () => ({ refreshPhotoStorage: vi.fn() }));
vi.mock('../offline/thumbnail', () => ({ makeThumbnail: vi.fn(async () => 'data:image/jpeg;base64,TT') }));
import { fetchPhoto, uploadPhoto } from '../api/photos';

// Stage 19D end to end on the phone's storage: a photo taken without a signal survives the closing of the application,
// is sent when the signal is back, and only after the changes made before it have reached the server.

const jpeg = (name = 'IMG.jpg') => new File([new Uint8Array([9, 8, 7])], name, { type: 'image/jpeg' });
const target = { projectId: 'p1', context: 'SURFACE' as const, surfaceId: 's1', roomId: 'r1' };
const answer = (id: string) => ({ asset: { id }, attachment: null, thumbnail_url: 't', display_url: 'd', urls_expire_at: 'x', storage: { state: 'OK' } }) as unknown as PhotoUploadResponse;
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 30)); });

describe('photos across a restart of the application (Stage 19D)', () => {
  beforeEach(async () => {
    localStorage.clear();
    resetPhotoUploadQueue();
    resetConnectionForTests();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    vi.mocked(uploadPhoto).mockReset().mockImplementation(async (params) => answer(params.uploadId));
    vi.mocked(fetchPhoto).mockReset().mockRejectedValue(Object.assign(new Error('nf'), { status: 404 }));
  });
  afterEach(() => resetPhotoUploadQueue());

  it('a photo taken without a signal waits on the phone, survives the restart and is sent when the signal returns', async () => {
    reportNetworkFailure();
    await act(async () => {
      getPhotoUploadQueue().enqueue([jpeg()], target, 'CAMERA');
    });
    await settle();
    expect(uploadPhoto).not.toHaveBeenCalled(); // nothing is tried without a signal
    const [kept] = await loadStoredPhotos();
    expect(kept).toMatchObject({ ownerId: 'owner-1', state: 'queued', attempt: 0, name: 'IMG.jpg' });

    // the application is closed and opened again: a new queue, empty, finds the photo on the phone
    resetPhotoUploadQueue();
    await act(async () => {
      await restorePhotoQueue();
    });
    expect(getPhotoUploadQueue().getItems()).toHaveLength(1);
    expect(getPhotoUploadQueue().getItems()[0]).toMatchObject({ state: 'queued', name: 'IMG.jpg', file: null });
    expect(uploadPhoto).not.toHaveBeenCalled(); // still no signal

    await act(async () => {
      reportNetworkSuccess();
    });
    await settle();
    expect(uploadPhoto).toHaveBeenCalledTimes(1);
    const sent = vi.mocked(uploadPhoto).mock.calls[0][0];
    expect(sent.uploadId).toBe(kept.uploadId);
    expect(sent.file.name).toBe('IMG.jpg');
    expect(sent.file.size).toBe(3);
    expect(getPhotoUploadQueue().getItems()[0].state).toBe('done');
    expect(await loadStoredPhotos()).toEqual([]); // sent: nothing is left on the phone
  });

  it('after the restart the row of a waiting photo still shows what the photo is (the small picture kept with it, Stage 19E)', async () => {
    reportNetworkFailure();
    await act(async () => {
      getPhotoUploadQueue().enqueue([jpeg()], target, 'CAMERA');
    });
    await settle();
    expect((await loadStoredPhotos())[0].thumb).toBe('data:image/jpeg;base64,TT');

    resetPhotoUploadQueue();
    await act(async () => {
      await restorePhotoQueue();
    });
    expect(getPhotoUploadQueue().getItems()[0].previewUrl).toBe('data:image/jpeg;base64,TT');
  });

  it('waits for the changes made before it (the wall the photo belongs to) to reach the server', async () => {
    setOutboxCounts({ pending: 2, failed: 0 });
    await act(async () => {
      getPhotoUploadQueue().enqueue([jpeg()], target, 'CAMERA');
    });
    await settle();
    expect(uploadPhoto).not.toHaveBeenCalled();

    await act(async () => {
      setOutboxCounts({ pending: 1, failed: 0 });
    });
    await settle();
    expect(uploadPhoto).not.toHaveBeenCalled();

    await act(async () => {
      setOutboxCounts({ pending: 0, failed: 1 }); // a refused change does not hold the photos back for ever
    });
    await settle();
    expect(uploadPhoto).toHaveBeenCalledTimes(1);
  });

  it('a photo whose upload had been started before the closing is looked up on the server first, not sent twice', async () => {
    vi.mocked(uploadPhoto).mockImplementation(() => new Promise(() => {})); // the application is closed in the middle of it
    await act(async () => {
      getPhotoUploadQueue().enqueue([jpeg()], target, 'CAMERA');
    });
    await settle();
    expect(uploadPhoto).toHaveBeenCalledTimes(1);
    const [kept] = await loadStoredPhotos();
    expect(kept.attempt).toBe(1); // written down: the server may have it

    resetPhotoUploadQueue();
    vi.mocked(fetchPhoto).mockReset().mockResolvedValue({
      asset: { id: kept.uploadId }, attachments: [{ id: 'att' }], thumbnail_url: 't', display_url: 'd', urls_expire_at: null,
    } as unknown as Awaited<ReturnType<typeof fetchPhoto>>);
    await act(async () => {
      await restorePhotoQueue();
    });
    await settle();
    expect(fetchPhoto).toHaveBeenCalledWith('p1', kept.uploadId);
    expect(uploadPhoto).toHaveBeenCalledTimes(1); // the server had it: nothing is sent again
    expect(getPhotoUploadQueue().getItems()[0].state).toBe('done');
    expect(await loadStoredPhotos()).toEqual([]);
  });

  it('does not bring back the photos of another owner, and removes them when the owner changes', async () => {
    reportNetworkFailure();
    await act(async () => {
      getPhotoUploadQueue().enqueue([jpeg()], target, 'CAMERA');
    });
    await settle();
    expect(await loadStoredPhotos()).toHaveLength(1);

    await act(async () => {
      await setOfflineOwner('owner-2'); // another person signs in on this phone: everything of the first is wiped
    });
    expect(await loadStoredPhotos()).toEqual([]);
    expect(getPhotoUploadQueue().getItems()).toEqual([]); // the queue in memory let go as well
    await act(async () => {
      await restorePhotoQueue();
    });
    expect(getPhotoUploadQueue().getItems()).toEqual([]);
  });
});
