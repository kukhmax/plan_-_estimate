import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PrepareOfflineButton } from './components/PrepareOfflineButton';
import { I18nProvider } from './hooks/useI18n';
import { reportNetworkFailure, resetConnectionForTests } from './offline/connection';
import * as prepare from './offline/prepareProject';

vi.mock('./offline/prepareProject', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./offline/prepareProject')>();
  return { ...actual, prepareProjectOffline: vi.fn(), lastPrepared: vi.fn() };
});

const view = () => render(<I18nProvider><PrepareOfflineButton projectId="p1" /></I18nProvider>);

describe('PrepareOfflineButton (Stage 19B)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    resetConnectionForTests();
    vi.mocked(prepare.lastPrepared).mockResolvedValue(null);
  });

  it('explains what it does and is a compact, wrapping control', async () => {
    view();
    const button = screen.getByLabelText('prepare-offline-button');
    expect(button).toHaveTextContent('Przygotuj do pracy offline');
    expect(button.className).toContain('min-h-11');
    expect(screen.getByLabelText('prepare-offline')).toHaveTextContent('Zapisuje na telefonie obiekt');
    await waitFor(() => expect(prepare.lastPrepared).toHaveBeenCalledWith('p1'));
  });

  it('shows the progress while it works and the result when it is done', async () => {
    let finish: (value: { saved: number; failed: number }) => void = () => {};
    vi.mocked(prepare.prepareProjectOffline).mockImplementation(async (_id, onProgress) => {
      onProgress?.({ done: 3, total: 12 });
      return new Promise((resolve) => {
        finish = resolve;
      });
    });
    view();
    fireEvent.click(screen.getByLabelText('prepare-offline-button'));

    expect(await screen.findByLabelText('prepare-progress')).toHaveTextContent('Zapisuję na telefonie… 3 / 12');
    expect(screen.getByLabelText('prepare-offline-button')).toBeDisabled();

    await act(async () => finish({ saved: 12, failed: 0 }));
    expect(await screen.findByText('Zapisano na telefonie: 12 pozycji. Możesz pracować bez zasięgu.')).toBeInTheDocument();
    expect(screen.getByLabelText('prepare-offline-button')).toBeEnabled();
    expect(screen.getByText(/Ostatnio przygotowano:/)).toBeInTheDocument();
  });

  it('says what did not work and offers to try again', async () => {
    vi.mocked(prepare.prepareProjectOffline).mockResolvedValue({ saved: 9, failed: 2 });
    view();
    fireEvent.click(screen.getByLabelText('prepare-offline-button'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Zapisano 9, nie udało się 2. Spróbuj ponownie przy lepszym zasięgu.');
    expect(screen.queryByText(/Ostatnio przygotowano:/)).toBeNull(); // an incomplete preparation is not "prepared"
    expect(screen.getByLabelText('prepare-offline-button')).toBeEnabled();
  });

  it('cannot start without a connection', async () => {
    view();
    act(() => reportNetworkFailure());
    expect(screen.getByLabelText('prepare-offline-button')).toBeDisabled();
    expect(screen.getByText('Wymaga połączenia z internetem.')).toBeInTheDocument();
  });

  it('shows when the object was prepared last, and speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(prepare.lastPrepared).mockResolvedValue({ at: new Date(2026, 9, 15, 9, 5).getTime(), saved: 5, failed: 0 });
    view();
    expect(screen.getByLabelText('prepare-offline-button')).toHaveTextContent('Подготовить к работе офлайн');
    expect(await screen.findByText(/Последняя подготовка: 15\.10.*09:05/)).toBeInTheDocument();
  });
});
