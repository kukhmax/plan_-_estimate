import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from './hooks/useI18n';
import type { AccessEntry, AccessOverview } from './types/access';
import { AccessScreen } from './components/AccessScreen';

vi.mock('./api/access', () => ({ fetchAccess: vi.fn(), decideAccess: vi.fn(), removeAccess: vi.fn(), saveAccessSettings: vi.fn() }));
import { decideAccess, fetchAccess, removeAccess, saveAccessSettings } from './api/access';

const entry = (id: number, status: AccessEntry['status'], over: Partial<AccessEntry> = {}): AccessEntry => ({
  id: `e${id}`, telegram_user_id: id, username: `user${id}`, first_name: `Name${id}`, last_name: 'Long-Surname-That-Must-Wrap', status,
  is_admin: false, created_at: '2026-10-19T08:00:00Z', decided_at: null, ...over,
});
const ADMIN = entry(1, 'ACTIVE', { is_admin: true });
const PENDING = entry(2, 'PENDING');
const BLOCKED = entry(3, 'BLOCKED');
const overview = (over: Partial<AccessOverview> = {}): AccessOverview => ({
  settings: { closed: true, contact: '@owner' }, entries: [PENDING, ADMIN, BLOCKED], ...over,
});

function renderScreen() {
  return render(<I18nProvider><AccessScreen /></I18nProvider>);
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(fetchAccess).mockResolvedValue(overview());
  vi.mocked(decideAccess).mockResolvedValue(PENDING);
  vi.mocked(removeAccess).mockResolvedValue(undefined);
  vi.mocked(saveAccessSettings).mockResolvedValue({ closed: true, contact: '@owner' });
});

describe('the access list screen', () => {
  it('groups the accounts by status and shows who they are', async () => {
    renderScreen();
    const pending = await screen.findByLabelText('access-group-pending');
    expect(within(pending).getByText(/Name2 Long-Surname/)).toBeInTheDocument();
    expect(within(pending).getByText(/@user2 · ID 2/)).toBeInTheDocument();
    expect(within(screen.getByLabelText('access-group-active')).getByText('Administrator')).toBeInTheDocument();
    expect(within(screen.getByLabelText('access-group-blocked')).getByLabelText('access-row-3')).toBeInTheDocument();
    expect(screen.getByLabelText('access-closed')).toBeChecked();
    expect(screen.getByLabelText('access-contact')).toHaveValue('@owner');
  });

  it('gives an administrator no buttons', async () => {
    renderScreen();
    const row = await screen.findByLabelText('access-row-1');
    expect(within(row).queryAllByRole('button')).toHaveLength(0);
  });

  it('admits a pending account and reloads the list', async () => {
    renderScreen();
    fireEvent.click(await screen.findByLabelText('access-admit-2'));
    await waitFor(() => expect(decideAccess).toHaveBeenCalledWith('e2', 'ACTIVE'));
    await waitFor(() => expect(fetchAccess).toHaveBeenCalledTimes(2));
  });

  it('blocks a pending account, unblocks a blocked one, removes a blocked one', async () => {
    renderScreen();
    fireEvent.click(await screen.findByLabelText('access-block-2'));
    await waitFor(() => expect(decideAccess).toHaveBeenCalledWith('e2', 'BLOCKED'));
    await waitFor(() => expect(fetchAccess).toHaveBeenCalledTimes(2));
    fireEvent.click(await screen.findByLabelText('access-admit-3'));
    await waitFor(() => expect(decideAccess).toHaveBeenCalledWith('e3', 'ACTIVE'));
    await waitFor(() => expect(fetchAccess).toHaveBeenCalledTimes(3));
    fireEvent.click(await screen.findByLabelText('access-remove-3'));
    await waitFor(() => expect(removeAccess).toHaveBeenCalledWith('e3'));
  });

  it('offers no removal for an admitted account', async () => {
    vi.mocked(fetchAccess).mockResolvedValue(overview({ entries: [ADMIN, entry(4, 'ACTIVE')] }));
    renderScreen();
    expect(await screen.findByLabelText('access-block-4')).toBeInTheDocument();
    expect(screen.queryByLabelText('access-remove-4')).toBeNull();
    expect(screen.queryByLabelText('access-admit-4')).toBeNull();
  });

  it('opens the registration with the switch', async () => {
    renderScreen();
    fireEvent.click(await screen.findByLabelText('access-closed'));
    await waitFor(() => expect(saveAccessSettings).toHaveBeenCalledWith({ closed: false }));
  });

  it('saves the contact only when it changed, and says so', async () => {
    renderScreen();
    const save = await screen.findByLabelText('access-save-contact');
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('access-contact'), { target: { value: 'Jan, @jan' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(saveAccessSettings).toHaveBeenCalledWith({ contact: 'Jan, @jan' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Zapisano');
  });

  it('shows an error and can try again when the list does not load', async () => {
    vi.mocked(fetchAccess).mockRejectedValueOnce(new Error('x'));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('access-retry'));
    expect(await screen.findByLabelText('access-group-pending')).toBeInTheDocument();
  });

  it('shows an error when a decision fails', async () => {
    vi.mocked(decideAccess).mockRejectedValueOnce(new Error('x'));
    renderScreen();
    fireEvent.click(await screen.findByLabelText('access-admit-2'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zapisać');
  });

  it('is written in Russian too', async () => {
    localStorage.setItem('locale', 'ru');
    renderScreen();
    await screen.findByLabelText('access-group-pending');
    expect(screen.getByRole('heading', { name: /Ожидают/ })).toBeInTheDocument();
  });
});
