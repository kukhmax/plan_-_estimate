import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SyncScreen } from './components/SyncScreen';
import { I18nProvider } from './hooks/useI18n';
import { getPhotoUploadQueue, resetPhotoUploadQueue } from './hooks/usePhotoUploadQueue';
import { reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from './offline/connection';
import { addOp, listOps, updateOp } from './offline/outbox';
import { resetSyncStateForTests, setDrainRequester, setDrainRunner } from './offline/outboxState';
import type { OutboxKind } from './offline/opTypes';
import { setOfflineOwner } from './offline/readCache';
import { freshIndexedDb } from './test/fakeIdb';

vi.mock('./api/photos', async () => {
  const actual = await vi.importActual<typeof import('./api/photos')>('./api/photos');
  return { ...actual, uploadPhoto: vi.fn(), fetchPhoto: vi.fn() };
});
vi.mock('./hooks/usePhotoStorage', () => ({ refreshPhotoStorage: vi.fn() }));

const P = '11111111-1111-4111-8111-111111111111';
const make = (kind: OutboxKind, label: string, createdAt = Date.UTC(2026, 9, 16, 8, 30)) =>
  addOp({ ownerId: 'owner-1', createdAt, method: 'POST', path: `/api/projects/${P}/notes`, body: { id: label }, kind, entityId: label, label });
const view = (onClose = vi.fn()) => ({ onClose, ...render(<I18nProvider><SyncScreen onClose={onClose} /></I18nProvider>) });
const refuse = async (seq: number, status: number, code?: string) => updateOp(seq, { status: 'failed', attempts: 1, error: { status, code, message: 'English words of the server' } });

describe('the screen "Synchronizacja" (Stage 19E)', () => {
  beforeEach(async () => {
    localStorage.clear();
    resetConnectionForTests();
    resetSyncStateForTests();
    resetPhotoUploadQueue();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
  });
  afterEach(() => resetPhotoUploadQueue());

  it('says that everything is sent when nothing waits', async () => {
    view();
    expect(await screen.findByLabelText('sync-nothing')).toHaveTextContent('Wszystko wysłane');
    expect(screen.queryByLabelText('sync-attention')).toBeNull();
    expect(screen.getByLabelText('sync-now')).toBeDisabled();
  });

  it('lists what waits, by kind and name, with the time it was made', async () => {
    await make('room.create', 'Salon');
    await make('note.update', 'Zamówić gładź');
    view();
    const section = await screen.findByLabelText('sync-waiting');
    expect(section).toHaveTextContent('Czekają na wysłanie (2)');
    expect(section).toHaveTextContent('Nowe pomieszczenie: Salon');
    expect(section).toHaveTextContent('Zmiana notatki: Zamówić gładź');
    expect(section).toHaveTextContent(/Zrobiono: /);
  });

  it('puts what the server refused first, with the reason in words (never the server\'s English) and keeps the rest apart', async () => {
    const a = await make('room.create', 'Salon');
    await make('note.create', 'Notatka');
    await refuse(a!.seq as number, 404);
    view();
    const attention = await screen.findByLabelText('sync-attention');
    expect(attention).toHaveTextContent('Wymagają uwagi (1)');
    expect(attention).toHaveTextContent('Nowe pomieszczenie: Salon');
    expect(attention).toHaveTextContent('Nie znaleziono rekordu na serwerze');
    expect(attention).not.toHaveTextContent('English words of the server');
    expect(screen.getByLabelText('sync-waiting')).toHaveTextContent('Czekają na wysłanie (1)');
    const order = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(order[0]).toMatch(/Wymagają uwagi/);
  });

  it('a status changed elsewhere says so', async () => {
    const a = await make('execution.transition', 'COMPLETED');
    await refuse(a!.seq as number, 409, 'WORK_EXECUTION_CONFLICT');
    view();
    expect(await screen.findByLabelText('sync-attention')).toHaveTextContent('Status tej pracy zmienił się w międzyczasie na serwerze.');
  });

  it('"Ponów" puts a refused change back to waiting and asks for the sending', async () => {
    const a = await make('room.create', 'Salon');
    await refuse(a!.seq as number, 422);
    const ask = vi.fn();
    setDrainRequester(ask);
    view();

    fireEvent.click(await screen.findByLabelText(`sync-retry-${a!.seq}`));

    await waitFor(async () => expect((await listOps())[0]).toMatchObject({ status: 'pending', attempts: 0 }));
    expect((await listOps())[0].error).toBeUndefined();
    expect(ask).toHaveBeenCalled();
    expect(await screen.findByLabelText('sync-waiting')).toHaveTextContent('Salon');
    expect(screen.queryByLabelText('sync-attention')).toBeNull();
  });

  it('"Usuń zmianę" asks twice, warns about what depends on it, and then removes only that change', async () => {
    const a = await make('room.create', 'Salon');
    await make('note.create', 'Notatka');
    await refuse(a!.seq as number, 422);
    view();

    fireEvent.click(await screen.findByLabelText(`sync-discard-${a!.seq}`));
    expect(screen.getByRole('alert')).toHaveTextContent('Zmiany od niej zależne mogą zostać odrzucone');
    expect((await listOps())).toHaveLength(2); // nothing yet

    fireEvent.click(screen.getByLabelText(`sync-discard-no-${a!.seq}`));
    expect(screen.getByLabelText(`sync-discard-${a!.seq}`)).toBeInTheDocument(); // taken back

    fireEvent.click(screen.getByLabelText(`sync-discard-${a!.seq}`));
    fireEvent.click(screen.getByLabelText(`sync-discard-yes-${a!.seq}`));

    await waitFor(async () => expect((await listOps()).map((o) => o.label)).toEqual(['Notatka']));
    await waitFor(() => expect(screen.queryByLabelText('sync-attention')).toBeNull());
  });

  it('without a signal says so, and does not offer to send', async () => {
    await make('room.create', 'Salon');
    reportNetworkFailure();
    view();
    expect(await screen.findByLabelText('sync-screen-offline')).toHaveTextContent('Brak połączenia');
    expect(screen.getByLabelText('sync-now')).toBeDisabled();
    act(() => reportNetworkSuccess());
    await waitFor(() => expect(screen.getByLabelText('sync-now')).toBeEnabled());
    expect(screen.queryByLabelText('sync-screen-offline')).toBeNull();
  });

  it('"Synchronizuj teraz" sends the waiting changes at once', async () => {
    await make('room.create', 'Salon');
    const run = vi.fn(async () => ({ sent: 1, refused: 0, stoppedBy: null }));
    setDrainRunner(run);
    // the button uses the engine's own function: stub the network it ends in
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 201, json: async () => ({}) }) as unknown as Response));
    localStorage.setItem('access_token', 'tok');
    view();

    fireEvent.click(await screen.findByLabelText('sync-now'));

    await waitFor(async () => expect(await listOps()).toEqual([]));
    expect(fetch).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it('shows the photos that wait, and the ones that failed among the refused', async () => {
    reportNetworkFailure();
    const queue = getPhotoUploadQueue();
    queue.enqueue([new File(['x'], 'wall.jpg', { type: 'image/jpeg' })], { projectId: P, context: 'SURFACE', surfaceId: 's' }, 'CAMERA');
    queue.enqueue([new File(['x'], 'broken.gif', { type: 'image/gif' })], { projectId: P, context: 'SURFACE', surfaceId: 's' }, 'GALLERY'); // refused at once
    view();

    expect(await screen.findByLabelText('sync-photos')).toHaveTextContent('Zdjęcia (1)');
    expect(screen.getByLabelText('sync-photos')).toHaveTextContent('wall.jpg');
    const attention = screen.getByLabelText('sync-attention');
    expect(attention).toHaveTextContent('Wymagają uwagi (1)');
    expect(within(attention).getByText('broken.gif')).toBeInTheDocument();
    expect(screen.queryByLabelText('sync-nothing')).toBeNull();
  });

  it('closes by its button and by Escape', async () => {
    const { onClose } = view();
    fireEvent.click(await screen.findByLabelText('sync-close'));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('speaks Russian, and long names and reasons wrap inside a 44 px high tap target', async () => {
    localStorage.setItem('locale', 'ru');
    const long = 'очень_длинное_название_без_пробелов_'.repeat(5);
    const a = await make('room.create', long);
    await refuse(a!.seq as number, 409);
    view();
    const attention = await screen.findByLabelText('sync-attention');
    expect(attention).toHaveTextContent('Требуют внимания (1)');
    expect(attention).toHaveTextContent('Новое помещение');
    expect(attention).toHaveTextContent('На сервере уже другая версия');
    expect(screen.getByLabelText('sync-now')).toHaveTextContent('Синхронизировать сейчас');
    for (const control of [screen.getByLabelText('sync-close'), screen.getByLabelText(`sync-retry-${a!.seq}`), screen.getByLabelText(`sync-discard-${a!.seq}`), screen.getByLabelText('sync-now')]) {
      expect(control.className).toMatch(/min-h-11/);
    }
    expect(screen.getByLabelText(`sync-refused-${a!.seq}`).querySelector('p.break-words')).not.toBeNull();
  });
});
