import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as catalogApi from '../api/contractCatalog';
import * as api from '../api/downtimes';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import * as peopleApi from '../api/representatives';
import { I18nProvider } from '../hooks/useI18n';
import ru from '../locales/ru.json';
import type { ContractCatalog } from '../types/contractCatalog';
import type { Downtime, DowntimeDay } from '../types/downtime';
import type { ProjectRepresentative } from '../types/representative';
import { ProjectDowntime, nextWorkingDay } from './ProjectDowntime';

vi.mock('../api/downtimes', () => ({
  fetchDowntimes: vi.fn(),
  openDowntime: vi.fn(),
  updateDowntime: vi.fn(),
  abandonDowntime: vi.fn(),
  issueDowntimeNotice: vi.fn(),
  issueDowntimeProtocol: vi.fn(),
}));
vi.mock('../api/documents', () => ({ previewDowntimeNoticePdf: vi.fn(), previewDowntimeProtocolPdf: vi.fn() }));
vi.mock('../api/contractCatalog', () => ({ fetchContractCatalog: vi.fn() }));
vi.mock('../api/representatives', () => ({ fetchRepresentatives: vi.fn() }));

// the real catalogues of the server: the screen must offer every cause they hold
const files = import.meta.glob('../../../backend/app/domain/contracts/catalog/*.json', { eager: true, import: 'default' }) as Record<string, unknown>;
const read = (name: string) => Object.entries(files).find(([path]) => path.endsWith(`/${name}`))![1];
const CATALOG = {
  requirements: read('premises_requirements.json'), instruments: read('assessment_instruments.json'), evaluation: read('evaluation_conditions.json'),
  defects: read('defect_classes.json'), tolerances: read('tolerances.json'), questionnaire: read('questionnaire.json'), work_kinds: read('concealed_work_kinds.json'),
  downtime_causes: read('downtime_causes.json'),
} as ContractCatalog;

const day = (date: string, weekday: number, over: Partial<DowntimeDay> = {}): DowntimeDay => ({ date, weekday, other_work: false, note: null, ...over });
const BLOCKED = [{ code: 'CAUSE_REQUIRED', details: null }, { code: 'PHOTOS_REQUIRED', details: null }] as Downtime['blockers'];

function draft(over: Partial<Downtime> = {}): Downtime {
  return {
    id: 'e1', project_id: 'p1', sequence: 1, status: 'DRAFT', cause_key: null, cause_text: null, cause_note: null, room_ids: [], noticed_on: '2026-10-12', noticed_time: '08:30',
    notice_channel: null, photo_ids: [], need_text: null, need_by: null, days: [], held_on: null, held_time: null, attendees: [], signature_refused: false, deadline_note: null,
    notes: null, notice_number: null, notice_issued_at: null, protocol_issued_at: null, photos: [],
    photo_options: [{ id: 'f1', caption: 'Zamknięte drzwi', captured_at: '2026-10-12T08:05:00', room_name: 'Salon' }, { id: 'f2', caption: null, captured_at: null, room_name: null }],
    rooms: [{ id: 'r1', name: 'Salon' }, { id: 'r2', name: 'Kuchnia' }],
    settlement: { listed: 0, chargeable: 0, rate: null, amount: null, cap: null, capped: false, payable: null, limit_days: null, limit_exceeded: false },
    blockers: BLOCKED, contract: { id: 'c1', version: 1, status: 'SIGNED' }, created_at: 'x', updated_at: 'x', ...over,
  };
}
function noticed(over: Partial<Downtime> = {}): Downtime {
  return draft({
    status: 'NOTICED', cause_key: 'no_access', cause_text: 'Brak dostępu do Obiektu', notice_number: 'ZAWPRZ/2026/10/12/0830', photo_options: [], photo_ids: ['f1'],
    blockers: [{ code: 'DAYS_REQUIRED', details: null }, { code: 'NO_ATTENDEES', details: null }], ...over,
  });
}
const SETTLEMENT = { listed: 3, chargeable: 2, rate: '150.00', amount: '300.00', cap: '1200.00', capped: false, payable: '300.00', limit_days: null, limit_exceeded: false };
const person = (over: Partial<ProjectRepresentative> = {}): ProjectRepresentative => ({
  id: 'rep1', project_id: 'p1', side: 'CUSTOMER', name: 'Anna Nowak', role_title: 'Właścicielka', phone: null, email: null,
  may_accept_and_sign: true, is_archived: false, created_at: 'x', updated_at: 'x', ...over,
});

/** What the server answers to opening and to every save: the episode as it stands. */
function serve(episode: Downtime) {
  vi.mocked(api.openDowntime).mockResolvedValue(episode);
  vi.mocked(api.updateDowntime).mockResolvedValue(episode);
}

const renderCard = () => render(<I18nProvider><ProjectDowntime projectId="p1" /></I18nProvider>);
async function begin() {
  renderCard();
  const start = await screen.findByLabelText('start-downtime');
  await act(async () => { fireEvent.click(start); });
  return screen.findByLabelText('downtime-form');
}
const lastChange = () => {
  const calls = vi.mocked(api.updateDowntime).mock.calls;
  return calls[calls.length - 1][2];
};

describe('nextWorkingDay', () => {
  it('skips Saturday and Sunday and crosses months and years', () => {
    expect(nextWorkingDay('2026-10-14')).toBe('2026-10-15');  // Wednesday -> Thursday
    expect(nextWorkingDay('2026-10-16')).toBe('2026-10-19');  // Friday -> Monday
    expect(nextWorkingDay('2026-10-17')).toBe('2026-10-19');  // Saturday -> Monday
    expect(nextWorkingDay('2026-10-18')).toBe('2026-10-19');  // Sunday -> Monday
    expect(nextWorkingDay('2026-10-30')).toBe('2026-11-02');  // Friday, end of the month
    expect(nextWorkingDay('2026-12-31')).toBe('2027-01-01');  // a Thursday into the new year
  });
});

describe('ProjectDowntime (Stage 16I.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchDowntimes).mockResolvedValue({ items: [], total: 0 });
    serve(draft());
    vi.mocked(catalogApi.fetchContractCatalog).mockResolvedValue(CATALOG);
    vi.mocked(peopleApi.fetchRepresentatives).mockResolvedValue({ items: [person(), person({ id: 'rep2', name: 'Piotr Archiwalny', is_archived: true })], total: 2 });
  });
  afterEach(cleanup);

  it('offers to start and to print the blank forms with full-width touch-sized buttons; a new notice gets the day and hour of now', async () => {
    serve(draft({ noticed_on: null, noticed_time: null }));
    renderCard();
    const button = await screen.findByLabelText('start-downtime');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('w-full');
    expect(button).toHaveTextContent('Zgłoś przestój');
    for (const label of ['preview-downtime-notice', 'preview-downtime-protocol']) expect(screen.getByLabelText(label).className).toContain('min-h-11');
    expect(api.openDowntime).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(button); });
    await screen.findByLabelText('downtime-form');
    await waitFor(() => expect(api.updateDowntime).toHaveBeenCalledWith('p1', 'e1', {
      noticed_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), noticed_time: expect.stringMatching(/^\d{2}:\d{2}$/) }));
  });

  it('keeps what the server has, writes the day of now into a noticed episode that has no protocol day yet, and mentions the latest one', async () => {
    await begin();
    expect(api.updateDowntime).not.toHaveBeenCalled();
    cleanup();
    serve(noticed());
    await begin();
    await waitFor(() => expect(api.updateDowntime).toHaveBeenCalledWith('p1', 'e1', {
      held_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), held_time: expect.stringMatching(/^\d{2}:\d{2}$/) }));
    cleanup();
    vi.mocked(api.fetchDowntimes).mockResolvedValue({ items: [draft({ id: 'e0', sequence: 3, status: 'CLOSED' })], total: 1 });
    renderCard();
    expect(await screen.findByText('Ostatni przestój: nr 3 — zamknięty, protokół wystawiony')).toBeInTheDocument();
    expect(screen.getByLabelText('start-downtime')).toHaveTextContent('Zgłoś przestój');
  });

  it('continues the open episode the server holds', async () => {
    vi.mocked(api.fetchDowntimes).mockResolvedValue({ items: [noticed()], total: 1 });
    renderCard();
    expect(await screen.findByLabelText('start-downtime')).toHaveTextContent('Kontynuuj zgłoszenie przestoju');
  });

  it('offers every cause of the contract\'s catalogue and saves the choice at once', async () => {
    await begin();
    const cause = screen.getByLabelText('downtime-cause') as HTMLSelectElement;
    expect(cause.className).toContain('min-h-11');
    expect(Array.from(cause.options).slice(1).map((o) => o.value)).toEqual(CATALOG.downtime_causes.items.map((c) => c.key));
    expect(cause.options[1].textContent).toBe('Brak dostępu do Obiektu');
    expect(cause.options[8].textContent).toBe('Inna przyczyna po stronie Zamawiającego (opis w uwagach)');
    await act(async () => { fireEvent.change(cause, { target: { value: 'no_utilities' } }); });
    expect(lastChange()).toEqual({ cause_key: 'no_utilities' });
    await act(async () => { fireEvent.change(cause, { target: { value: '' } }); });
    expect(lastChange()).toEqual({ cause_key: null });
  });

  it('puts the rooms in or out with one tap each, and says that none means the whole object', async () => {
    serve(draft({ room_ids: ['r1'] }));
    await begin();
    expect(screen.getByText('Nic nie zaznaczone oznacza cały Obiekt.')).toBeInTheDocument();
    expect(screen.getByLabelText('downtime-room-r1')).toBeChecked();
    expect(screen.getByLabelText('downtime-room-r2')).not.toBeChecked();
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-room-r2')); });
    expect(lastChange()).toEqual({ room_ids: ['r1', 'r2'] });
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-room-r1')); });
    expect(lastChange()).toEqual({ room_ids: [] });
  });

  it('lists the photos that may be chosen with their room and time, each in a 44 px row, and says what to do when there are none', async () => {
    vi.mocked(api.updateDowntime).mockResolvedValue(draft({ photo_ids: ['f1'] }));
    await begin();
    expect(screen.getByText('Zamknięte drzwi · Salon · 2026-10-12 08:05')).toBeInTheDocument();
    expect(screen.getByText('Zdjęcie bez opisu')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-photo-f1')); });
    expect(lastChange()).toEqual({ photo_ids: ['f1'] });
    await waitFor(() => expect(screen.getByLabelText('downtime-photo-f1')).toBeChecked());
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-photo-f1')); });
    expect(lastChange()).toEqual({ photo_ids: [] });
    cleanup();
    serve(draft({ photo_options: [] }));
    await begin();
    expect(screen.getByText(/Obiekt nie ma jeszcze zdjęć/)).toBeInTheDocument();
  });

  it('saves the text fields when they are left and sends nothing per letter or for a blank over an empty field', async () => {
    await begin();
    const need = screen.getByLabelText('downtime-need');
    fireEvent.change(need, { target: { value: 'Udostępnić klucze' } });
    expect(api.updateDowntime).not.toHaveBeenCalled();
    await act(async () => { fireEvent.blur(need); });
    expect(lastChange()).toEqual({ need_text: 'Udostępnić klucze' });
    const channel = screen.getByLabelText('downtime-channel');
    fireEvent.change(channel, { target: { value: '  ' } });
    await act(async () => { fireEvent.blur(channel); });
    expect(api.updateDowntime).toHaveBeenCalledTimes(1);
    const note = screen.getByLabelText('downtime-cause-note');
    fireEvent.change(note, { target: { value: 'Klucze u administratora' } });
    await act(async () => { fireEvent.blur(note); });
    expect(lastChange()).toEqual({ cause_note: 'Klucze u administratora' });
    await act(async () => { fireEvent.change(screen.getByLabelText('downtime-need-by'), { target: { value: '2026-10-14' } }); });
    expect(lastChange()).toEqual({ need_by: '2026-10-14' });
    await act(async () => { fireEvent.change(screen.getByLabelText('downtime-noticed-on'), { target: { value: '2026-10-13' } }); });
    expect(lastChange()).toEqual({ noticed_on: '2026-10-13' });
  });

  it('says in words what is missing from the notice, keeps the issue button shut, and a ready notice is issued and the card moves on to the protocol', async () => {
    await begin();
    expect(screen.getByLabelText('gate-CAUSE_REQUIRED')).toHaveTextContent('Wybierz przyczynę przestoju.');
    expect(screen.getByLabelText('gate-PHOTOS_REQUIRED')).toHaveTextContent('Zaznacz co najmniej jedno zdjęcie przeszkody.');
    expect(screen.getByLabelText('issue-downtime-notice')).toBeDisabled();
    cleanup();
    serve(draft({ blockers: [] }));
    vi.mocked(api.issueDowntimeNotice).mockResolvedValue({} as never);
    vi.mocked(api.fetchDowntimes).mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValue({ items: [noticed()], total: 1 });
    await begin();
    expect(screen.getByText(/Wszystko gotowe/)).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-downtime-notice')); });
    expect(api.issueDowntimeNotice).toHaveBeenCalledWith('p1', 'e1');
    expect(await screen.findByLabelText('downtime-noticed-row')).toHaveTextContent('Zawiadomienie nr ZAWPRZ/2026/10/12/0830 — Brak dostępu do Obiektu');
    expect(screen.getByLabelText('downtime-note')).toHaveTextContent('Zawiadomienie zostało wystawione');
    expect(screen.queryByLabelText('downtime-cause')).toBeNull();  // the notice is no more to be changed
    expect(screen.getByLabelText('downtime-days')).toBeInTheDocument();
  });

  it('a refusal of the server at issue replaces the list of what is missing', async () => {
    serve(draft({ blockers: [] }));
    vi.mocked(api.issueDowntimeNotice).mockRejectedValue(new ApiError('English', 422, 'DOWNTIME_GATE_BLOCKED', {
      code: 'DOWNTIME_GATE_BLOCKED', details: { blockers: [{ code: 'NEED_REQUIRED', details: null }] } }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-downtime-notice')); });
    expect(await screen.findByLabelText('gate-NEED_REQUIRED')).toHaveTextContent('Napisz, czego potrzebujesz od Zamawiającego.');
    expect(screen.getByLabelText('issue-downtime-notice')).toBeDisabled();
  });

  it('shows the days with their weekday, saves the answer about other work and the note, and removes a day', async () => {
    const days = [day('2026-10-14', 2), day('2026-10-15', 3, { other_work: true, note: 'kuchnia' })];
    serve(noticed({ days, settlement: { ...SETTLEMENT, listed: 2, chargeable: 1 } }));
    vi.mocked(api.updateDowntime).mockResolvedValue(noticed({ days, settlement: { ...SETTLEMENT, listed: 2, chargeable: 1 } }));
    await begin();
    const first = screen.getByLabelText('downtime-day-2026-10-14');
    expect(first).toHaveTextContent('2026-10-14 · środa');
    expect(screen.getByLabelText('downtime-day-2026-10-15')).toHaveTextContent('2026-10-15 · czwartek');
    expect(screen.getByLabelText('downtime-other-work-2026-10-14')).not.toBeChecked();
    expect(screen.getByLabelText('downtime-other-work-2026-10-15')).toBeChecked();
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-other-work-2026-10-14')); });
    expect(lastChange()).toEqual({ days: { '2026-10-14': { other_work: true } } });
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-other-work-2026-10-15')); });
    expect(lastChange()).toEqual({ days: { '2026-10-15': { other_work: false } } });
    const note = screen.getByLabelText('downtime-day-note-2026-10-14');
    fireEvent.change(note, { target: { value: 'Brama zamknięta' } });
    await act(async () => { fireEvent.blur(note); });
    expect(lastChange()).toEqual({ days: { '2026-10-14': { note: 'Brama zamknięta' } } });
    const remove = screen.getByLabelText('downtime-day-remove-2026-10-14');
    expect(remove.className).toContain('min-h-11');
    await act(async () => { fireEvent.click(remove); });
    expect(lastChange()).toEqual({ days: { '2026-10-14': null } });
  });

  it('adds the next working day with one tap: after the last day, skipping the weekend, or after the notice when there is none', async () => {
    serve(noticed({ days: [day('2026-10-15', 3), day('2026-10-16', 4)], settlement: { ...SETTLEMENT, listed: 2 } }));
    await begin();
    const next = screen.getByLabelText('downtime-add-next-day');
    expect(next.className).toContain('min-h-11');
    await act(async () => { fireEvent.click(next); });
    expect(lastChange()).toEqual({ days: { '2026-10-19': {} } });  // Friday + one working day = Monday
    cleanup();
    serve(noticed({ days: [] }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-add-next-day')); });
    expect(lastChange()).toEqual({ days: { '2026-10-13': {} } });  // the notice was on Monday 12 October
    cleanup();
    serve(noticed({ days: [], noticed_on: null }));
    await begin();
    expect(screen.getByLabelText('downtime-add-next-day')).toBeDisabled();
  });

  it('adds a day of another date and shows the sentence of the server when the day is refused', async () => {
    serve(noticed());
    await begin();
    expect(screen.getByLabelText('downtime-add-picked-day')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('downtime-pick-day'), { target: { value: '2026-10-17' } });
    vi.mocked(api.updateDowntime).mockRejectedValueOnce(new ApiError('English', 422, 'DOWNTIME_INVALID', { code: 'DOWNTIME_INVALID', details: { key: 'days', reason: 'BAD_DAY' } }));
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-add-picked-day')); });
    expect(lastChange()).toEqual({ days: { '2026-10-17': {} } });
    expect(await screen.findByLabelText('downtime-error')).toHaveTextContent('dzień musi być dniem roboczym (poniedziałek–piątek) po dniu zawiadomienia');
    expect(screen.getByLabelText('downtime-pick-day')).toHaveValue('');
  });

  it('shows the sum for readiness as the server derived it: the days, the rate, the amount, the cap, the limit', async () => {
    const days = [day('2026-10-14', 2), day('2026-10-15', 3, { other_work: true }), day('2026-10-16', 4)];
    serve(noticed({ days, settlement: SETTLEMENT }));
    await begin();
    const panel = screen.getByLabelText('downtime-settlement');
    expect(panel).toHaveTextContent('Dni przestoju: 3, w tym płatnych: 2');
    expect(panel).toHaveTextContent('Stawka za dobę (z umowy): 150,00 zł');
    expect(panel).toHaveTextContent('Kwota za gotowość: 300,00 zł');
    expect(within(panel).queryByText(/ograniczona limitem/)).toBeNull();
    expect(within(panel).queryByText(/dłużej niż limit/)).toBeNull();
    cleanup();
    serve(noticed({ days, settlement: { ...SETTLEMENT, capped: true, payable: '1200.00', amount: '4000.00', limit_days: 2, limit_exceeded: true } }));
    await begin();
    const capped = screen.getByLabelText('downtime-settlement');
    expect(capped).toHaveTextContent('Kwota za gotowość: 1200,00 zł');
    expect(capped).toHaveTextContent('Kwota ograniczona limitem z umowy: 1200,00 zł');
    expect(capped).toHaveTextContent('Przestój trwa dłużej niż limit z umowy (2 dni roboczych).');
    cleanup();
    serve(noticed({ days, settlement: { ...SETTLEMENT, rate: null, amount: null, payable: null } }));
    await begin();
    expect(screen.getByLabelText('downtime-settlement')).toHaveTextContent('Umowa nie podaje stawki');
    expect(screen.getByLabelText('downtime-settlement')).not.toHaveTextContent('Kwota za gotowość');
    cleanup();
    serve(noticed({ days: [] }));
    await begin();
    expect(screen.queryByLabelText('downtime-settlement')).toBeNull();
    expect(screen.getByText('Brak dni — dodaj pierwszy dzień przestoju.')).toBeInTheDocument();
  });

  it('records the people present by a tap and by hand, the whole list each time', async () => {
    serve(noticed({ held_on: '2026-10-19', held_time: '09:00', attendees: [{ person_id: null, name: 'Jan Sąsiad', role: 'administrator' }] }));
    vi.mocked(api.updateDowntime).mockImplementation(async (_p, _id, changes) => noticed({
      held_on: '2026-10-19', held_time: '09:00', attendees: (changes.attendees ?? []).map((a) => ('person_id' in a ? { person_id: a.person_id, name: 'Anna Nowak', role: 'Właścicielka' } : { person_id: null, name: a.name, role: a.role ?? null })),
    }));
    await begin();
    expect(screen.queryByLabelText('downtime-person-rep2')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-person-rep1')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }] });
    expect(screen.getByLabelText('downtime-extra-add')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('downtime-extra'), { target: { value: 'Maria Kowalska, nadzór' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-extra-add')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }, { name: 'Maria Kowalska', role: 'nadzór' }] });
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-extra-remove-0')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Maria Kowalska', role: 'nadzór' }] });
  });

  it('saves the day of the protocol, the effect on the deadline, the refusal to sign with its hint, and the notes', async () => {
    serve(noticed({ held_on: '2026-10-19', held_time: '09:00' }));
    await begin();
    await act(async () => { fireEvent.change(screen.getByLabelText('downtime-held-on'), { target: { value: '2026-10-20' } }); });
    expect(lastChange()).toEqual({ held_on: '2026-10-20' });
    const held = screen.getByLabelText('downtime-held-time');
    fireEvent.change(held, { target: { value: '10:15' } });
    await act(async () => { fireEvent.blur(held); });
    expect(lastChange()).toEqual({ held_time: '10:15' });
    const deadline = screen.getByLabelText('downtime-deadline-note');
    fireEvent.change(deadline, { target: { value: 'Termin przesuwa się o 2 dni' } });
    await act(async () => { fireEvent.blur(deadline); });
    expect(lastChange()).toEqual({ deadline_note: 'Termin przesuwa się o 2 dni' });
    expect(screen.queryByText('Opisz okoliczności w uwagach poniżej.')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-refused')); });
    expect(lastChange()).toEqual({ signature_refused: true });
    vi.mocked(api.updateDowntime).mockResolvedValue(noticed({ signature_refused: true }));
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-refused')); });
    expect(await screen.findByText('Opisz okoliczności w uwagach poniżej.')).toBeInTheDocument();
    const notes = screen.getByLabelText('downtime-notes');
    fireEvent.change(notes, { target: { value: 'Odmówił podpisu' } });
    await act(async () => { fireEvent.blur(notes); });
    expect(lastChange()).toEqual({ notes: 'Odmówił podpisu' });
  });

  it('issues the protocol when the gate is open, closes the card and reports it; a gate that is shut keeps the button shut', async () => {
    await begin();
    cleanup();
    serve(noticed());
    await begin();
    expect(screen.getByLabelText('gate-DAYS_REQUIRED')).toHaveTextContent('Dodaj co najmniej jeden dzień przestoju.');
    expect(screen.getByLabelText('gate-NO_ATTENDEES')).toHaveTextContent('Zaznacz lub dopisz osoby obecne.');
    expect(screen.getByLabelText('issue-downtime-protocol')).toBeDisabled();
    cleanup();
    serve(noticed({ blockers: [] }));
    vi.mocked(api.issueDowntimeProtocol).mockResolvedValue({} as never);
    vi.mocked(api.fetchDowntimes).mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValue({ items: [draft({ status: 'CLOSED', sequence: 1 })], total: 1 });
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-downtime-protocol')); });
    expect(api.issueDowntimeProtocol).toHaveBeenCalledWith('p1', 'e1');
    await waitFor(() => expect(screen.queryByLabelText('downtime-form')).toBeNull());
    expect(screen.getByLabelText('downtime-note')).toHaveTextContent('Protokół został wystawiony');
    expect(screen.getByText('Ostatni przestój: nr 1 — zamknięty, protokół wystawiony')).toBeInTheDocument();
  });

  it('a refusal of the server at the protocol replaces the list of what is missing', async () => {
    serve(noticed({ blockers: [] }));
    vi.mocked(api.issueDowntimeProtocol).mockRejectedValue(new ApiError('English', 422, 'DOWNTIME_GATE_BLOCKED', {
      code: 'DOWNTIME_GATE_BLOCKED', details: { blockers: [{ code: 'DAY_AFTER_PROTOCOL', details: { days: ['2026-10-20'] } }] } }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-downtime-protocol')); });
    expect(await screen.findByLabelText('gate-DAY_AFTER_PROTOCOL')).toHaveTextContent('późniejszy niż data protokołu');
    expect(screen.getByLabelText('issue-downtime-protocol')).toBeDisabled();
  });

  it.each([
    ['NOTICE_FROZEN', 'zawiadomienie zostało już wystawione'],
    ['NOT_NOTICED_YET', 'dopiero po wystawieniu zawiadomienia'],
    ['UNKNOWN_PHOTO', 'to zdjęcie nie pasuje'],
    ['UNKNOWN_CAUSE', 'nieznana przyczyna'],
  ])('names the reason when the server refuses an entry: %s', async (reason, sentence) => {
    await begin();
    vi.mocked(api.updateDowntime).mockRejectedValueOnce(new ApiError('English', 422, 'DOWNTIME_INVALID', { code: 'DOWNTIME_INVALID', details: { key: 'x', reason } }));
    await act(async () => { fireEvent.click(screen.getByLabelText('downtime-room-r1')); });
    expect(await screen.findByLabelText('downtime-error')).toHaveTextContent(sentence);
  });

  it('sends the taps one at a time in order and the working version waits for them', async () => {
    await begin();
    let release: (value: Downtime) => void = () => undefined;
    vi.mocked(api.updateDowntime).mockImplementationOnce(() => new Promise<Downtime>((resolve) => { release = resolve; }));
    vi.mocked(documentsApi.previewDowntimeNoticePdf).mockResolvedValue({ sent: true, pages: 1, byte_size: 1 });
    fireEvent.click(screen.getByLabelText('downtime-room-r1'));
    fireEvent.click(screen.getByLabelText('downtime-room-r2'));
    await waitFor(() => expect(api.updateDowntime).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('downtime-saving')).toHaveTextContent('Zapisuję…');
    await act(async () => { fireEvent.click(screen.getByLabelText('preview-downtime-notice')); });
    expect(documentsApi.previewDowntimeNoticePdf).not.toHaveBeenCalled();
    await act(async () => { release(draft()); });
    await waitFor(() => expect(api.updateDowntime).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.updateDowntime).mock.calls.map((c) => Object.keys(c[2])[0])).toEqual(['room_ids', 'room_ids']);
    await waitFor(() => expect(documentsApi.previewDowntimeNoticePdf).toHaveBeenCalledWith('p1'));
    expect(await screen.findByLabelText('downtime-note')).toHaveTextContent('Wersja robocza zawiadomienia wysłana do czatu z botem');
  });

  it('abandons a draft only after a second tap, and ends a noticed episode without a protocol only after a second tap too', async () => {
    await begin();
    vi.mocked(api.abandonDowntime).mockResolvedValue(draft({ status: 'ARCHIVED' }));
    const abandon = screen.getByLabelText('abandon-downtime');
    expect(abandon).toHaveTextContent('Odwołaj zgłoszenie');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonDowntime).not.toHaveBeenCalled();
    expect(abandon).toHaveTextContent('Naciśnij ponownie, aby odwołać');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonDowntime).toHaveBeenCalledWith('p1', 'e1');
    await waitFor(() => expect(screen.queryByLabelText('downtime-form')).toBeNull());
    expect(screen.getByLabelText('downtime-note')).toHaveTextContent('Zgłoszenie przestoju odwołane.');
    cleanup();
    serve(noticed());
    await begin();
    const finish = screen.getByLabelText('abandon-downtime');
    expect(finish).toHaveTextContent('Przeszkoda usunięta — zakończ bez protokołu');
    await act(async () => { fireEvent.click(finish); });
    expect(finish).toHaveTextContent('Naciśnij ponownie, aby zakończyć bez protokołu');
    await act(async () => { fireEvent.click(screen.getByLabelText('close-downtime-form')); });
    await act(async () => { fireEvent.click(screen.getByLabelText('start-downtime')); });
    expect(screen.getByLabelText('abandon-downtime')).toHaveTextContent('Przeszkoda usunięta — zakończ bez protokołu');  // closing forgets the first tap
    await act(async () => { fireEvent.click(screen.getByLabelText('abandon-downtime')); });
    await act(async () => { fireEvent.click(screen.getByLabelText('abandon-downtime')); });
    await waitFor(() => expect(screen.queryByLabelText('downtime-form')).toBeNull());
    expect(screen.getByLabelText('downtime-note')).toHaveTextContent('Przestój zakończony bez protokołu');
  });

  it('sends both working versions from the closed card and offers a retry when the load fails', async () => {
    vi.mocked(documentsApi.previewDowntimeNoticePdf).mockResolvedValue({ sent: true, pages: 1, byte_size: 1 });
    vi.mocked(documentsApi.previewDowntimeProtocolPdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 1 });
    renderCard();
    const previewNotice = await screen.findByLabelText('preview-downtime-notice');
    await act(async () => { fireEvent.click(previewNotice); });
    expect(documentsApi.previewDowntimeNoticePdf).toHaveBeenCalledWith('p1');
    expect(await screen.findByLabelText('downtime-note')).toHaveTextContent('Wersja robocza zawiadomienia');
    await act(async () => { fireEvent.click(screen.getByLabelText('preview-downtime-protocol')); });
    expect(documentsApi.previewDowntimeProtocolPdf).toHaveBeenCalledWith('p1');
    expect(await screen.findByText(/Wersja robocza protokołu wysłana/)).toBeInTheDocument();
    cleanup();
    vi.mocked(api.fetchDowntimes).mockRejectedValueOnce(new Error('net')).mockResolvedValue({ items: [], total: 0 });
    renderCard();
    expect(await screen.findByText('Nie udało się wczytać zgłoszeń przestoju.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' })); });
    expect(await screen.findByLabelText('start-downtime')).toBeInTheDocument();
  });

  it('is localised in Russian and keeps every control touch-sized, in the notice and in the protocol', async () => {
    localStorage.setItem('locale', 'ru');
    const form = await begin();
    expect(screen.getByText('Простой по вине заказчика')).toBeInTheDocument();
    expect((screen.getByLabelText('downtime-cause') as HTMLSelectElement).options[1].textContent).toBe('Нет доступа на объект');
    expect(screen.getByLabelText('gate-CAUSE_REQUIRED')).toHaveTextContent(ru.downtime.gate.CAUSE_REQUIRED);
    for (const control of form.querySelectorAll('input:not([type=checkbox]), select, textarea, button')) {
      expect((control as HTMLElement).className).toMatch(/min-h-11/);
    }
    cleanup();
    serve(noticed({ days: [day('2026-10-14', 2)], settlement: { ...SETTLEMENT, listed: 1, chargeable: 1 } }));
    const protocol = await begin();
    expect(screen.getByLabelText('downtime-day-2026-10-14')).toHaveTextContent('среда');
    expect(screen.getByLabelText('downtime-settlement')).toHaveTextContent('Ставка за сутки (из договора): 150,00 zł');
    for (const control of protocol.querySelectorAll('input:not([type=checkbox]), select, textarea, button')) {
      expect((control as HTMLElement).className).toMatch(/min-h-11/);
    }
  });
});
