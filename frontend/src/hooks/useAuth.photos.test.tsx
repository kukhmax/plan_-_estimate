import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { freshIndexedDb } from '../test/fakeIdb';
import { reportNetworkFailure, resetConnectionForTests } from '../offline/connection';
import { idbPhotoStore } from '../offline/photoStore';
import { setOfflineOwner } from '../offline/readCache';
import { useAuth } from './useAuth';
import { getPhotoUploadQueue, resetPhotoUploadQueue } from './usePhotoUploadQueue';

vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth');
  return { ...actual, loginWithTelegram: vi.fn(async () => ({ access_token: 't', user: { id: 'owner-1' }, is_dev_auth: false })) };
});
vi.mock('./useTelegramWebApp', () => ({ useTelegramWebApp: () => ({ isAvailable: true, initData: 'signed' }) }));
vi.mock('./usePhotoStorage', () => ({ refreshPhotoStorage: vi.fn() }));

describe('signing in puts back the photos kept on the phone (Stage 19D)', () => {
  beforeEach(async () => {
    localStorage.clear();
    resetPhotoUploadQueue();
    resetConnectionForTests();
    await freshIndexedDb();
  });
  afterEach(() => resetPhotoUploadQueue());

  it('the photos of the owner who signs in are in the queue again', async () => {
    await setOfflineOwner('owner-1');
    await idbPhotoStore.put(
      {
        id: 'q1', uploadId: 'up-1', file: null, name: 'IMG.jpg', size: 3, target: { projectId: 'p1', context: 'SURFACE', surfaceId: 's1' },
        source: 'CAMERA', state: 'queued', progress: 0, attempt: 0, previewUrl: null, error: null, result: null, notBefore: 0,
        networkRetries: 0, busyRetried: false, verify: false, authRetried: false, saveFailed: false,
      },
      new File([new Uint8Array([1, 2, 3])], 'IMG.jpg', { type: 'image/jpeg' }),
      null,
    );
    reportNetworkFailure(); // the application is opened in the basement: the photo waits

    renderHook(() => useAuth());

    await waitFor(() => expect(getPhotoUploadQueue().getItems().map((i) => i.name)).toEqual(['IMG.jpg']));
  });
});
