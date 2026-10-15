import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/calendar';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { Reminder } from '../types/calendar';
import { ReminderSheet, type ReminderContext } from './ReminderSheet';

vi.mock('../api/calendar', () => ({ createReminder: vi.fn(), cancelReminder: vi.fn() }));

const REMINDER: Reminder = {
  id: 'r-1', project_id: 'p', room_id: 'r', surface_id: 's', occurrence_key: 'k', origin: 'USER', kind: 'USER', title: 'Zadzwonić',
  send_at: '2026-10-20T08:00:00Z', status: 'PENDING', close_on_status: null,
};

function open(context: ReminderContext = {}, props: Partial<React.ComponentProps<typeof ReminderSheet>> = {}) {
  const onClose = vi.fn();
  const onChanged = vi.fn();
  render(
    <I18nProvider>
      <ReminderSheet context={context} onClose={onClose} onChanged={onChanged} {...props} />
    </I18nProvider>,
  );
  return { onClose, onChanged };
}

const presets = () => screen.getAllByRole('radio').map((radio) => radio.getAttribute('aria-label'));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.createReminder).mockResolvedValue(REMINDER);
  vi.mocked(api.cancelReminder).mockResolvedValue({ ...REMINDER, status: 'CANCELLED' });
});

describe('the presets', () => {
  it('offers only the presets that can be made for the place', () => {
    open({});
    expect(presets()).toEqual(['reminder-preset-IN_1H', 'reminder-preset-IN_3H', 'reminder-preset-TOMORROW', 'reminder-preset-CUSTOM']);
  });

  it('adds the day of the work once it has a planned date and the end of the break once the work is done', () => {
    open({ occurrenceKey: 'k', hasPlannedDate: true, hasBreakEnd: true });
    expect(presets()).toEqual([
      'reminder-preset-BREAK_END', 'reminder-preset-WORK_DAY', 'reminder-preset-DAY_BEFORE',
      'reminder-preset-IN_1H', 'reminder-preset-IN_3H', 'reminder-preset-TOMORROW', 'reminder-preset-CUSTOM',
    ]);
  });

  it('preselects one, so the usual case is a preset and one press of save', () => {
    open({});
    expect(screen.getByLabelText('reminder-preset-IN_1H')).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByLabelText('reminder-preset-TOMORROW'));
    expect(screen.getByLabelText('reminder-preset-TOMORROW')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('reminder-preset-IN_1H')).toHaveAttribute('aria-checked', 'false');
  });

  it('keeps every control at least 44 px tall and says the names in Polish', () => {
    open({});
    for (const radio of screen.getAllByRole('radio')) expect(radio.className).toContain('min-h-11');
    expect(screen.getByLabelText('reminder-save').className).toContain('min-h-11');
    expect(screen.getByLabelText('reminder-preset-TOMORROW')).toHaveTextContent('Jutro rano');
  });
});

describe('saving', () => {
  it('sends the preset with the place and the note, then closes and tells the caller', async () => {
    const { onClose, onChanged } = open({ projectId: 'p', roomId: 'r', surfaceId: 's', occurrenceKey: 'k', defaultTitle: 'Gładź — Ściana A', hasPlannedDate: true });
    fireEvent.click(screen.getByLabelText('reminder-preset-WORK_DAY'));
    fireEvent.click(screen.getByLabelText('reminder-save'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.createReminder).toHaveBeenCalledWith({
      preset: 'WORK_DAY', title: 'Gładź — Ściana A', project_id: 'p', room_id: 'r', surface_id: 's', occurrence_key: 'k',
    });
    expect(onChanged).toHaveBeenCalled();
  });

  it('puts the owners own note before the name of the work', async () => {
    open({ occurrenceKey: 'k', projectId: 'p', defaultTitle: 'Gładź — Ściana A' });
    fireEvent.change(screen.getByLabelText('reminder-note'), { target: { value: '  Zadzwonić do klienta ' } });
    fireEvent.click(screen.getByLabelText('reminder-save'));
    await waitFor(() => expect(api.createReminder).toHaveBeenCalled());
    expect(vi.mocked(api.createReminder).mock.calls[0][0].title).toBe('Zadzwonić do klienta');
  });

  it('for an own time sends the day and the hour, not an instant (the server knows the zone)', async () => {
    open({});
    fireEvent.click(screen.getByLabelText('reminder-preset-CUSTOM'));
    fireEvent.change(screen.getByLabelText('reminder-date'), { target: { value: '2026-10-25' } });
    fireEvent.change(screen.getByLabelText('reminder-time'), { target: { value: '14:30' } });
    fireEvent.change(screen.getByLabelText('reminder-note'), { target: { value: 'x' } });
    fireEvent.click(screen.getByLabelText('reminder-save'));
    await waitFor(() => expect(api.createReminder).toHaveBeenCalled());
    expect(vi.mocked(api.createReminder).mock.calls[0][0]).toMatchObject({ preset: 'CUSTOM', local_date: '2026-10-25', local_time: '14:30' });
    expect(vi.mocked(api.createReminder).mock.calls[0][0]).not.toHaveProperty('send_at');
  });

  it('does not show the date and the time before they are needed', () => {
    open({});
    expect(screen.queryByLabelText('reminder-date')).toBeNull();
  });

  it.each([
    ['NO_PLANNED_DATE', 'Najpierw ustaw planowaną datę pracy.'],
    ['IN_THE_PAST', 'Ten termin już minął.'],
    ['TITLE_REQUIRED', 'Wpisz notatkę.'],
    ['SOMETHING_NEW', 'Nie udało się zapisać przypomnienia.'],
  ])('says what is wrong in words (%s) and stays open', async (code, text) => {
    vi.mocked(api.createReminder).mockRejectedValue(new ApiError('x', 422, code));
    const { onClose } = open({});
    fireEvent.click(screen.getByLabelText('reminder-save'));
    expect(await screen.findByRole('alert')).toHaveTextContent(text);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('cannot be pressed twice while it saves', async () => {
    let finish: (value: Reminder) => void = () => undefined;
    vi.mocked(api.createReminder).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    open({});
    fireEvent.click(screen.getByLabelText('reminder-save'));
    expect(screen.getByLabelText('reminder-save')).toBeDisabled();
    finish(REMINDER);
    await waitFor(() => expect(api.createReminder).toHaveBeenCalledTimes(1));
  });
});

describe('the reminders that are already set', () => {
  it('lists them with their time and removes one', async () => {
    const { onChanged } = open({}, { existing: [REMINDER], formatWhen: (iso) => `at ${iso.slice(11, 16)}` });
    expect(screen.getByLabelText('reminder-existing')).toHaveTextContent('🔔 at 08:00 — Zadzwonić');
    fireEvent.click(screen.getByLabelText('reminder-remove-r-1'));
    await waitFor(() => expect(api.cancelReminder).toHaveBeenCalledWith('r-1'));
    expect(onChanged).toHaveBeenCalled();
  });

  it('shows no list when there is nothing set, and closes on cancel', () => {
    const { onClose } = open({});
    expect(screen.queryByLabelText('reminder-existing')).toBeNull();
    fireEvent.click(screen.getByLabelText('reminder-cancel'));
    expect(onClose).toHaveBeenCalled();
  });
});

describe('the Russian words', () => {
  it('uses the presets of the Russian dictionary', () => {
    localStorage.setItem('locale', 'ru');
    open({});
    expect(screen.getByLabelText('reminder-preset-TOMORROW')).toHaveTextContent('Завтра утром');
    expect(screen.getByLabelText('reminder-save')).toHaveTextContent('Сохранить напоминание');
  });
});
