import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as catalogApi from '../api/contractCatalog';
import * as api from '../api/concealedWorks';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import * as peopleApi from '../api/representatives';
import * as roomsApi from '../api/rooms';
import * as surfacesApi from '../api/surfaces';
import { I18nProvider } from '../hooks/useI18n';
import ru from '../locales/ru.json';
import type { Concealed } from '../types/concealed';
import type { ContractCatalog } from '../types/contractCatalog';
import type { ProjectRepresentative } from '../types/representative';
import { ProjectConcealedWorks } from './ProjectConcealedWorks';

vi.mock('../api/concealedWorks', () => ({
  fetchConcealedWorks: vi.fn(),
  openConcealedDraft: vi.fn(),
  updateConcealed: vi.fn(),
  abandonConcealedDraft: vi.fn(),
  issueConcealed: vi.fn(),
}));
vi.mock('../api/documents', () => ({ previewConcealedPdf: vi.fn() }));
vi.mock('../api/contractCatalog', () => ({ fetchContractCatalog: vi.fn() }));
vi.mock('../api/representatives', () => ({ fetchRepresentatives: vi.fn() }));
vi.mock('../api/rooms', () => ({ fetchRooms: vi.fn() }));
vi.mock('../api/surfaces', () => ({ fetchSurfaces: vi.fn() }));

// the real catalogues of the server: the screen must offer every kind of work they hold
const files = import.meta.glob('../../../backend/app/domain/contracts/catalog/*.json', { eager: true, import: 'default' }) as Record<string, unknown>;
const read = (name: string) => Object.entries(files).find(([path]) => path.endsWith(`/${name}`))![1];
const CATALOG = {
  requirements: read('premises_requirements.json'), instruments: read('assessment_instruments.json'), evaluation: read('evaluation_conditions.json'),
  defects: read('defect_classes.json'), tolerances: read('tolerances.json'), questionnaire: read('questionnaire.json'), work_kinds: read('concealed_work_kinds.json'),
} as ContractCatalog;
const SURFACE = 's1';

function protocol(over: Partial<Concealed> = {}): Concealed {
  return {
    id: 'z1', project_id: 'p1', sequence: 1, status: 'DRAFT', held_on: '2026-10-20', held_time: '08:15', customer_absent: false, notified_on: null, attendees: [],
    surface: null, work_kind: null, work_note: null, material: null, batch: null, photo_ids: [], result: null, remarks: null, cover_consent: null,
    photo_options: [], blockers: [{ code: 'SURFACE_REQUIRED', details: null }], contract: { id: 'c1', version: 1, status: 'SIGNED' }, created_at: 'x', updated_at: 'x', ...over,
  };
}
const withSurface = (over: Partial<Concealed> = {}) => protocol({
  surface: { id: SURFACE, name: 'Ściana A', room_id: 'r1', room_name: 'Salon' },
  photo_options: [{ id: 'f1', caption: 'Narożnik przy oknie', captured_at: '2026-10-20T08:05:00' }, { id: 'f2', caption: null, captured_at: null }], ...over,
});
const person = (over: Partial<ProjectRepresentative> = {}): ProjectRepresentative => ({
  id: 'rep1', project_id: 'p1', side: 'CUSTOMER', name: 'Anna Nowak', role_title: 'Właścicielka', phone: null, email: null,
  may_accept_and_sign: true, is_archived: false, created_at: 'x', updated_at: 'x', ...over,
});

const renderCard = () => render(<I18nProvider><ProjectConcealedWorks projectId="p1" /></I18nProvider>);
async function begin() {
  renderCard();
  const start = await screen.findByLabelText('start-concealed');
  await act(async () => { fireEvent.click(start); });
  return screen.findByLabelText('concealed-form');
}
const lastChange = () => {
  const calls = vi.mocked(api.updateConcealed).mock.calls;
  return calls[calls.length - 1][2];
};

describe('ProjectConcealedWorks (Stage 16G.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchConcealedWorks).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.openConcealedDraft).mockResolvedValue(withSurface());
    vi.mocked(api.updateConcealed).mockImplementation(async () => withSurface());
    vi.mocked(catalogApi.fetchContractCatalog).mockResolvedValue(CATALOG);
    vi.mocked(peopleApi.fetchRepresentatives).mockResolvedValue({ items: [person(), person({ id: 'rep2', name: 'Piotr Archiwalny', is_archived: true })], total: 2 });
    vi.mocked(roomsApi.fetchRooms).mockResolvedValue({ items: [{ id: 'r1', name: 'Salon' }, { id: 'r2', name: 'Łazienka' }], total: 2 } as never);
    vi.mocked(surfacesApi.fetchSurfaces).mockImplementation(async (_p, roomId) => ({
      items: roomId === 'r1' ? [{ id: SURFACE, room_id: 'r1', name: 'Wall 1', surface_type: 'WALL' }, { id: 's2', room_id: 'r1', name: 'Sufit', surface_type: 'CEILING' }] : [{ id: 's3', room_id: 'r2', name: 'Wall 1', surface_type: 'WALL' }],
      total: 2,
    }) as never);
  });
  afterEach(cleanup);

  it('offers to start with full-width touch-sized buttons and opens the draft, writing the day and the hour of now when there are none', async () => {
    vi.mocked(api.openConcealedDraft).mockResolvedValue(protocol({ held_on: null, held_time: null }));
    renderCard();
    const button = await screen.findByLabelText('start-concealed');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('w-full');
    expect(button).toHaveTextContent('Rozpocznij protokół odbioru');
    expect(screen.getByLabelText('preview-concealed').className).toContain('min-h-11');
    expect(api.openConcealedDraft).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(button); });
    await screen.findByLabelText('concealed-form');
    await waitFor(() => expect(api.updateConcealed).toHaveBeenCalledWith('p1', 'z1', {
      held_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), held_time: expect.stringMatching(/^\d{2}:\d{2}$/) }));
  });

  it('keeps the day the server has and mentions the latest issued protocol', async () => {
    vi.mocked(api.fetchConcealedWorks).mockResolvedValue({ items: [protocol({ id: 'z0', sequence: 3, status: 'ISSUED' })], total: 1 });
    await begin();
    expect(api.updateConcealed).not.toHaveBeenCalled();
    cleanup();
    renderCard();
    expect(await screen.findByText('Ostatni protokół: nr 3 — wystawiony')).toBeInTheDocument();
    expect(screen.getByLabelText('start-concealed')).toHaveTextContent('Nowy protokół odbioru');
  });

  it('offers the surfaces grouped by room and every kind of work of the catalogue, and saves the choice at once', async () => {
    const form = await begin();
    const surface = screen.getByLabelText('concealed-surface') as HTMLSelectElement;
    expect(surface.className).toContain('min-h-11');
    expect(Array.from(form.querySelectorAll('optgroup')).map((g) => g.label)).toEqual(['Salon', 'Łazienka']);
    expect(Array.from(surface.options).map((o) => o.textContent)).toEqual(['— wybierz powierzchnię —', 'Ściana 1', 'Sufit', 'Ściana 1']);
    const kind = screen.getByLabelText('concealed-work-kind') as HTMLSelectElement;
    expect(Array.from(kind.options).slice(1).map((o) => o.value)).toEqual(CATALOG.work_kinds.items.map((k) => k.key));
    expect(kind.options[1].textContent).toBe('Gruntowanie podłoża');
    await act(async () => { fireEvent.change(surface, { target: { value: SURFACE } }); });
    expect(lastChange()).toEqual({ surface_id: SURFACE });
    await act(async () => { fireEvent.change(kind, { target: { value: 'priming' } }); });
    expect(lastChange()).toEqual({ work_kind: 'priming' });
    await act(async () => { fireEvent.change(surface, { target: { value: '' } }); });
    expect(lastChange()).toEqual({ surface_id: null });
  });

  it('lists the evidence photos of the surface to tick, each with at least a 44 px row, and says what to do when there are none', async () => {
    vi.mocked(api.updateConcealed).mockResolvedValue(withSurface({ photo_ids: ['f1'] }));
    await begin();
    const first = screen.getByLabelText('concealed-photo-f1');
    expect(screen.getByText('Narożnik przy oknie · 2026-10-20 08:05')).toBeInTheDocument();
    expect(screen.getByText('Zdjęcie bez opisu')).toBeInTheDocument();
    await act(async () => { fireEvent.click(first); });
    expect(lastChange()).toEqual({ photo_ids: ['f1'] });
    await waitFor(() => expect(screen.getByLabelText('concealed-photo-f1')).toBeChecked());
    vi.mocked(api.updateConcealed).mockResolvedValue(withSurface({ photo_ids: [] }));
    await act(async () => { fireEvent.click(screen.getByLabelText('concealed-photo-f1')); });
    expect(lastChange()).toEqual({ photo_ids: [] });
    cleanup();
    vi.mocked(api.openConcealedDraft).mockResolvedValue(withSurface({ photo_options: [] }));
    await begin();
    expect(screen.getByText(/nie ma zdjęć w kategorii/)).toBeInTheDocument();
    cleanup();
    vi.mocked(api.openConcealedDraft).mockResolvedValue(protocol());
    await begin();
    expect(screen.getByText('Najpierw wybierz powierzchnię.')).toBeInTheDocument();
  });

  it('saves the text fields when they are left and sends nothing per letter or for a blank over an empty field', async () => {
    await begin();
    const material = screen.getByLabelText('concealed-material');
    fireEvent.change(material, { target: { value: 'Grunt głęboko penetrujący' } });
    expect(api.updateConcealed).not.toHaveBeenCalled();
    await act(async () => { fireEvent.blur(material); });
    expect(lastChange()).toEqual({ material: 'Grunt głęboko penetrujący' });
    const batch = screen.getByLabelText('concealed-batch');
    fireEvent.change(batch, { target: { value: '  ' } });
    await act(async () => { fireEvent.blur(batch); });
    expect(api.updateConcealed).toHaveBeenCalledTimes(1);
    const note = screen.getByLabelText('concealed-work-note');
    fireEvent.change(note, { target: { value: 'dwie warstwy' } });
    await act(async () => { fireEvent.blur(note); });
    expect(lastChange()).toEqual({ work_note: 'dwie warstwy' });
    const day = screen.getByLabelText('concealed-held-on');
    await act(async () => { fireEvent.change(day, { target: { value: '2026-10-21' } }); });
    expect(lastChange()).toEqual({ held_on: '2026-10-21' });
  });

  it('records the people present by a tap and by hand, the whole list each time', async () => {
    vi.mocked(api.openConcealedDraft).mockResolvedValue(withSurface({ attendees: [{ person_id: null, name: 'Jan Sąsiad', role: 'administrator' }] }));
    vi.mocked(api.updateConcealed).mockImplementation(async (_p, _id, changes) => withSurface({
      attendees: (changes.attendees ?? []).map((a) => ('person_id' in a ? { person_id: a.person_id, name: 'Anna Nowak', role: 'Właścicielka' } : { person_id: null, name: a.name, role: a.role ?? null })),
    }));
    await begin();
    expect(screen.queryByLabelText('concealed-person-rep2')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByLabelText('concealed-person-rep1')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }] });
    expect(screen.getByLabelText('concealed-extra-add')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('concealed-extra'), { target: { value: 'Maria Kowalska, nadzór' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('concealed-extra-add')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }, { name: 'Maria Kowalska', role: 'nadzór' }] });
    await act(async () => { fireEvent.click(screen.getByLabelText('concealed-extra-remove-0')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Maria Kowalska', role: 'nadzór' }] });
  });

  it('turns into a one-sided protocol when the customer did not come: the day of the notification instead of the people and no consent', async () => {
    await begin();
    expect(screen.getByLabelText('concealed-consent-GIVEN')).toBeInTheDocument();
    expect(screen.queryByLabelText('concealed-notified-on')).toBeNull();
    vi.mocked(api.updateConcealed).mockResolvedValue(withSurface({ customer_absent: true }));
    await act(async () => { fireEvent.click(screen.getByLabelText('concealed-absent')); });
    expect(lastChange()).toEqual({ customer_absent: true });
    const notified = await screen.findByLabelText('concealed-notified-on');
    expect(notified).toHaveAttribute('type', 'date');
    expect(screen.queryByLabelText('concealed-person-rep1')).toBeNull();
    expect(screen.queryByLabelText('concealed-consent-GIVEN')).toBeNull();
    await act(async () => { fireEvent.change(notified, { target: { value: '2026-10-19' } }); });
    expect(lastChange()).toEqual({ notified_on: '2026-10-19' });
    vi.mocked(api.updateConcealed).mockResolvedValue(withSurface({ customer_absent: false }));
    await act(async () => { fireEvent.click(screen.getByLabelText('concealed-absent')); });
    expect(lastChange()).toEqual({ customer_absent: false });
  });

  it('chooses the result and the consent with large buttons, and asks for remarks only when they are needed', async () => {
    await begin();
    expect(screen.queryByLabelText('concealed-remarks')).toBeNull();
    for (const [label, change] of [['concealed-result-ACCEPTED', { result: 'ACCEPTED' }], ['concealed-consent-WITHHELD', { cover_consent: 'WITHHELD' }]] as const) {
      expect(screen.getByLabelText(label).className).toContain('min-h-11');
      await act(async () => { fireEvent.click(screen.getByLabelText(label)); });
      expect(lastChange()).toEqual(change);
    }
    vi.mocked(api.updateConcealed).mockResolvedValue(withSurface({ result: 'WITH_REMARKS' }));
    await act(async () => { fireEvent.click(screen.getByLabelText('concealed-result-WITH_REMARKS')); });
    expect(screen.getByLabelText('concealed-result-WITH_REMARKS')).toHaveAttribute('aria-pressed', 'true');
    const remarks = await screen.findByLabelText('concealed-remarks');
    fireEvent.change(remarks, { target: { value: 'Zacieki przy parapecie' } });
    await act(async () => { fireEvent.blur(remarks); });
    expect(lastChange()).toEqual({ remarks: 'Zacieki przy parapecie' });
  });

  it('says in words what is still missing and keeps the issue button shut; a ready protocol is issued and the form closes', async () => {
    vi.mocked(api.openConcealedDraft).mockResolvedValue(withSurface({ blockers: [
      { code: 'PHOTOS_REQUIRED', details: null }, { code: 'NOTIFIED_ON_REQUIRED', details: null }, { code: 'CONTRACT_REQUIRED', details: null }] }));
    await begin();
    expect(screen.getByLabelText('gate-PHOTOS_REQUIRED')).toHaveTextContent('Zaznacz co najmniej jedno zdjęcie');
    expect(screen.getByLabelText('gate-NOTIFIED_ON_REQUIRED')).toHaveTextContent('datę zawiadomienia');
    expect(screen.getByLabelText('gate-CONTRACT_REQUIRED')).toHaveTextContent('Brak wystawionej lub podpisanej umowy');
    expect(screen.getByLabelText('issue-concealed')).toBeDisabled();
    cleanup();
    vi.mocked(api.openConcealedDraft).mockResolvedValue(withSurface({ blockers: [] }));
    vi.mocked(api.issueConcealed).mockResolvedValue({} as never);
    vi.mocked(api.fetchConcealedWorks).mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValue({ items: [protocol({ status: 'ISSUED' })], total: 1 });
    await begin();
    expect(screen.getByText(/Wszystko gotowe/)).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-concealed')); });
    expect(api.issueConcealed).toHaveBeenCalledWith('p1', 'z1');
    await waitFor(() => expect(screen.queryByLabelText('concealed-form')).toBeNull());
    expect(screen.getByLabelText('concealed-note')).toHaveTextContent('Protokół został wystawiony');
    expect(screen.getByText('Ostatni protokół: nr 1 — wystawiony')).toBeInTheDocument();
  });

  it('a refusal of the server at issue replaces the list of what is missing', async () => {
    vi.mocked(api.openConcealedDraft).mockResolvedValue(withSurface({ blockers: [] }));
    vi.mocked(api.issueConcealed).mockRejectedValue(new ApiError('English', 422, 'CONCEALED_GATE_BLOCKED', {
      code: 'CONCEALED_GATE_BLOCKED', details: { blockers: [{ code: 'RESULT_REQUIRED', details: null }] } }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-concealed')); });
    expect(await screen.findByLabelText('gate-RESULT_REQUIRED')).toHaveTextContent('Wybierz wynik odbioru.');
    expect(screen.getByLabelText('issue-concealed')).toBeDisabled();
  });

  it.each([
    ['UNKNOWN_PHOTO', 'zdjęcie nie należy do tej powierzchni'],
    ['UNKNOWN_SURFACE', 'zarchiwizowana'],
    ['BAD_TIME', 'nieprawidłowa godzina'],
  ])('names the reason when the server refuses an entry: %s', async (reason, sentence) => {
    await begin();
    vi.mocked(api.updateConcealed).mockRejectedValueOnce(new ApiError('English', 422, 'CONCEALED_INVALID', { code: 'CONCEALED_INVALID', details: { key: 'x', reason } }));
    await act(async () => { fireEvent.click(screen.getByLabelText('concealed-result-ACCEPTED')); });
    expect(await screen.findByLabelText('concealed-error')).toHaveTextContent(sentence);
  });

  it('sends the taps one at a time in order, the working version waits for them, and a draft is abandoned only after a second tap', async () => {
    await begin();
    let release: (value: Concealed) => void = () => undefined;
    vi.mocked(api.updateConcealed).mockImplementationOnce(() => new Promise<Concealed>((resolve) => { release = resolve; }));
    vi.mocked(documentsApi.previewConcealedPdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 1 });
    fireEvent.click(screen.getByLabelText('concealed-result-ACCEPTED'));
    fireEvent.click(screen.getByLabelText('concealed-consent-GIVEN'));
    await waitFor(() => expect(api.updateConcealed).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('concealed-saving')).toHaveTextContent('Zapisuję…');
    await act(async () => { fireEvent.click(screen.getAllByLabelText('preview-concealed')[0]); });
    expect(documentsApi.previewConcealedPdf).not.toHaveBeenCalled();
    await act(async () => { release(withSurface()); });
    await waitFor(() => expect(api.updateConcealed).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.updateConcealed).mock.calls.map((c) => Object.keys(c[2])[0])).toEqual(['result', 'cover_consent']);
    await waitFor(() => expect(documentsApi.previewConcealedPdf).toHaveBeenCalledWith('p1'));
    expect(await screen.findByLabelText('concealed-note')).toHaveTextContent('Wersja robocza protokołu wysłana do czatu z botem');
    vi.mocked(api.abandonConcealedDraft).mockResolvedValue(protocol({ status: 'ARCHIVED' }));
    const abandon = screen.getByLabelText('abandon-concealed-draft');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonConcealedDraft).not.toHaveBeenCalled();
    expect(abandon).toHaveTextContent('Naciśnij ponownie');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonConcealedDraft).toHaveBeenCalledWith('p1', 'z1');
    await waitFor(() => expect(screen.queryByLabelText('concealed-form')).toBeNull());
    expect(screen.getByLabelText('concealed-note')).toHaveTextContent('Szkic odrzucony.');
  });

  it('sends the working version from the closed card and offers a retry when the load fails', async () => {
    vi.mocked(documentsApi.previewConcealedPdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 1 });
    renderCard();
    const previewButton = await screen.findByLabelText('preview-concealed');
    await act(async () => { fireEvent.click(previewButton); });
    expect(documentsApi.previewConcealedPdf).toHaveBeenCalledWith('p1');
    cleanup();
    vi.mocked(api.fetchConcealedWorks).mockRejectedValueOnce(new Error('net')).mockResolvedValue({ items: [], total: 0 });
    renderCard();
    expect(await screen.findByText('Nie udało się wczytać protokołów.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' })); });
    expect(await screen.findByLabelText('start-concealed')).toBeInTheDocument();
  });

  it('is localised in Russian and keeps every control touch-sized', async () => {
    localStorage.setItem('locale', 'ru');
    const form = await begin();
    expect(screen.getByText('Протокол приёмки скрываемых работ')).toBeInTheDocument();
    expect(screen.getByLabelText('concealed-result-ACCEPTED')).toHaveTextContent(ru.concealed.result_options.ACCEPTED);
    expect((screen.getByLabelText('concealed-work-kind') as HTMLSelectElement).options[1].textContent).toBe('Грунтование основания');
    for (const control of form.querySelectorAll('input:not([type=checkbox]), select, textarea, button')) {
      expect((control as HTMLElement).className).toMatch(/min-h-11/);
    }
  });
});
