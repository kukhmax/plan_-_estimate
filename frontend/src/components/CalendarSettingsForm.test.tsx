import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/calendar';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { CalendarSettings } from '../types/calendar';
import { CalendarSettingsForm } from './CalendarSettingsForm';

vi.mock('../api/calendar', () => ({ fetchCalendarSettings: vi.fn(), saveCalendarSettings: vi.fn() }));

const SETTINGS: CalendarSettings = {
  timezone: 'Europe/Warsaw', enabled: true, kind_overrides: {}, quiet_from: '21:00:00', quiet_to: '07:00:00', digest_at: '08:00:00', language: null,
  kinds: [
    { kind: 'BREAK_END', default_push: true, sends: true },
    { kind: 'PAYMENT_TERM', default_push: false, sends: false },
  ],
  timezones: ['Europe/Warsaw', 'Europe/Berlin'],
};

function form(onSaved = vi.fn()) {
  render(
    <I18nProvider>
      <CalendarSettingsForm onSaved={onSaved} />
    </I18nProvider>,
  );
  return { onSaved };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.fetchCalendarSettings).mockResolvedValue(SETTINGS);
  vi.mocked(api.saveCalendarSettings).mockImplementation(async (body) => ({ ...SETTINGS, ...body, kinds: SETTINGS.kinds } as CalendarSettings));
});

describe('the settings form', () => {
  it('shows what the server says, times without the seconds', async () => {
    form();
    expect(await screen.findByLabelText('settings-quiet-from')).toHaveValue('21:00');
    expect(screen.getByLabelText('settings-quiet-to')).toHaveValue('07:00');
    expect(screen.getByLabelText('settings-digest')).toHaveValue('08:00');
    expect(screen.getByLabelText('settings-timezone')).toHaveValue('Europe/Warsaw');
    expect(screen.getByLabelText('settings-enabled')).toBeChecked();
    expect(screen.getByLabelText('settings-kind-BREAK_END')).toBeChecked();
    expect(screen.getByLabelText('settings-kind-PAYMENT_TERM')).not.toBeChecked();
    expect(screen.getByText('Koniec przerwy technologicznej')).toBeInTheDocument();
  });

  it('stores only the choices that differ from the defaults of the kinds', async () => {
    const { onSaved } = form();
    fireEvent.click(await screen.findByLabelText('settings-kind-PAYMENT_TERM')); // on, the default is off
    fireEvent.click(screen.getByLabelText('settings-kind-BREAK_END')); // off, the default is on
    fireEvent.change(screen.getByLabelText('settings-timezone'), { target: { value: 'Europe/Berlin' } });
    fireEvent.change(screen.getByLabelText('settings-digest'), { target: { value: '09:00' } });
    fireEvent.change(screen.getByLabelText('settings-language'), { target: { value: 'ru' } });
    fireEvent.click(screen.getByLabelText('settings-save'));
    await waitFor(() => expect(api.saveCalendarSettings).toHaveBeenCalled());
    expect(api.saveCalendarSettings).toHaveBeenCalledWith({
      timezone: 'Europe/Berlin', enabled: true, kind_overrides: { PAYMENT_TERM: true, BREAK_END: false },
      quiet_from: '21:00', quiet_to: '07:00', digest_at: '09:00', language: 'ru',
    });
    expect(await screen.findByRole('status')).toHaveTextContent('Ustawienia zapisane.');
    expect(onSaved).toHaveBeenCalled();
  });

  it('offers the four languages of the messages and saves Ukrainian and English too (V2-7)', async () => {
    form();
    await screen.findByLabelText('settings-save');
    const select = screen.getByLabelText('settings-language');
    expect([...select.querySelectorAll('option')].map((option) => option.getAttribute('value'))).toEqual(['', 'pl', 'ru', 'uk', 'en']);
    for (const code of ['uk', 'en']) {
      vi.mocked(api.saveCalendarSettings).mockClear();
      fireEvent.change(select, { target: { value: code } });
      fireEvent.click(screen.getByLabelText('settings-save'));
      await waitFor(() => expect(api.saveCalendarSettings).toHaveBeenCalled());
      expect(vi.mocked(api.saveCalendarSettings).mock.calls[0][0].language).toBe(code);
    }
  });

  it('sends no overrides when nothing was changed', async () => {
    form();
    fireEvent.click(await screen.findByLabelText('settings-save'));
    await waitFor(() => expect(api.saveCalendarSettings).toHaveBeenCalled());
    expect(vi.mocked(api.saveCalendarSettings).mock.calls[0][0].kind_overrides).toEqual({}); // toMatchObject({}) would match anything
    expect(vi.mocked(api.saveCalendarSettings).mock.calls[0][0].language).toBeNull();
  });

  it('says why the server refused', async () => {
    vi.mocked(api.saveCalendarSettings).mockRejectedValueOnce(new ApiError('x', 422, 'DIGEST_IN_QUIET_HOURS'));
    form();
    fireEvent.click(await screen.findByLabelText('settings-save'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Poranne podsumowanie nie może wypadać w ciszy nocnej.');
  });

  it('says it when the settings cannot be read', async () => {
    vi.mocked(api.fetchCalendarSettings).mockRejectedValueOnce(new Error('down'));
    form();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać kalendarza.');
  });

  it('has controls at least 44 px tall and is in Russian when the application is', async () => {
    localStorage.setItem('locale', 'ru');
    form();
    const save = await screen.findByLabelText('settings-save');
    expect(save.className).toContain('min-h-11');
    expect(save).toHaveTextContent('Сохранить настройки');
    expect(screen.getByLabelText('settings-digest').className).toContain('min-h-11');
  });
});
