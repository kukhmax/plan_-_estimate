import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as catalogApi from '../api/contractCatalog';
import * as documentsApi from '../api/documents';
import * as api from '../api/handovers';
import { ApiError } from '../api/http';
import * as peopleApi from '../api/representatives';
import * as roomsApi from '../api/rooms';
import { I18nProvider } from '../hooks/useI18n';
import ru from '../locales/ru.json';
import type { ContractCatalog } from '../types/contractCatalog';
import type { Handover } from '../types/handover';
import type { ProjectRepresentative } from '../types/representative';
import { ProjectHandover } from './ProjectHandover';

vi.mock('../api/handovers', () => ({
  fetchHandovers: vi.fn(),
  openHandoverDraft: vi.fn(),
  updateHandover: vi.fn(),
  abandonHandoverDraft: vi.fn(),
  issueHandover: vi.fn(),
}));
vi.mock('../api/documents', () => ({ previewHandoverPdf: vi.fn() }));
vi.mock('../api/contractCatalog', () => ({ fetchContractCatalog: vi.fn() }));
vi.mock('../api/representatives', () => ({ fetchRepresentatives: vi.fn() }));
vi.mock('../api/rooms', () => ({ fetchRooms: vi.fn() }));

// the real catalogues of the server: the screen must draw every requirement they hold
const files = import.meta.glob('../../../backend/app/domain/contracts/catalog/*.json', { eager: true, import: 'default' }) as Record<string, unknown>;
const read = (name: string) => Object.entries(files).find(([path]) => path.endsWith(`/${name}`))![1];
const CATALOG = {
  requirements: read('premises_requirements.json'), instruments: read('assessment_instruments.json'), evaluation: read('evaluation_conditions.json'),
  defects: read('defect_classes.json'), tolerances: read('tolerances.json'), questionnaire: read('questionnaire.json'),
} as ContractCatalog;
const KEYS = CATALOG.requirements.items.map((r) => r.key);
const ROOM = 'room1';

function protocol(over: Partial<Handover> = {}): Handover {
  return {
    id: 'h1', project_id: 'p1', sequence: 1, status: 'DRAFT', held_on: '2026-10-20', held_time: null, attendees: [], rooms: {}, meters: null, notes: null,
    suggested: {}, blockers: [{ code: 'NO_ATTENDEES', details: null }], contract: { id: 'c1', version: 1, status: 'SIGNED' },
    required_values: { lighting_level: 300, temperature_range: { min: 5, max: 25 }, lighting_permanent: true }, created_at: 'x', updated_at: 'x', ...over,
  };
}
const person = (over: Partial<ProjectRepresentative> = {}): ProjectRepresentative => ({
  id: 'rep1', project_id: 'p1', side: 'CUSTOMER', name: 'Anna Nowak', role_title: 'Właścicielka', phone: null, email: null,
  may_accept_and_sign: true, is_archived: false, created_at: 'x', updated_at: 'x', ...over,
});

const renderCard = () => render(<I18nProvider><ProjectHandover projectId="p1" /></I18nProvider>);

async function begin(expandRoom = true) {
  renderCard();
  const start = await screen.findByLabelText('start-handover');
  await act(async () => { fireEvent.click(start); });
  const form = await screen.findByLabelText('handover-form');
  if (expandRoom) await act(async () => { fireEvent.click(screen.getByLabelText(`handover-room-${ROOM}`)); });
  return form;
}
const lastChange = () => {
  const calls = vi.mocked(api.updateHandover).mock.calls;
  return calls[calls.length - 1][2];
};

describe('ProjectHandover (Stage 16F.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchHandovers).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.openHandoverDraft).mockResolvedValue(protocol());
    vi.mocked(api.updateHandover).mockImplementation(async () => protocol());
    vi.mocked(catalogApi.fetchContractCatalog).mockResolvedValue(CATALOG);
    vi.mocked(peopleApi.fetchRepresentatives).mockResolvedValue({ items: [person(), person({ id: 'rep2', name: 'Piotr Archiwalny', is_archived: true })], total: 2 });
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [{ id: ROOM, name: 'Salon' }, { id: 'room2', name: 'Łazienka' }], total: 2 } as never);
  });
  afterEach(cleanup);

  it('offers to start with full-width touch-sized buttons and opens the draft on demand, with today as the day when there is none', async () => {
    vi.mocked(api.openHandoverDraft).mockResolvedValue(protocol({ held_on: null }));
    renderCard();
    const button = await screen.findByLabelText('start-handover');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('w-full');
    expect(button).toHaveTextContent('Rozpocznij protokół przekazania');
    expect(screen.getByLabelText('preview-handover').className).toContain('min-h-11');
    expect(api.openHandoverDraft).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(button); });
    await screen.findByLabelText('handover-form');
    expect(api.openHandoverDraft).toHaveBeenCalledWith('p1');
    await waitFor(() => expect(api.updateHandover).toHaveBeenCalledWith('p1', 'h1', { held_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) }));
  });

  it('keeps the day the server already has and mentions the latest issued protocol', async () => {
    vi.mocked(api.fetchHandovers).mockResolvedValue({ items: [protocol({ id: 'h0', sequence: 2, status: 'ISSUED' })], total: 1 });
    await begin(false);
    expect(api.updateHandover).not.toHaveBeenCalled();
    cleanup();
    renderCard();
    expect(await screen.findByText('Ostatni protokół: nr 2 — wystawiony')).toBeInTheDocument();
    expect(screen.getByLabelText('start-handover')).toHaveTextContent('Nowy protokół przekazania');
  });

  it('draws every requirement of the catalogue with four large state buttons and the number the contract asks for', async () => {
    await begin();
    for (const key of KEYS) expect(screen.getByLabelText(`handover-state-${ROOM}-${key}-YES`)).toBeInTheDocument();
    for (const key of KEYS) {
      for (const state of ['YES', 'NO', 'CONDITIONAL', 'NOT_APPLICABLE']) {
        expect(screen.getByLabelText(`handover-state-${ROOM}-${key}-${state}`).className).toContain('min-h-11');
      }
    }
    expect(screen.getByText('Wymagane: 300 lx')).toBeInTheDocument();
    expect(screen.getByText('Wymagane: od 5 do 25 °C')).toBeInTheDocument();
    expect(screen.getByText('Wymagane: Tak')).toBeInTheDocument();
    expect(screen.getAllByText('Wymagana wartość: brak w umowie').length).toBeGreaterThan(0);
    expect(screen.getAllByText('0 z 14 wymagań', { exact: false })).toHaveLength(2); // one per room
  });

  it('saves a tap at once with a small payload and shows what the server answers', async () => {
    vi.mocked(api.updateHandover).mockResolvedValue(protocol({ rooms: { [ROOM]: { requirements: { lighting_level: { state: 'NO' } } } } }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText(`handover-state-${ROOM}-lighting_level-NO`)); });
    expect(lastChange()).toEqual({ rooms: { [ROOM]: { requirements: { lighting_level: { state: 'NO' } } } } });
    await waitFor(() => expect(screen.getByLabelText(`handover-state-${ROOM}-lighting_level-NO`)).toHaveAttribute('aria-pressed', 'true'));
    expect(screen.getByLabelText(`handover-state-${ROOM}-lighting_level-YES`)).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('1 z 14 wymagań', { exact: false })).toBeInTheDocument();
    expect(screen.getByLabelText(`handover-note-${ROOM}-lighting_level`)).toBeInTheDocument(); // a note is offered for an unmet requirement
    expect(screen.queryByLabelText(`handover-note-${ROOM}-windows_glazed`)).toBeNull();
  });

  it('"everything met" sets every requirement and the decision in one request', async () => {
    await begin();
    const button = screen.getByLabelText(`handover-all-met-${ROOM}`);
    expect(button.className).toMatch(/w-full/);
    await act(async () => { fireEvent.click(button); });
    expect(api.updateHandover).toHaveBeenCalledTimes(1);
    const sent = lastChange().rooms![ROOM]!;
    expect(Object.keys(sent.requirements!)).toEqual(KEYS);
    expect(Object.values(sent.requirements!).every((e) => (e as { state: string }).state === 'YES')).toBe(true);
    expect(sent.decision).toBe('HANDED_OVER');
  });

  it('sends a measured value when the field is left, a range only when both limits are there, and clears with null', async () => {
    await begin();
    vi.mocked(api.updateHandover).mockResolvedValueOnce(protocol({ rooms: { [ROOM]: { requirements: { lighting_level: { value: 120.5 } } } } }));
    const level = screen.getByLabelText(`handover-value-${ROOM}-lighting_level`);
    expect(level).toHaveAttribute('inputmode', 'decimal');
    fireEvent.change(level, { target: { value: '120,5' } });
    expect(api.updateHandover).not.toHaveBeenCalled(); // nothing is sent per letter
    await act(async () => { fireEvent.blur(level); });
    expect(lastChange()).toEqual({ rooms: { [ROOM]: { requirements: { lighting_level: { value: 120.5 } } } } });
    await waitFor(() => expect(screen.getByLabelText(`handover-value-${ROOM}-lighting_level`)).toHaveValue('120,5'));
    const low = screen.getByLabelText(`handover-value-${ROOM}-temperature_range-min`);
    fireEvent.change(low, { target: { value: '8' } });
    await act(async () => { fireEvent.blur(low); });
    expect(api.updateHandover).toHaveBeenCalledTimes(1); // one limit alone is not a range
    vi.mocked(api.updateHandover).mockResolvedValue(protocol({ rooms: { [ROOM]: { requirements: { lighting_level: { value: 120.5 }, temperature_range: { value: { min: 8, max: 12 } } } } } }));
    const high = screen.getByLabelText(`handover-value-${ROOM}-temperature_range-max`);
    fireEvent.change(high, { target: { value: '12' } });
    await act(async () => { fireEvent.blur(high); });
    expect(lastChange()).toEqual({ rooms: { [ROOM]: { requirements: { temperature_range: { value: { min: 8, max: 12 } } } } } });
    await waitFor(() => expect(screen.getByLabelText(`handover-value-${ROOM}-temperature_range-min`)).toHaveValue('8'));
    fireEvent.change(screen.getByLabelText(`handover-value-${ROOM}-lighting_level`), { target: { value: '' } });
    await act(async () => { fireEvent.blur(screen.getByLabelText(`handover-value-${ROOM}-lighting_level`)); });
    expect(lastChange()).toEqual({ rooms: { [ROOM]: { requirements: { lighting_level: { value: null } } } } });
  });

  it('saves a note, the damages and the notes of the protocol when the field is left', async () => {
    vi.mocked(api.updateHandover).mockResolvedValue(protocol({ rooms: { [ROOM]: { requirements: { lighting_level: { state: 'NO' } } } } }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText(`handover-state-${ROOM}-lighting_level-NO`)); });
    const noteField = await screen.findByLabelText(`handover-note-${ROOM}-lighting_level`);
    fireEvent.change(noteField, { target: { value: 'lampa budowlana' } });
    await act(async () => { fireEvent.blur(noteField); });
    expect(lastChange()).toEqual({ rooms: { [ROOM]: { requirements: { lighting_level: { note: 'lampa budowlana' } } } } });
    const damages = screen.getByLabelText(`handover-damages-${ROOM}`);
    fireEvent.change(damages, { target: { value: 'Rysa nad oknem (zdjęcie 12)' } });
    await act(async () => { fireEvent.blur(damages); });
    expect(lastChange()).toEqual({ rooms: { [ROOM]: { damages: 'Rysa nad oknem (zdjęcie 12)' } } });
    fireEvent.change(screen.getByLabelText('handover-meters'), { target: { value: 'woda 123' } });
    await act(async () => { fireEvent.blur(screen.getByLabelText('handover-meters')); });
    expect(lastChange()).toEqual({ meters: 'woda 123' });
    fireEvent.change(screen.getByLabelText('handover-notes'), { target: { value: '  ' } });
    await act(async () => { fireEvent.blur(screen.getByLabelText('handover-notes')); });
    expect(api.updateHandover).toHaveBeenCalledTimes(4); // a blank over an empty field is not sent
  });

  it('lets "handed over" be chosen only when the findings allow it and always allows the stricter decisions', async () => {
    vi.mocked(api.openHandoverDraft).mockResolvedValue(protocol({ rooms: { [ROOM]: { requirements: { lighting_level: { state: 'NO' } } } }, suggested: { [ROOM]: null } }));
    await begin();
    expect(screen.getByLabelText(`handover-decision-${ROOM}-HANDED_OVER`)).toBeDisabled();
    expect(screen.getByText('Uzupełnij stan wymagań, aby zobaczyć sugestię.')).toBeInTheDocument();
    expect(screen.getByText('„Przekazane” — tylko gdy wszystkie wymagania są spełnione.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByLabelText(`handover-decision-${ROOM}-CONDITIONAL`)); });
    expect(lastChange()).toEqual({ rooms: { [ROOM]: { decision: 'CONDITIONAL' } } });
    cleanup();
    vi.mocked(api.openHandoverDraft).mockResolvedValue(protocol({ suggested: { [ROOM]: 'HANDED_OVER' }, rooms: { [ROOM]: { decision: 'HANDED_OVER' } } }));
    await begin();
    expect(screen.getByLabelText(`handover-decision-${ROOM}-HANDED_OVER`)).toBeEnabled();
    expect(screen.getByLabelText(`handover-decision-${ROOM}-HANDED_OVER`)).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Sugerowane: Przekazane')).toBeInTheDocument();
  });

  it('records who is present: persons of the register by a tap, and others by hand, each change sending the whole list', async () => {
    vi.mocked(api.openHandoverDraft).mockResolvedValue(protocol({ attendees: [{ person_id: null, name: 'Jan Sąsiad', role: 'administrator' }] }));
    vi.mocked(api.updateHandover).mockImplementation(async (_p, _id, changes) => protocol({
      attendees: (changes.attendees ?? []).map((a) => ('person_id' in a ? { person_id: a.person_id, name: 'Anna Nowak', role: 'Właścicielka' } : { person_id: null, name: a.name, role: a.role ?? null })),
    }));
    await begin(false);
    expect(screen.queryByLabelText('handover-person-rep2')).toBeNull(); // an archived person is not offered
    await act(async () => { fireEvent.click(screen.getByLabelText('handover-person-rep1')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }] });
    expect(screen.getByLabelText('handover-extra-add')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('handover-extra'), { target: { value: 'Maria Kowalska, nadzór, inspektor' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('handover-extra-add')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }, { name: 'Maria Kowalska', role: 'nadzór, inspektor' }] });
    expect(screen.getByLabelText('handover-extra')).toHaveValue('');
    await act(async () => { fireEvent.click(screen.getByLabelText('handover-extra-remove-0')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Maria Kowalska', role: 'nadzór, inspektor' }] });
  });

  it('says in words what is still missing, naming the rooms, and keeps the issue button shut', async () => {
    vi.mocked(api.openHandoverDraft).mockResolvedValue(protocol({ blockers: [
      { code: 'CONTRACT_REQUIRED', details: null },
      { code: 'REQUIREMENTS_MISSING', details: { rooms: [{ room_id: ROOM, keys: ['a', 'b', 'c'] }] } },
      { code: 'DECISION_MISSING', details: { room_ids: ['room2'] } },
      { code: 'DECISION_TOO_FAVOURABLE', details: { room_ids: [ROOM, 'room2'] } },
    ] }));
    await begin(false);
    const gate = screen.getByLabelText('handover-gate');
    expect(within(gate).getByLabelText('gate-CONTRACT_REQUIRED')).toHaveTextContent('Brak wystawionej lub podpisanej umowy');
    expect(within(gate).getByLabelText('gate-REQUIREMENTS_MISSING')).toHaveTextContent('Brakuje stanu wymagań: Salon (3).');
    expect(within(gate).getByLabelText('gate-DECISION_MISSING')).toHaveTextContent('Brak decyzji dla: Łazienka.');
    expect(within(gate).getByLabelText('gate-DECISION_TOO_FAVOURABLE')).toHaveTextContent('Salon, Łazienka');
    expect(screen.getByLabelText('issue-handover')).toBeDisabled();
  });

  it('issues a ready protocol, closes the form and reloads the list; a refusal of the server replaces the list of what is missing', async () => {
    vi.mocked(api.openHandoverDraft).mockResolvedValue(protocol({ blockers: [] }));
    vi.mocked(api.issueHandover).mockResolvedValue({} as never);
    vi.mocked(api.fetchHandovers).mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValue({ items: [protocol({ status: 'ISSUED' })], total: 1 });
    await begin(false);
    expect(screen.getByText(/Wszystko gotowe/)).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-handover')); });
    expect(api.issueHandover).toHaveBeenCalledWith('p1', 'h1');
    await waitFor(() => expect(screen.queryByLabelText('handover-form')).toBeNull());
    expect(screen.getByLabelText('handover-note')).toHaveTextContent('Protokół został wystawiony');
    expect(screen.getByText('Ostatni protokół: nr 1 — wystawiony')).toBeInTheDocument();
    cleanup();
    vi.mocked(api.issueHandover).mockRejectedValue(new ApiError('English', 422, 'HANDOVER_GATE_BLOCKED', {
      code: 'HANDOVER_GATE_BLOCKED', details: { blockers: [{ code: 'HELD_ON_REQUIRED', details: null }] } }));
    vi.mocked(api.fetchHandovers).mockResolvedValue({ items: [], total: 0 });
    await begin(false);
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-handover')); });
    expect(await screen.findByLabelText('gate-HELD_ON_REQUIRED')).toHaveTextContent('Wpisz datę przekazania.');
    expect(screen.getByLabelText('issue-handover')).toBeDisabled();
  });

  it.each([
    ['BAD_TIME', 'nieprawidłowa godzina'],
    ['OUT_OF_RANGE', 'wartość poza dozwolonym zakresem'],
    ['UNKNOWN_ROOM', 'zarchiwizowane'],
  ])('names the reason when the server refuses an entry: %s', async (reason, sentence) => {
    await begin();
    vi.mocked(api.updateHandover).mockRejectedValueOnce(new ApiError('English', 422, 'HANDOVER_INVALID', { code: 'HANDOVER_INVALID', details: { key: 'x', reason } }));
    await act(async () => { fireEvent.click(screen.getByLabelText(`handover-state-${ROOM}-lighting_level-YES`)); });
    expect(await screen.findByLabelText('handover-error')).toHaveTextContent(sentence);
  });

  it('sends the taps one at a time in the order they were made, and the working version waits for them', async () => {
    await begin();
    let release: (value: Handover) => void = () => undefined;
    vi.mocked(api.updateHandover).mockImplementationOnce(() => new Promise<Handover>((resolve) => { release = resolve; }));
    vi.mocked(documentsApi.previewHandoverPdf).mockResolvedValue({ sent: true, pages: 4, byte_size: 1 });
    fireEvent.click(screen.getByLabelText(`handover-state-${ROOM}-lighting_level-YES`));
    fireEvent.click(screen.getByLabelText(`handover-state-${ROOM}-windows_glazed-NO`));
    await waitFor(() => expect(api.updateHandover).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('handover-saving')).toHaveTextContent('Zapisuję…');
    await act(async () => { fireEvent.click(screen.getAllByLabelText('preview-handover')[0]); });
    expect(documentsApi.previewHandoverPdf).not.toHaveBeenCalled(); // the first save is still in the air
    await act(async () => { release(protocol()); });
    await waitFor(() => expect(api.updateHandover).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.updateHandover).mock.calls.map((call) => Object.keys(call[2].rooms![ROOM]!.requirements!)[0])).toEqual(['lighting_level', 'windows_glazed']);
    await waitFor(() => expect(documentsApi.previewHandoverPdf).toHaveBeenCalledWith('p1'));
    expect(await screen.findByLabelText('handover-note')).toHaveTextContent('Wersja robocza protokołu wysłana do czatu z botem');
  });

  it('sends the working version from the closed card as well, abandons a draft only after a second tap, and offers a retry when the load fails', async () => {
    vi.mocked(documentsApi.previewHandoverPdf).mockResolvedValue({ sent: true, pages: 4, byte_size: 1 });
    renderCard();
    const previewButton = await screen.findByLabelText('preview-handover');
    await act(async () => { fireEvent.click(previewButton); });
    expect(documentsApi.previewHandoverPdf).toHaveBeenCalledWith('p1');
    cleanup();
    vi.mocked(api.abandonHandoverDraft).mockResolvedValue(protocol({ status: 'ARCHIVED' }));
    await begin(false);
    const abandon = screen.getByLabelText('abandon-handover-draft');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonHandoverDraft).not.toHaveBeenCalled();
    expect(abandon).toHaveTextContent('Naciśnij ponownie');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonHandoverDraft).toHaveBeenCalledWith('p1', 'h1');
    await waitFor(() => expect(screen.queryByLabelText('handover-form')).toBeNull());
    expect(screen.getByLabelText('handover-note')).toHaveTextContent('Szkic odrzucony.');
    cleanup();
    vi.mocked(api.fetchHandovers).mockRejectedValueOnce(new Error('net')).mockResolvedValue({ items: [], total: 0 });
    renderCard();
    expect(await screen.findByText('Nie udało się wczytać protokołów.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' })); });
    expect(await screen.findByLabelText('start-handover')).toBeInTheDocument();
  });

  it('is localised in Russian and keeps every control touch-sized', async () => {
    localStorage.setItem('locale', 'ru');
    const form = await begin();
    expect(screen.getByText('Протокол передачи помещений')).toBeInTheDocument();
    expect(screen.getByLabelText(`handover-state-${ROOM}-lighting_level-YES`)).toHaveTextContent(ru.handover.state.YES);
    expect(screen.getByText(/Требуется: 300/)).toBeInTheDocument();
    expect(screen.getByLabelText(`handover-all-met-${ROOM}`)).toHaveTextContent('Всё выполнено');
    for (const control of form.querySelectorAll('input:not([type=checkbox]), select, textarea, button')) {
      expect((control as HTMLElement).className).toMatch(/min-h-11/);
    }
  });
});
