import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { AccountModal } from './components/AccountModal';
import { I18nProvider } from './hooks/useI18n';
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
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    await saveRead('/api/projects', { items: [] });
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

  it('gives no such warning when nothing waits', () => {
    view();
    fireEvent.click(screen.getByLabelText('clear-offline-button'));
    expect(screen.queryByLabelText('clear-offline-pending')).toBeNull();
  });

  it('speaks Russian', () => {
    localStorage.setItem('locale', 'ru');
    view();
    expect(screen.getByLabelText('clear-offline-button')).toHaveTextContent('Очистить офлайн-данные');
  });
});
