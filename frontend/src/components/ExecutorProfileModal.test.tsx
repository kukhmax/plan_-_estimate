import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as profileApi from '../api/executorProfile';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { ExecutorProfile } from '../types/executorProfile';
import { ExecutorProfileModal } from './ExecutorProfileModal';

vi.mock('../api/executorProfile', async () => {
  const actual = await vi.importActual<typeof import('../api/executorProfile')>('../api/executorProfile');
  return { ...actual, fetchExecutorProfile: vi.fn(), saveExecutorProfile: vi.fn() };
});

const SAVED: ExecutorProfile = {
  id: 'p1', name: 'Jan Kowalski', nip: '7740001454', street: 'ul. Długa 1', postal_code: '30-001', city: 'Kraków',
  phone: '+48 600 100 200', email: 'jan@example.pl', bank_account: '61109010140000071219812874',
  created_at: '2026-10-08T10:00:00Z', updated_at: '2026-10-08T10:00:00Z',
};

function renderModal(onClose = vi.fn()) {
  render(
    <I18nProvider>
      <ExecutorProfileModal onClose={onClose} />
    </I18nProvider>,
  );
  return onClose;
}

function invalid(fields: Record<string, string>) {
  return new ApiError('bad', 422, 'EXECUTOR_PROFILE_INVALID', { code: 'EXECUTOR_PROFILE_INVALID', message: 'bad', fields });
}

describe('ExecutorProfileModal (Stage 15C)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('shows the loading state, then an empty form when nothing is saved yet', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(null);
    renderModal();
    expect(screen.getByRole('status')).toHaveTextContent('Ładowanie profilu…');
    expect(await screen.findByLabelText('NIP')).toHaveValue('');
    expect(screen.getByLabelText('Nazwa firmy lub imię i nazwisko')).toHaveValue('');
  });

  it('fills the form from the saved profile', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(SAVED);
    renderModal();
    expect(await screen.findByLabelText('NIP')).toHaveValue('7740001454');
    expect(screen.getByLabelText('Miejscowość')).toHaveValue('Kraków');
    expect(screen.getByLabelText('Numer rachunku bankowego')).toHaveValue('61109010140000071219812874');
  });

  it('uses mobile-appropriate inputs with touch-sized controls', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(null);
    renderModal();
    expect(await screen.findByLabelText('NIP')).toHaveAttribute('inputmode', 'numeric');
    expect(screen.getByLabelText('Kod pocztowy')).toHaveAttribute('inputmode', 'numeric');
    expect(screen.getByLabelText('Numer rachunku bankowego')).toHaveAttribute('inputmode', 'numeric');
    expect(screen.getByLabelText('Telefon')).toHaveAttribute('type', 'tel');
    expect(screen.getByLabelText('E-mail')).toHaveAttribute('type', 'email');
    for (const input of screen.getAllByRole('textbox')) expect(input.className).toContain('min-h-11');
    expect(screen.getByRole('button', { name: 'Zapisz' }).className).toContain('min-h-11');
    expect(screen.getByRole('button', { name: 'close-executor-profile' }).className).toContain('min-w-11');
  });

  it('offers a retry when loading fails and loads again', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockRejectedValueOnce(new Error('net')).mockResolvedValueOnce(SAVED);
    renderModal();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać profilu.');
    expect(screen.queryByLabelText('NIP')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    expect(await screen.findByLabelText('NIP')).toHaveValue('7740001454');
  });

  it('saves the whole form and shows the normalised values the backend returned', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(null);
    vi.mocked(profileApi.saveExecutorProfile).mockResolvedValue(SAVED);
    renderModal();
    fireEvent.change(await screen.findByLabelText('Nazwa firmy lub imię i nazwisko'), { target: { value: 'Jan Kowalski' } });
    fireEvent.change(screen.getByLabelText('NIP'), { target: { value: '774-000-14-54' } });
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
    expect(await screen.findByText('Profil zapisany.')).toBeInTheDocument();
    expect(profileApi.saveExecutorProfile).toHaveBeenCalledWith({
      name: 'Jan Kowalski', nip: '774-000-14-54', street: '', postal_code: '', city: '', phone: '', email: '', bank_account: '',
    });
    expect(screen.getByLabelText('NIP')).toHaveValue('7740001454');
  });

  it('marks every wrong field with its own message and clears one when it is edited', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(null);
    vi.mocked(profileApi.saveExecutorProfile).mockRejectedValue(
      invalid({ name: 'NAME_REQUIRED', nip: 'NIP_INVALID', bank_account: 'BANK_ACCOUNT_INVALID' }),
    );
    renderModal();
    await screen.findByLabelText('NIP');
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
    expect(await screen.findByText('Popraw zaznaczone pola.')).toBeInTheDocument();
    expect(screen.getByText('Podaj nazwę wykonawcy.')).toBeInTheDocument();
    expect(screen.getByText('Niepoprawny NIP (10 cyfr, suma kontrolna).')).toBeInTheDocument();
    expect(screen.getByText('Niepoprawny numer rachunku (26 cyfr).')).toBeInTheDocument();
    expect(screen.getByLabelText('NIP')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Telefon')).not.toHaveAttribute('aria-invalid');
    fireEvent.change(screen.getByLabelText('NIP'), { target: { value: '7740001454' } });
    expect(screen.queryByText('Niepoprawny NIP (10 cyfr, suma kontrolna).')).toBeNull();
    expect(screen.getByLabelText('NIP')).not.toHaveAttribute('aria-invalid');
    expect(screen.getByText('Podaj nazwę wykonawcy.')).toBeInTheDocument();
  });

  it('shows a generic message for any other failure and keeps the typed values', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(null);
    vi.mocked(profileApi.saveExecutorProfile).mockRejectedValue(new ApiError('Request failed (500)', 500));
    renderModal();
    fireEvent.change(await screen.findByLabelText('Miejscowość'), { target: { value: 'Łódź' } });
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zapisać profilu.');
    expect(screen.getByLabelText('Miejscowość')).toHaveValue('Łódź');
  });

  it('does not send a second save while one is running', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(null);
    let release: (value: ExecutorProfile) => void = () => undefined;
    vi.mocked(profileApi.saveExecutorProfile).mockReturnValue(new Promise((resolve) => { release = resolve; }));
    renderModal();
    await screen.findByLabelText('NIP');
    const form = screen.getByRole('button', { name: 'Zapisz' }).closest('form') as HTMLFormElement;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(profileApi.saveExecutorProfile).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Zapisywanie...' })).toBeDisabled();
    release(SAVED);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zapisz' })).toBeEnabled());
  });

  it('closes from the cross and from the close button', async () => {
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(null);
    const onClose = renderModal();
    await screen.findByLabelText('NIP');
    fireEvent.click(screen.getByRole('button', { name: 'close-executor-profile' }));
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('is localised in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(profileApi.fetchExecutorProfile).mockResolvedValue(null);
    vi.mocked(profileApi.saveExecutorProfile).mockRejectedValue(invalid({ postal_code: 'POSTAL_CODE_INVALID' }));
    renderModal();
    expect(await screen.findByLabelText('Почтовый индекс')).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Профиль исполнителя' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Индекс в формате 00-000.')).toBeInTheDocument();
  });
});
