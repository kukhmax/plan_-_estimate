import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as catalogApi from '../api/contractCatalog';
import * as api from '../api/acceptances';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import * as peopleApi from '../api/representatives';
import { I18nProvider } from '../hooks/useI18n';
import ru from '../locales/ru.json';
import type { Acceptance, AcceptanceSurface } from '../types/acceptance';
import type { ContractCatalog } from '../types/contractCatalog';
import type { ProjectRepresentative } from '../types/representative';
import { ProjectAcceptance } from './ProjectAcceptance';

vi.mock('../api/acceptances', () => ({
  fetchAcceptances: vi.fn(),
  openAcceptanceDraft: vi.fn(),
  updateAcceptance: vi.fn(),
  abandonAcceptanceDraft: vi.fn(),
  issueAcceptance: vi.fn(),
}));
vi.mock('../api/documents', () => ({ previewAcceptancePdf: vi.fn() }));
vi.mock('../api/contractCatalog', () => ({ fetchContractCatalog: vi.fn() }));
vi.mock('../api/representatives', () => ({ fetchRepresentatives: vi.fn() }));

// the real catalogues of the server: the screen must offer every instrument they hold
const files = import.meta.glob('../../../backend/app/domain/contracts/catalog/*.json', { eager: true, import: 'default' }) as Record<string, unknown>;
const read = (name: string) => Object.entries(files).find(([path]) => path.endsWith(`/${name}`))![1];
const CATALOG = {
  requirements: read('premises_requirements.json'), instruments: read('assessment_instruments.json'), evaluation: read('evaluation_conditions.json'),
  defects: read('defect_classes.json'), tolerances: read('tolerances.json'), questionnaire: read('questionnaire.json'), work_kinds: read('concealed_work_kinds.json'),
} as ContractCatalog;

const surface = (over: Partial<AcceptanceSurface> = {}): AcceptanceSurface => ({
  id: 's1', name: 'Ściana A', surface_type: 'WALL', room_id: 'r1', room_name: 'Salon', quality_target: 'S2',
  works: [{ name: 'Gładź gipsowa', status: 'COMPLETED' }, { name: 'Malowanie', status: 'IN_PROGRESS' }], incomplete: 1, assessed: false, remarks: [],
  result: 'NOT_ACCEPTED', photo_options: [{ id: 'f1', caption: 'Smuga po gładzi', captured_at: '2026-10-20T08:05:00' }, { id: 'f2', caption: null, captured_at: null }], ...over,
});
function protocol(over: Partial<Acceptance> = {}): Acceptance {
  return {
    id: 'a1', project_id: 'p1', sequence: 1, status: 'DRAFT', held_on: '2026-10-20', held_time: '10:00', customer_absent: false, notified_on: null, renotified_on: null,
    attendees: [], room_ids: ['r1'], conditions_note: null, instrument_keys: [], batches: null, instructions_given: false, amount_due: null, amount_retained: null, notes: null,
    scope_kind: 'PARTIAL', result: 'NOT_ACCEPTED', rooms: [{ id: 'r1', name: 'Salon', surfaces: 1 }, { id: 'r2', name: 'Łazienka', surfaces: 2 }], surfaces: [surface()],
    conditions: [{ key: 'S2', lighting: 'DIFFUSE', requires_agreement: false, text_pl: 'Ocena wizualna przy oświetleniu rozproszonym.' }],
    blockers: [{ code: 'NO_ATTENDEES', details: null }], contract: { id: 'c1', version: 1, status: 'SIGNED' }, created_at: 'x', updated_at: 'x', ...over,
  };
}
const person = (over: Partial<ProjectRepresentative> = {}): ProjectRepresentative => ({
  id: 'rep1', project_id: 'p1', side: 'CUSTOMER', name: 'Anna Nowak', role_title: 'Właścicielka', phone: null, email: null,
  may_accept_and_sign: true, is_archived: false, created_at: 'x', updated_at: 'x', ...over,
});

const renderCard = () => render(<I18nProvider><ProjectAcceptance projectId="p1" /></I18nProvider>);
async function begin() {
  renderCard();
  const start = await screen.findByLabelText('start-acceptance');
  await act(async () => { fireEvent.click(start); });
  return screen.findByLabelText('acceptance-form');
}
const lastChange = () => {
  const calls = vi.mocked(api.updateAcceptance).mock.calls;
  return calls[calls.length - 1][2];
};

describe('ProjectAcceptance (Stage 16H.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchAcceptances).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol());
    vi.mocked(api.updateAcceptance).mockImplementation(async () => protocol());
    vi.mocked(catalogApi.fetchContractCatalog).mockResolvedValue(CATALOG);
    vi.mocked(peopleApi.fetchRepresentatives).mockResolvedValue({ items: [person(), person({ id: 'rep2', name: 'Piotr Archiwalny', is_archived: true })], total: 2 });
  });
  afterEach(cleanup);

  it('offers to start with full-width touch-sized buttons; the draft gets the day and hour of now and every room that has planned works', async () => {
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({ held_on: null, held_time: null, room_ids: [], scope_kind: null }));
    renderCard();
    const button = await screen.findByLabelText('start-acceptance');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('w-full');
    expect(button).toHaveTextContent('Rozpocznij odbiór prac');
    expect(screen.getByLabelText('preview-acceptance').className).toContain('min-h-11');
    expect(api.openAcceptanceDraft).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(button); });
    await screen.findByLabelText('acceptance-form');
    await waitFor(() => expect(api.updateAcceptance).toHaveBeenCalledWith('p1', 'a1', {
      held_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), held_time: expect.stringMatching(/^\d{2}:\d{2}$/), room_ids: ['r1', 'r2'] }));
  });

  it('keeps what the server has (no defaults written) and mentions the latest issued protocol', async () => {
    vi.mocked(api.fetchAcceptances).mockResolvedValue({ items: [protocol({ id: 'a0', sequence: 3, status: 'ISSUED' })], total: 1 });
    await begin();
    expect(api.updateAcceptance).not.toHaveBeenCalled();
    cleanup();
    renderCard();
    expect(await screen.findByText('Ostatni protokół: nr 3 — wystawiony')).toBeInTheDocument();
    expect(screen.getByLabelText('start-acceptance')).toHaveTextContent('Nowy odbiór prac');
  });

  it('puts the rooms in or out of scope with one tap each and shows the kind of acceptance the server derived', async () => {
    await begin();
    expect(screen.getByLabelText('acceptance-room-r1')).toBeChecked();
    expect(screen.getByLabelText('acceptance-room-r2')).not.toBeChecked();
    expect(screen.getByText('Łazienka · powierzchni: 2')).toBeInTheDocument();
    expect(screen.getByLabelText('acceptance-scope-kind')).toHaveTextContent('Odbiór częściowy');
    vi.mocked(api.updateAcceptance).mockResolvedValue(protocol({ room_ids: ['r1', 'r2'], scope_kind: 'FINAL' }));
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-room-r2')); });
    expect(lastChange()).toEqual({ room_ids: ['r1', 'r2'] });
    await waitFor(() => expect(screen.getByLabelText('acceptance-scope-kind')).toHaveTextContent('Odbiór końcowy'));
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-room-r1')); });
    expect(lastChange()).toEqual({ room_ids: ['r2'] });
  });

  it('shows each surface with the state of its planned works, says what is unfinished and never lets the result be typed', async () => {
    await begin();
    const card = screen.getByLabelText('acceptance-surface-s1');
    expect(card).toHaveTextContent('Salon — Ściana A');
    expect(card).toHaveTextContent('standard S2');
    expect(within(card).getByText('Gładź gipsowa').nextSibling).toHaveTextContent('wykonana');
    expect(within(card).getByText('Malowanie').nextSibling).toHaveTextContent('w trakcie');
    expect(within(card).getByText('Niewykonane prace: 1')).toBeInTheDocument();
    expect(screen.getByLabelText('acceptance-surface-result-s1')).toHaveTextContent('Nie odebrano');
    const result = screen.getByLabelText('acceptance-result');
    expect(result).toHaveTextContent('Nie odebrano');
    expect(within(result).queryAllByRole('button')).toHaveLength(0);  // the result is shown, not chosen
    expect(result).toHaveTextContent('nie wpisuje się go ręcznie');
  });

  it('marks a surface as checked with one tap and shows the derived result the server sends back', async () => {
    vi.mocked(api.updateAcceptance).mockResolvedValue(protocol({
      result: 'ACCEPTED', surfaces: [surface({ assessed: true, incomplete: 0, result: 'ACCEPTED', works: [{ name: 'Gładź gipsowa', status: 'COMPLETED' }] })] }));
    await begin();
    const box = screen.getByLabelText('acceptance-assessed-s1');
    expect(box.className).toContain('h-5');
    await act(async () => { fireEvent.click(box); });
    expect(lastChange()).toEqual({ surfaces: { s1: { assessed: true } } });
    await waitFor(() => expect(screen.getByLabelText('acceptance-assessed-s1')).toBeChecked());
    expect(screen.getByLabelText('acceptance-surface-result-s1')).toHaveTextContent('Odebrano');
    expect(screen.getByLabelText('acceptance-result').textContent).toContain('Odebrano');
    vi.mocked(api.updateAcceptance).mockResolvedValue(protocol({ surfaces: [surface({ assessed: false })] }));
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-assessed-s1')); });
    expect(lastChange()).toEqual({ surfaces: { s1: { assessed: false } } });
  });

  it('writes a remark: nothing is saved until place, description and class (and a deadline for a removable one) are there; the surface is marked checked with it', async () => {
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-add-s1')); });
    const save = screen.getByLabelText('acceptance-remark-save');
    expect(save).toBeDisabled();
    expect(save.className).toContain('min-h-11');
    fireEvent.change(screen.getByLabelText('acceptance-remark-place'), { target: { value: ' Narożnik przy oknie ' } });
    fireEvent.change(screen.getByLabelText('acceptance-remark-description'), { target: { value: 'Smuga w świetle bocznym' } });
    expect(save).toBeDisabled();
    expect(screen.queryByLabelText('acceptance-remark-deadline')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-class-REMOVABLE')); });
    expect(screen.getByLabelText('acceptance-remark-class-REMOVABLE')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('acceptance-remark-class-REMOVABLE')).toHaveTextContent('Wada usuwalna');
    expect(screen.getByLabelText('acceptance-remark-class-SIGNIFICANT')).toHaveTextContent('Wada istotna');
    expect(save).toBeDisabled();  // a removable remark needs its deadline
    fireEvent.change(screen.getByLabelText('acceptance-remark-deadline'), { target: { value: '2026-10-25' } });
    expect(save).not.toBeDisabled();
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-photo-f1')); });
    await act(async () => { fireEvent.click(save); });
    const sent = lastChange().surfaces!.s1!;
    const ids = Object.keys(sent.remarks!);
    expect(ids).toHaveLength(1);
    expect(ids[0]).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(sent).toEqual({ assessed: true, remarks: { [ids[0]]: {
      place: 'Narożnik przy oknie', description: 'Smuga w świetle bocznym', classification: 'REMOVABLE', deadline: '2026-10-25', photo_ids: ['f1'] } } });
    expect(screen.queryByLabelText('acceptance-remark-form')).toBeNull();
  });

  it('a significant remark needs no deadline and sends none; the form can be cancelled', async () => {
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-add-s1')); });
    fireEvent.change(screen.getByLabelText('acceptance-remark-place'), { target: { value: 'Sufit' } });
    fireEvent.change(screen.getByLabelText('acceptance-remark-description'), { target: { value: 'Pęknięcie na całej długości' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-class-SIGNIFICANT')); });
    expect(screen.queryByLabelText('acceptance-remark-deadline')).toBeNull();
    expect(screen.getByLabelText('acceptance-remark-save')).not.toBeDisabled();
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-save')); });
    expect(Object.values(lastChange().surfaces!.s1!.remarks!)[0]).toEqual({
      place: 'Sufit', description: 'Pęknięcie na całej długości', classification: 'SIGNIFICANT', deadline: null, photo_ids: [] });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-add-s1')); });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-cancel')); });
    expect(screen.queryByLabelText('acceptance-remark-form')).toBeNull();
  });

  it('lists the remarks of a surface with their class and deadline, changes one under its own key and removes one with null', async () => {
    const remark = { id: 'm1', place: 'Narożnik', description: 'Smuga', classification: 'REMOVABLE' as const, deadline: '2026-10-25', photo_ids: ['f1'] };
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({ surfaces: [surface({ assessed: true, remarks: [remark], result: 'NOT_ACCEPTED' })] }));
    await begin();
    const row = screen.getByLabelText('acceptance-remark-m1');
    expect(row).toHaveTextContent('Narożnik — Smuga');
    expect(row).toHaveTextContent('Wada usuwalna');
    expect(row).toHaveTextContent('do 2026-10-25');
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-edit-m1')); });
    expect(screen.getByLabelText('acceptance-remark-place')).toHaveValue('Narożnik');
    expect(screen.getByLabelText('acceptance-remark-deadline')).toHaveValue('2026-10-25');
    expect(screen.getByLabelText('acceptance-remark-photo-f1')).toBeChecked();
    vi.mocked(api.updateAcceptance).mockResolvedValue(protocol({ surfaces: [surface({ assessed: true, remarks: [remark] })] }));
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-class-SIGNIFICANT')); });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-save')); });
    expect(lastChange()).toEqual({ surfaces: { s1: { assessed: true, remarks: { m1: {
      place: 'Narożnik', description: 'Smuga', classification: 'SIGNIFICANT', deadline: null, photo_ids: ['f1'] } } } } });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-remove-m1')); });
    expect(lastChange()).toEqual({ surfaces: { s1: { remarks: { m1: null } } } });
  });

  it('offers only the defect photos of the surface to a remark and says what to do when there are none', async () => {
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({ surfaces: [surface({ photo_options: [] })] }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-add-s1')); });
    expect(screen.getByText(/nie ma zdjęć w kategorii „Usterka”/)).toBeInTheDocument();
    cleanup();
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol());
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-add-s1')); });
    expect(screen.getByText('Smuga po gładzi · 2026-10-20 08:05')).toBeInTheDocument();
    expect(screen.getByText('Zdjęcie bez opisu')).toBeInTheDocument();
  });

  it('records the people present by a tap and by hand, the whole list each time', async () => {
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({ attendees: [{ person_id: null, name: 'Jan Sąsiad', role: 'administrator' }] }));
    vi.mocked(api.updateAcceptance).mockImplementation(async (_p, _id, changes) => protocol({
      attendees: (changes.attendees ?? []).map((a) => ('person_id' in a ? { person_id: a.person_id, name: 'Anna Nowak', role: 'Właścicielka' } : { person_id: null, name: a.name, role: a.role ?? null })),
    }));
    await begin();
    expect(screen.queryByLabelText('acceptance-person-rep2')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-person-rep1')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }] });
    expect(screen.getByLabelText('acceptance-extra-add')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('acceptance-extra'), { target: { value: 'Maria Kowalska, nadzór' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-extra-add')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }, { name: 'Maria Kowalska', role: 'nadzór' }] });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-extra-remove-0')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Maria Kowalska', role: 'nadzór' }] });
  });

  it('turns into a one-sided protocol when the customer did not come: both notification days instead of the people', async () => {
    await begin();
    expect(screen.queryByLabelText('acceptance-notified-on')).toBeNull();
    vi.mocked(api.updateAcceptance).mockResolvedValue(protocol({ customer_absent: true }));
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-absent')); });
    expect(lastChange()).toEqual({ customer_absent: true });
    const first = await screen.findByLabelText('acceptance-notified-on');
    const second = screen.getByLabelText('acceptance-renotified-on');
    expect(first).toHaveAttribute('type', 'date');
    expect(second).toHaveAttribute('type', 'date');
    expect(screen.queryByLabelText('acceptance-person-rep1')).toBeNull();
    await act(async () => { fireEvent.change(first, { target: { value: '2026-10-14' } }); });
    expect(lastChange()).toEqual({ notified_on: '2026-10-14' });
    await act(async () => { fireEvent.change(second, { target: { value: '2026-10-17' } }); });
    expect(lastChange()).toEqual({ renotified_on: '2026-10-17' });
    vi.mocked(api.updateAcceptance).mockResolvedValue(protocol({ customer_absent: false }));
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-absent')); });
    expect(lastChange()).toEqual({ customer_absent: false });
  });

  it('shows the conditions of the assessment of the standards in scope from the server, asks for the agreed ones when the standard needs them, and offers every instrument of the catalogue', async () => {
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({
      conditions: [
        { key: 'S2', lighting: 'DIFFUSE', requires_agreement: false, text_pl: 'Ocena wizualna przy oświetleniu rozproszonym.' },
        { key: 'S4', lighting: 'AGREED_BEFORE_WORK', requires_agreement: true, text_pl: 'Warunki uzgadniane przed pracami.' }] }));
    await begin();
    const conditions = screen.getByLabelText('acceptance-conditions');
    expect(conditions).toHaveTextContent('S2 — Standard malarski');
    expect(conditions).toHaveTextContent('Ocena wizualna przy oświetleniu rozproszonym.');
    expect(conditions).toHaveTextContent('S4 — Standard premium uzgadniany indywidualnie');
    expect(within(conditions).getAllByText(/wymaga warunków uzgodnionych przed pracami/)).toHaveLength(1);  // only for the standard that needs it
    const note = screen.getByLabelText('acceptance-conditions-note');
    fireEvent.change(note, { target: { value: 'Światło boczne LED, obserwacja z 1,5 m' } });
    expect(api.updateAcceptance).not.toHaveBeenCalled();
    await act(async () => { fireEvent.blur(note); });
    expect(lastChange()).toEqual({ conditions_note: 'Światło boczne LED, obserwacja z 1,5 m' });
    for (const instrument of CATALOG.instruments.items) expect(screen.getByLabelText(`acceptance-instrument-${instrument.key}`)).toBeInTheDocument();
    expect(screen.getByLabelText('acceptance-instrument-raking_light').closest('label')).toHaveTextContent('Lampa światła smugowego');
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-instrument-raking_light')); });
    expect(lastChange()).toEqual({ instrument_keys: ['raking_light'] });
    cleanup();
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({ conditions: [] }));
    await begin();
    expect(screen.queryByLabelText('acceptance-conditions')).toBeNull();
  });

  it('saves the settlement when a field is left, with mobile decimal input, and nothing per letter or for a blank over an empty field', async () => {
    await begin();
    const due = screen.getByLabelText('acceptance-amount-due');
    expect(due).toHaveAttribute('inputmode', 'decimal');
    expect(screen.getByLabelText('acceptance-amount-retained')).toHaveAttribute('inputmode', 'decimal');
    fireEvent.change(due, { target: { value: '2000,50' } });
    expect(api.updateAcceptance).not.toHaveBeenCalled();
    await act(async () => { fireEvent.blur(due); });
    expect(lastChange()).toEqual({ amount_due: '2000,50' });
    const retained = screen.getByLabelText('acceptance-amount-retained');
    fireEvent.change(retained, { target: { value: '  ' } });
    await act(async () => { fireEvent.blur(retained); });
    expect(api.updateAcceptance).toHaveBeenCalledTimes(1);
    const batches = screen.getByLabelText('acceptance-batches');
    fireEvent.change(batches, { target: { value: 'Gładź L77/3' } });
    await act(async () => { fireEvent.blur(batches); });
    expect(lastChange()).toEqual({ batches: 'Gładź L77/3' });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-instructions')); });
    expect(lastChange()).toEqual({ instructions_given: true });
    const notes = screen.getByLabelText('acceptance-notes');
    fireEvent.change(notes, { target: { value: 'Klucze oddane' } });
    await act(async () => { fireEvent.blur(notes); });
    expect(lastChange()).toEqual({ notes: 'Klucze oddane' });
    const day = screen.getByLabelText('acceptance-held-on');
    await act(async () => { fireEvent.change(day, { target: { value: '2026-10-21' } }); });
    expect(lastChange()).toEqual({ held_on: '2026-10-21' });
  });

  it('says in words what is still missing and keeps the issue button shut; a ready protocol is issued and the form closes', async () => {
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({ blockers: [
      { code: 'SURFACE_NOT_ASSESSED', details: null }, { code: 'RENOTIFIED_ON_REQUIRED', details: null }, { code: 'CONTRACT_REQUIRED', details: null }] }));
    await begin();
    expect(screen.getByLabelText('gate-SURFACE_NOT_ASSESSED')).toHaveTextContent('Oznacz jako sprawdzone wszystkie odbierane powierzchnie.');
    expect(screen.getByLabelText('gate-RENOTIFIED_ON_REQUIRED')).toHaveTextContent('ponownego zawiadomienia');
    expect(screen.getByLabelText('gate-CONTRACT_REQUIRED')).toHaveTextContent('Brak wystawionej lub podpisanej umowy');
    expect(screen.getByLabelText('issue-acceptance')).toBeDisabled();
    cleanup();
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({ blockers: [] }));
    vi.mocked(api.issueAcceptance).mockResolvedValue({} as never);
    vi.mocked(api.fetchAcceptances).mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValue({ items: [protocol({ status: 'ISSUED' })], total: 1 });
    await begin();
    expect(screen.getByText(/Wszystko gotowe/)).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-acceptance')); });
    expect(api.issueAcceptance).toHaveBeenCalledWith('p1', 'a1');
    await waitFor(() => expect(screen.queryByLabelText('acceptance-form')).toBeNull());
    expect(screen.getByLabelText('acceptance-note')).toHaveTextContent('Protokół został wystawiony');
    expect(screen.getByText('Ostatni protokół: nr 1 — wystawiony')).toBeInTheDocument();
  });

  it('a refusal of the server at issue replaces the list of what is missing', async () => {
    vi.mocked(api.openAcceptanceDraft).mockResolvedValue(protocol({ blockers: [] }));
    vi.mocked(api.issueAcceptance).mockRejectedValue(new ApiError('English', 422, 'ACCEPTANCE_GATE_BLOCKED', {
      code: 'ACCEPTANCE_GATE_BLOCKED', details: { blockers: [{ code: 'CONDITIONS_NOTE_REQUIRED', details: null }] } }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-acceptance')); });
    expect(await screen.findByLabelText('gate-CONDITIONS_NOTE_REQUIRED')).toHaveTextContent('Wpisz uzgodnione warunki oceny');
    expect(screen.getByLabelText('issue-acceptance')).toBeDisabled();
  });

  it.each([
    ['BAD_REMARK', 'uwaga wymaga miejsca'],
    ['BAD_MONEY', 'nieprawidłowa kwota'],
    ['UNKNOWN_PHOTO', 'zdjęcie nie jest zdjęciem usterki'],
    ['UNKNOWN_ROOM', 'pomieszczenie nie należy'],
  ])('names the reason when the server refuses an entry: %s', async (reason, sentence) => {
    await begin();
    vi.mocked(api.updateAcceptance).mockRejectedValueOnce(new ApiError('English', 422, 'ACCEPTANCE_INVALID', { code: 'ACCEPTANCE_INVALID', details: { key: 'x', reason } }));
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-assessed-s1')); });
    expect(await screen.findByLabelText('acceptance-error')).toHaveTextContent(sentence);
  });

  it('sends the taps one at a time in order, the working version waits for them, and a draft is abandoned only after a second tap', async () => {
    await begin();
    let release: (value: Acceptance) => void = () => undefined;
    vi.mocked(api.updateAcceptance).mockImplementationOnce(() => new Promise<Acceptance>((resolve) => { release = resolve; }));
    vi.mocked(documentsApi.previewAcceptancePdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 1 });
    fireEvent.click(screen.getByLabelText('acceptance-assessed-s1'));
    fireEvent.click(screen.getByLabelText('acceptance-instructions'));
    await waitFor(() => expect(api.updateAcceptance).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('acceptance-saving')).toHaveTextContent('Zapisuję…');
    await act(async () => { fireEvent.click(screen.getAllByLabelText('preview-acceptance')[0]); });
    expect(documentsApi.previewAcceptancePdf).not.toHaveBeenCalled();
    await act(async () => { release(protocol()); });
    await waitFor(() => expect(api.updateAcceptance).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.updateAcceptance).mock.calls.map((c) => Object.keys(c[2])[0])).toEqual(['surfaces', 'instructions_given']);
    await waitFor(() => expect(documentsApi.previewAcceptancePdf).toHaveBeenCalledWith('p1'));
    expect(await screen.findByLabelText('acceptance-note')).toHaveTextContent('Wersja robocza protokołu wysłana do czatu z botem');
    vi.mocked(api.abandonAcceptanceDraft).mockResolvedValue(protocol({ status: 'ARCHIVED' }));
    const abandon = screen.getByLabelText('abandon-acceptance-draft');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonAcceptanceDraft).not.toHaveBeenCalled();
    expect(abandon).toHaveTextContent('Naciśnij ponownie');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonAcceptanceDraft).toHaveBeenCalledWith('p1', 'a1');
    await waitFor(() => expect(screen.queryByLabelText('acceptance-form')).toBeNull());
    expect(screen.getByLabelText('acceptance-note')).toHaveTextContent('Szkic odrzucony.');
  });

  it('sends the working version from the closed card and offers a retry when the load fails', async () => {
    vi.mocked(documentsApi.previewAcceptancePdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 1 });
    renderCard();
    const previewButton = await screen.findByLabelText('preview-acceptance');
    await act(async () => { fireEvent.click(previewButton); });
    expect(documentsApi.previewAcceptancePdf).toHaveBeenCalledWith('p1');
    cleanup();
    vi.mocked(api.fetchAcceptances).mockRejectedValueOnce(new Error('net')).mockResolvedValue({ items: [], total: 0 });
    renderCard();
    expect(await screen.findByText('Nie udało się wczytać protokołów odbioru.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' })); });
    expect(await screen.findByLabelText('start-acceptance')).toBeInTheDocument();
  });

  it('is localised in Russian and keeps every control touch-sized, also in the remark form', async () => {
    localStorage.setItem('locale', 'ru');
    const form = await begin();
    expect(screen.getByText('Протокол приёмки работ')).toBeInTheDocument();
    expect(screen.getByLabelText('acceptance-surface-result-s1')).toHaveTextContent(ru.acceptance.surface_result.NOT_ACCEPTED);
    expect(screen.getByLabelText('acceptance-scope-kind')).toHaveTextContent('Частичная приёмка');
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-add-s1')); });
    await act(async () => { fireEvent.click(screen.getByLabelText('acceptance-remark-class-REMOVABLE')); });
    expect(screen.getByLabelText('acceptance-remark-class-REMOVABLE')).toHaveTextContent('Устранимое замечание');
    for (const control of form.querySelectorAll('input:not([type=checkbox]), select, textarea, button')) {
      expect((control as HTMLElement).className).toMatch(/min-h-11/);
    }
  });
});
