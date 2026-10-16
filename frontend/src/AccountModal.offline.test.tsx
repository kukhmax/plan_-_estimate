import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountModal } from './components/AccountModal';
import { I18nProvider } from './hooks/useI18n';
import { getPhotoUploadQueue, resetPhotoUploadQueue } from './hooks/usePhotoUploadQueue';
import { reportNetworkFailure, resetConnectionForTests } from './offline/connection';
import { loadStoredPhotos } from './offline/photoStore';
import { addOp, listOps } from './offline/outbox';
import { resetSyncStateForTests } from './offline/outboxState';
import { loadRead, saveRead, setOfflineOwner } from './offline/readCache';
import { freshIndexedDb } from './test/fakeIdb';

const user = {
  id: 'owner-1', telegram_user_id: 1, username: 'jan', first_name: 'Jan', last_name: 'K', language_code: 'pl',
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
};
const view = () => render(<I18nProvider><AccountModal user={user} isDevAuth={false} onClose={() => {}} /></I18nProvider>);

describe('"Wyczyść dane offline" in the account window (Stage 19B)', () => {
  beforeEach(async () => {
    localStorage.clear();
    resetSyncStateForTests();
    resetPhotoUploadQueue();
    resetConnectionForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    await saveRead('/api/projects', { items: [] });
  });
  afterEach(() => {
    resetPhotoUploadQueue();
    resetConnectionForTests();
  });

  it('removes the copies kept on the phone only after a second tap', async () => {
    view();
    expect(screen.getByLabelText('offline-data')).toHaveTextContent('Dane zapisane na telefonie do pracy bez zasięgu.');
    fireEvent.click(screen.getByLabelText('clear-offline-button'));
    expect(screen.getByText(/Usunąć dane offline z telefonu\?/)).toBeInTheDocument();
    expect(await loadRead('/api/projects')).not.toBeNull(); // nothing yet

    fireEvent.click(screen.getByLabelText('clear-offline-confirm'));

    expect(await screen.findByText('Dane offline usunięto.')).toBeInTheDocument();
    expect(await loadRead('/api/projects')).toBeNull();
  });

  it('a first tap can be taken back', async () => {
    view();
    fireEvent.click(screen.getByLabelText('clear-offline-button'));
    fireEvent.click(screen.getByLabelText('clear-offline-cancel'));
    expect(screen.getByLabelText('clear-offline-button')).toBeInTheDocument();
    await waitFor(async () => expect(await loadRead('/api/projects')).not.toBeNull());
  });

  it('warns when changes made without a signal have not been sent yet, and removes them too when confirmed', async () => {
    await addOp({ ownerId: 'owner-1', createdAt: 1, method: 'POST', path: '/api/projects/p/notes', body: { body: 'x' }, kind: 'note.create', entityId: 'n', label: 'x' });
    view();
    fireEvent.click(screen.getByLabelText('clear-offline-button'));
    expect(await screen.findByLabelText('clear-offline-pending')).toHaveTextContent('zmiany niewysłane na serwer zostaną utracone (1)');

    fireEvent.click(screen.getByLabelText('clear-offline-confirm'));

    expect(await screen.findByText('Dane offline usunięto.')).toBeInTheDocument();
    expect(await listOps()).toEqual([]);
  });

  it('warns about the photos waiting on the phone, and removes them with the rest when confirmed (Stage 19D)', async () => {
    reportNetworkFailure(); // no signal: the photo stays on the phone
    getPhotoUploadQueue().enqueue([new File(['x'], 'IMG.jpg', { type: 'image/jpeg' })], { projectId: 'p', context: 'SURFACE', surfaceId: 's' }, 'CAMERA');
    await waitFor(async () => expect(await loadStoredPhotos()).toHaveLength(1));
    view();
    fireEvent.click(screen.getByLabelText('clear-offline-button'));
    expect(await screen.findByLabelText('clear-offline-photos')).toHaveTextContent('zdjęcia niewysłane na serwer zostaną utracone (1)');

    fireEvent.click(screen.getByLabelText('clear-offline-confirm'));

    expect(await screen.findByText('Dane offline usunięto.')).toBeInTheDocument();
    expect(await loadStoredPhotos()).toEqual([]);
    expect(getPhotoUploadQueue().getItems()).toEqual([]);
  });

  it('gives no such warning when nothing waits', () => {
    view();
    fireEvent.click(screen.getByLabelText('clear-offline-button'));
    expect(screen.queryByLabelText('clear-offline-pending')).toBeNull();
    expect(screen.queryByLabelText('clear-offline-photos')).toBeNull();
  });

  it('speaks Russian', () => {
    localStorage.setItem('locale', 'ru');
    view();
    expect(screen.getByLabelText('clear-offline-button')).toHaveTextContent('Очистить офлайн-данные');
  });
});

describe('the account window leads to the screen of what waits (Stage 19E)', () => {
  beforeEach(async () => {
    localStorage.clear();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
  });

  it('has the button, with the count of what waits, and opens the screen through the host', async () => {
    await addOp({ ownerId: 'owner-1', createdAt: 1, method: 'POST', path: '/api/projects/p/notes', body: { body: 'x' }, kind: 'note.create', entityId: 'n', label: 'x' });
    const open = vi.fn();
    render(<I18nProvider><AccountModal user={user} isDevAuth={false} onClose={() => {}} onOpenSync={open} /></I18nProvider>);
    const button = await screen.findByLabelText('open-sync-screen');
    await waitFor(() => expect(button).toHaveTextContent('Synchronizacja (1)'));
    expect(button.className).toMatch(/min-h-11/);
    fireEvent.click(button);
    expect(open).toHaveBeenCalledTimes(1);
  });

  it('is not drawn when the host gives no way to open it', () => {
    view();
    expect(screen.queryByLabelText('open-sync-screen')).toBeNull();
  });
});
