import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/pressureTests';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import * as peopleApi from '../api/representatives';
import { I18nProvider } from '../hooks/useI18n';
import ru from '../locales/ru.json';
import type { Pressure } from '../types/pressure';
import type { ProjectRepresentative } from '../types/representative';
import { ProjectPressureTests } from './ProjectPressureTests';

vi.mock('../api/pressureTests', () => ({
  fetchPressureTests: vi.fn(),
  openPressureDraft: vi.fn(),
  updatePressure: vi.fn(),
  abandonPressureDraft: vi.fn(),
  issuePressure: vi.fn(),
}));
vi.mock('../api/documents', () => ({ previewPressureTestPdf: vi.fn() }));
vi.mock('../api/representatives', () => ({ fetchRepresentatives: vi.fn() }));

const PHOTOS = ['f1', 'f2', 'f3', 'f4', 'f5'].map((id, i) => ({
  id, caption: i === 0 ? 'Manometr' : null, place: i === 0 ? 'Łazienka' : null, captured_at: null, created_at: '2026-10-20T08:05:00',
}));

function protocol(over: Partial<Pressure> = {}): Pressure {
  return {
    id: 'z1', project_id: 'p1', sequence: 1, status: 'DRAFT', held_on: '2026-10-20', held_time: '08:15', customer_absent: false, notified_on: null, attendees: [],
    system: null, section: null, medium: null, test_pressure_bar: null, duration_min: null, pressure_drop_bar: null, photo_ids: [], result: null, remarks: null,
    photo_options: PHOTOS, blockers: [{ code: 'SYSTEM_REQUIRED', details: null }], created_at: 'x', updated_at: 'x', ...over,
  };
}
const person = (over: Partial<ProjectRepresentative> = {}): ProjectRepresentative => ({
  id: 'rep1', project_id: 'p1', side: 'CUSTOMER', name: 'Anna Nowak', role_title: 'Właścicielka', phone: null, email: null,
  may_accept_and_sign: true, is_archived: false, created_at: 'x', updated_at: 'x', ...over,
});

const renderCard = () => render(<I18nProvider><ProjectPressureTests projectId="p1" /></I18nProvider>);
async function begin() {
  renderCard();
  const start = await screen.findByLabelText('start-pressure');
  await act(async () => { fireEvent.click(start); });
  return screen.findByLabelText('pressure-form');
}
const lastChange = () => {
  const calls = vi.mocked(api.updatePressure).mock.calls;
  return calls[calls.length - 1][2];
};
const field = (label: string, value: string) => {
  const input = screen.getByLabelText(label);
  fireEvent.change(input, { target: { value } });
  fireEvent.blur(input);
};

describe('ProjectPressureTests (V2-12b)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchPressureTests).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.openPressureDraft).mockResolvedValue(protocol());
    vi.mocked(api.updatePressure).mockImplementation(async () => protocol());
    vi.mocked(peopleApi.fetchRepresentatives).mockResolvedValue({ items: [person(), person({ id: 'rep2', name: 'Piotr Archiwalny', is_archived: true })], total: 2 });
  });
  afterEach(cleanup);

  it('offers a full-width, touch-sized start and writes the day and hour of now when the draft has none', async () => {
    vi.mocked(api.openPressureDraft).mockResolvedValue(protocol({ held_on: null, held_time: null }));
    renderCard();
    const button = await screen.findByLabelText('start-pressure');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('w-full');
    expect(button).toHaveTextContent('Rozpocznij protokół próby');
    expect(api.openPressureDraft).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(button); });
    await screen.findByLabelText('pressure-form');
    await waitFor(() => expect(api.updatePressure).toHaveBeenCalledWith('p1', 'z1', {
      held_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), held_time: expect.stringMatching(/^\d{2}:\d{2}$/) }));
  });

  it('mentions the latest issued protocol and offers a new one', async () => {
    vi.mocked(api.fetchPressureTests).mockResolvedValue({ items: [protocol({ id: 'z0', sequence: 3, status: 'ISSUED' })], total: 1 });
    renderCard();
    expect(await screen.findByText('Ostatni protokół: nr 3 — wystawiony')).toBeInTheDocument();
    expect(screen.getByLabelText('start-pressure')).toHaveTextContent('Nowy protokół próby');
  });

  it('saves the system, the medium and the result at once', async () => {
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-system-HEATING')); });
    expect(lastChange()).toEqual({ system: 'HEATING' });
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-medium-AIR')); });
    expect(lastChange()).toEqual({ medium: 'AIR' });
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-result-NEGATIVE')); });
    expect(lastChange()).toEqual({ result: 'NEGATIVE' });
    for (const id of ['pressure-system-HEATING', 'pressure-medium-AIR', 'pressure-result-NEGATIVE']) expect(screen.getByLabelText(id).className).toContain('min-h-11');
  });

  it('sends the pressures as typed (decimal keyboard) and the duration as a whole number', async () => {
    await begin();
    expect(screen.getByLabelText('pressure-test-pressure')).toHaveAttribute('inputmode', 'decimal');
    expect(screen.getByLabelText('pressure-duration')).toHaveAttribute('inputmode', 'numeric');
    await act(async () => { field('pressure-test-pressure', '6,5'); });
    expect(lastChange()).toEqual({ test_pressure_bar: '6,5' });
    await act(async () => { field('pressure-duration', '30'); });
    expect(lastChange()).toEqual({ duration_min: 30 });
    await act(async () => { field('pressure-drop', '0'); });
    expect(lastChange()).toEqual({ pressure_drop_bar: '0' });
  });

  it('refuses a duration that is not a whole number of minutes before sending it', async () => {
    await begin();
    await act(async () => { field('pressure-duration', '1,5'); });
    expect(await screen.findByLabelText('pressure-error')).toHaveTextContent('nieprawidłowa wartość');
    await act(async () => { field('pressure-duration', '2000'); });
    expect(await screen.findByLabelText('pressure-error')).toHaveTextContent('poza dozwolonym zakresem');
    expect(api.updatePressure).not.toHaveBeenCalled();
  });

  it('lets at most four photos be chosen', async () => {
    vi.mocked(api.openPressureDraft).mockResolvedValue(protocol({ photo_ids: ['f1', 'f2', 'f3', 'f4'] }));
    await begin();
    expect(screen.getByLabelText('pressure-photo-f1')).toBeEnabled();
    expect(screen.getByLabelText('pressure-photo-f5')).toBeDisabled();
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-photo-f1')); });
    expect(lastChange()).toEqual({ photo_ids: ['f2', 'f3', 'f4'] });
  });

  it('swaps the people present for the day of the notice when the customer did not come', async () => {
    await begin();
    expect(screen.getByLabelText('pressure-person-rep1')).toBeInTheDocument();
    expect(screen.queryByText(/Archiwalny/)).toBeNull();
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-person-rep1')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }] });
    vi.mocked(api.updatePressure).mockImplementation(async () => protocol({ customer_absent: true }));
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-absent')); });
    expect(lastChange()).toEqual({ customer_absent: true });
    expect(await screen.findByLabelText('pressure-notified-on')).toBeInTheDocument();
    expect(screen.queryByLabelText('pressure-person-rep1')).toBeNull();
  });

  it('adds and removes a person who is not among the people of the object', async () => {
    await begin();
    await act(async () => { fireEvent.change(screen.getByLabelText('pressure-extra'), { target: { value: 'Jan Kowalski, hydraulik' } }); });
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-extra-add')); });
    expect(lastChange()).toEqual({ attendees: [{ name: 'Jan Kowalski', role: 'hydraulik' }] });
  });

  it('shows what is missing and keeps the issue button off until nothing is', async () => {
    await begin();
    expect(await screen.findByLabelText('gate-SYSTEM_REQUIRED')).toHaveTextContent('Wybierz rodzaj instalacji.');
    expect(screen.getByLabelText('issue-pressure')).toBeDisabled();
    vi.mocked(api.updatePressure).mockImplementation(async () => protocol({ blockers: [] }));
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-system-GAS')); });
    await waitFor(() => expect(screen.getByLabelText('issue-pressure')).toBeEnabled());
    vi.mocked(api.issuePressure).mockResolvedValue({} as never);
    vi.mocked(api.fetchPressureTests).mockResolvedValue({ items: [protocol({ status: 'ISSUED' })], total: 1 });
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-pressure')); });
    expect(api.issuePressure).toHaveBeenCalledWith('p1', 'z1');
    expect(await screen.findByLabelText('pressure-note')).toHaveTextContent('Protokół został wystawiony');
  });

  it('shows the blockers the server sends when issuing is refused', async () => {
    await begin();
    vi.mocked(api.updatePressure).mockImplementation(async () => protocol({ blockers: [] }));
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-system-GAS')); });
    vi.mocked(api.issuePressure).mockRejectedValue(new ApiError('English', 422, 'PRESSURE_GATE_BLOCKED', {
      code: 'PRESSURE_GATE_BLOCKED', details: { blockers: [{ code: 'RESULT_REQUIRED', details: null }] } }));
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-pressure')); });
    expect(await screen.findByLabelText('gate-RESULT_REQUIRED')).toHaveTextContent('Wybierz wynik próby.');
  });

  it.each([
    ['OUT_OF_RANGE', 'wartość poza dozwolonym zakresem'],
    ['TOO_MANY_PHOTOS', 'można wybrać najwyżej 4 zdjęcia'],
    ['UNKNOWN_PHOTO', 'zdjęcie nie należy do tego obiektu lub zostało usunięte'],
  ])('says in words why the server refused (%s)', async (reason, words) => {
    await begin();
    vi.mocked(api.updatePressure).mockRejectedValueOnce(new ApiError('English', 422, 'PRESSURE_INVALID', { code: 'PRESSURE_INVALID', details: { key: 'x', reason } }));
    await act(async () => { fireEvent.click(screen.getByLabelText('pressure-system-GAS')); });
    expect(await screen.findByLabelText('pressure-error')).toHaveTextContent(words);
  });

  it('asks twice before discarding the draft', async () => {
    await begin();
    vi.mocked(api.abandonPressureDraft).mockResolvedValue(undefined as never);
    await act(async () => { fireEvent.click(screen.getByLabelText('abandon-pressure-draft')); });
    expect(api.abandonPressureDraft).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(screen.getByLabelText('abandon-pressure-draft')); });
    expect(api.abandonPressureDraft).toHaveBeenCalledWith('p1', 'z1');
    expect(await screen.findByLabelText('pressure-note')).toHaveTextContent('Szkic odrzucony.');
  });

  it('sends the working version to the chat', async () => {
    renderCard();
    vi.mocked(documentsApi.previewPressureTestPdf).mockResolvedValue(undefined as never);
    const preview = await screen.findByLabelText('preview-pressure');
    await act(async () => { fireEvent.click(preview); });
    expect(documentsApi.previewPressureTestPdf).toHaveBeenCalledWith('p1');
    expect(await screen.findByLabelText('pressure-note')).toHaveTextContent('Wersja robocza protokołu wysłana');
  });

  it('speaks Russian when the language is Russian', async () => {
    localStorage.setItem('locale', 'ru');
    await begin();
    expect(screen.getByLabelText('pressure-system-COLD_WATER')).toHaveTextContent(ru.pressure.systems.COLD_WATER);
    expect(screen.getByLabelText('pressure-result-POSITIVE')).toHaveTextContent(ru.pressure.result_options.POSITIVE);
  });
});
