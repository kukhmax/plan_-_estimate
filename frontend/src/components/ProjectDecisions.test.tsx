import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/decisions';
import * as documentsApi from '../api/documents';
import { ApiError } from '../api/http';
import * as peopleApi from '../api/representatives';
import { I18nProvider } from '../hooks/useI18n';
import ru from '../locales/ru.json';
import type { Decision, DecisionItem, DecisionRiskOption } from '../types/decision';
import type { ProjectRepresentative } from '../types/representative';
import { ProjectDecisions } from './ProjectDecisions';

vi.mock('../api/decisions', () => ({
  fetchDecisions: vi.fn(),
  openDecisionDraft: vi.fn(),
  updateDecision: vi.fn(),
  abandonDecisionDraft: vi.fn(),
  issueDecision: vi.fn(),
}));
vi.mock('../api/documents', () => ({ previewDecisionPdf: vi.fn() }));
vi.mock('../api/representatives', () => ({ fetchRepresentatives: vi.fn() }));

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const riskItem = (over: Partial<DecisionItem> = {}): DecisionItem => ({
  id: 'i1', source: 'RISK', risk_id: 'r1', room_id: 'room1', room_name: 'Salon', severity: 'CRITICAL', blocks_finishing: true,
  title: 'Podwyższona wilgotność podłoża', state: 'Zmierzona wilgotność przekracza dopuszczalny poziom.', recommendation: 'Wstrzymuję prace do czasu osuszenia podłoża.',
  consequence: 'Wykończenie na wilgotnym podłożu może się odspajać.', price: null, decision: null, executor_action: null, order_ref: null, note: null,
  risk_active: true, ...over,
});
const ownItem = (over: Partial<DecisionItem> = {}): DecisionItem => ({
  id: 'i2', source: 'OWN', risk_id: null, room_id: 'room1', room_name: 'Salon', severity: null, blocks_finishing: false, title: 'Wydłużenie przerwy technologicznej',
  state: null, recommendation: 'Odczekać 72 godziny.', consequence: 'Gładź może pękać.', price: '300.00', decision: null, executor_action: null, order_ref: null, note: null,
  risk_active: true, ...over,
});
const option = (over: Partial<DecisionRiskOption> = {}): DecisionRiskOption => ({
  id: 'r1', room_id: 'room1', room_name: 'Salon', severity: 'CRITICAL', blocks_finishing: true, title: 'Podwyższona wilgotność podłoża',
  consequence: 'Wykończenie może się odspajać.', used: false, ...over,
});
function protocol(over: Partial<Decision> = {}): Decision {
  return {
    id: 'd1', project_id: 'p1', sequence: 1, status: 'DRAFT', held_on: '2026-10-20', held_time: '10:00', attendees: [], understood: false, signature_refused: false,
    notes: null, items: [], risk_options: [option(), option({ id: 'r2', severity: 'HIGH', title: 'Spękania na łączeniach płyt g-k', blocks_finishing: false, room_name: 'Kuchnia' })],
    rooms: [{ id: 'room1', name: 'Salon' }, { id: 'room2', name: 'Kuchnia' }], blockers: [{ code: 'NO_ITEMS', details: null }],
    contract: { id: 'c1', version: 1, status: 'SIGNED' }, created_at: 'x', updated_at: 'x', ...over,
  };
}
const person = (over: Partial<ProjectRepresentative> = {}): ProjectRepresentative => ({
  id: 'rep1', project_id: 'p1', side: 'CUSTOMER', name: 'Anna Nowak', role_title: 'Właścicielka', phone: null, email: null,
  may_accept_and_sign: true, is_archived: false, created_at: 'x', updated_at: 'x', ...over,
});

const renderCard = () => render(<I18nProvider><ProjectDecisions projectId="p1" /></I18nProvider>);
async function begin() {
  renderCard();
  const start = await screen.findByLabelText('start-decision');
  await act(async () => { fireEvent.click(start); });
  return screen.findByLabelText('decision-form');
}
const lastChange = () => {
  const calls = vi.mocked(api.updateDecision).mock.calls;
  return calls[calls.length - 1][2];
};

describe('ProjectDecisions (Stage 16I.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchDecisions).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol());
    vi.mocked(api.updateDecision).mockImplementation(async () => protocol());
    vi.mocked(peopleApi.fetchRepresentatives).mockResolvedValue({ items: [person(), person({ id: 'rep2', name: 'Piotr Archiwalny', is_archived: true })], total: 2 });
  });
  afterEach(cleanup);

  it('offers to start with full-width touch-sized buttons and opens the draft, writing the day and hour of now when there are none', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ held_on: null, held_time: null }));
    renderCard();
    const button = await screen.findByLabelText('start-decision');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('w-full');
    expect(button).toHaveTextContent('Rozpocznij protokół decyzji');
    expect(screen.getByLabelText('preview-decision').className).toContain('min-h-11');
    expect(api.openDecisionDraft).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(button); });
    await screen.findByLabelText('decision-form');
    await waitFor(() => expect(api.updateDecision).toHaveBeenCalledWith('p1', 'd1', {
      held_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), held_time: expect.stringMatching(/^\d{2}:\d{2}$/) }));
  });

  it('keeps what the server has and mentions the latest issued protocol', async () => {
    vi.mocked(api.fetchDecisions).mockResolvedValue({ items: [protocol({ id: 'd0', sequence: 3, status: 'ISSUED' })], total: 1 });
    await begin();
    expect(api.updateDecision).not.toHaveBeenCalled();
    cleanup();
    renderCard();
    expect(await screen.findByText('Ostatni protokół: nr 3 — wystawiony')).toBeInTheDocument();
    expect(screen.getByLabelText('start-decision')).toHaveTextContent('Nowy protokół decyzji');
  });

  it('adds a risk of the application with one tap under a new UUID key, and offers only the risks that are not in the protocol yet', async () => {
    await begin();
    const first = screen.getByLabelText('decision-add-risk-r1');
    expect(first.className).toContain('min-h-11');
    expect(first).toHaveTextContent('Podwyższona wilgotność podłoża · Salon · Krytyczne');
    expect(screen.getByLabelText('decision-add-risk-r2')).toHaveTextContent('Spękania na łączeniach płyt g-k · Kuchnia · Wysokie');
    await act(async () => { fireEvent.click(first); });
    const [[key, change]] = Object.entries(lastChange().items!);
    expect(key).toMatch(UUID);
    expect(change).toEqual({ risk_id: 'r1' });
    vi.mocked(api.updateDecision).mockResolvedValue(protocol({ items: [riskItem()], risk_options: [option({ used: true }), option({ id: 'r2', title: 'Inne' })] }));
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-add-risk-r2')); });
    await waitFor(() => expect(screen.queryByLabelText('decision-add-risk-r1')).toBeNull());
    expect(screen.getByLabelText('decision-add-risk-r2')).toBeInTheDocument();
  });

  it('says there is nothing to add when no risk is left', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ risk_options: [option({ used: true })], items: [riskItem()] }));
    await begin();
    expect(screen.getByText(/Brak ryzyk do dodania/)).toBeInTheDocument();
    cleanup();
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol());
    await begin();
    expect(screen.getByText(/Brak pozycji — dodaj ryzyko z badania albo własne zalecenie/)).toBeInTheDocument();
  });

  it('shows an item with the catalogue\'s words, what was found, the recommendation and the risk, and flags a risk that is gone', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ items: [riskItem(), riskItem({ id: 'i3', risk_active: false, title: 'Dawne ryzyko' }), ownItem()] }));
    await begin();
    const card = screen.getByLabelText('decision-item-i1');
    expect(card).toHaveTextContent('Podwyższona wilgotność podłoża · Salon · Krytyczne');
    expect(card).toHaveTextContent('Stan stwierdzony: Zmierzona wilgotność przekracza dopuszczalny poziom.');
    expect(card).toHaveTextContent('Zalecenie Wykonawcy: Wstrzymuję prace do czasu osuszenia podłoża.');
    expect(card).toHaveTextContent('Ryzyko i możliwe skutki: Wykończenie na wilgotnym podłożu');
    expect(card).toHaveTextContent('Ryzyko wstrzymuje prace wykończeniowe');
    expect(within(card).queryByText(/nie jest już stwierdzone/)).toBeNull();
    expect(within(screen.getByLabelText('decision-item-i3')).getByText(/nie jest już stwierdzone w badaniu/)).toBeInTheDocument();
    const own = screen.getByLabelText('decision-item-i2');
    expect(own).toHaveTextContent('Cena zalecenia: 300.00');
    expect(own).not.toHaveTextContent('Stan stwierdzony');
  });

  it('records the decision with one large button and asks for the order number only when the customer accepts', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ items: [riskItem()] }));
    vi.mocked(api.updateDecision).mockResolvedValue(protocol({ items: [riskItem()] }));
    await begin();
    for (const [choice, label] of [['ACCEPTED', 'Akceptuje zalecenie'], ['DECLINED', 'Rezygnuje z zalecenia'], ['INSISTS', 'Żąda wykonania wbrew zaleceniu']] as const) {
      const button = screen.getByLabelText(`decision-choice-i1-${choice}`);
      expect(button.className).toContain('min-h-11');
      expect(button).toHaveTextContent(label);
      await act(async () => { fireEvent.click(button); });
      expect(lastChange()).toEqual({ items: { i1: { decision: choice } } });
    }
    expect(screen.queryByLabelText('decision-order-i1')).toBeNull();
    vi.mocked(api.updateDecision).mockResolvedValue(protocol({ items: [riskItem({ decision: 'ACCEPTED' })] }));
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-choice-i1-ACCEPTED')); });
    expect(screen.getByLabelText('decision-choice-i1-ACCEPTED')).toHaveAttribute('aria-pressed', 'true');
    const order = await screen.findByLabelText('decision-order-i1');
    fireEvent.change(order, { target: { value: 'Z/12' } });
    expect(api.updateDecision).toHaveBeenCalledTimes(4);  // nothing per letter
    await act(async () => { fireEvent.blur(order); });
    expect(lastChange()).toEqual({ items: { i1: { order_ref: 'Z/12' } } });
  });

  it('asks the contractor for his own answer only when the customer insists on the work against the recommendation', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ items: [riskItem({ decision: 'DECLINED' })] }));
    await begin();
    expect(screen.queryByLabelText('decision-action-i1-PERFORM')).toBeNull();
    cleanup();
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ items: [riskItem({ decision: 'INSISTS' })] }));
    vi.mocked(api.updateDecision).mockResolvedValue(protocol({ items: [riskItem({ decision: 'INSISTS' })] }));
    await begin();
    const perform = screen.getByLabelText('decision-action-i1-PERFORM');
    expect(perform.className).toContain('min-h-11');
    expect(perform).toHaveTextContent('Wykonam po sporządzeniu protokołu');
    expect(screen.getByLabelText('decision-action-i1-REFUSE')).toHaveTextContent('Odmawiam wykonania');
    await act(async () => { fireEvent.click(perform); });
    expect(lastChange()).toEqual({ items: { i1: { executor_action: 'PERFORM' } } });
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-action-i1-REFUSE')); });
    expect(lastChange()).toEqual({ items: { i1: { executor_action: 'REFUSE' } } });
  });

  it('writes a recommendation of his own: nothing is added until the three texts are there, price with decimal input, room optional', async () => {
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-own-open')); });
    const save = screen.getByLabelText('decision-own-save');
    expect(save).toBeDisabled();
    expect(save.className).toContain('min-h-11');
    expect(screen.getByLabelText('decision-own-price')).toHaveAttribute('inputmode', 'decimal');
    fireEvent.change(screen.getByLabelText('decision-own-title'), { target: { value: ' Wydłużenie przerwy ' } });
    fireEvent.change(screen.getByLabelText('decision-own-recommendation'), { target: { value: 'Odczekać 72 godziny' } });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('decision-own-consequence'), { target: { value: 'Gładź może pękać' } });
    expect(save).not.toBeDisabled();
    const rooms = screen.getByLabelText('decision-own-room') as HTMLSelectElement;
    expect(Array.from(rooms.options).map((o) => o.textContent)).toEqual(['— bez pomieszczenia —', 'Salon', 'Kuchnia']);
    fireEvent.change(rooms, { target: { value: 'room2' } });
    fireEvent.change(screen.getByLabelText('decision-own-price'), { target: { value: '300,50' } });
    await act(async () => { fireEvent.click(save); });
    const [[key, change]] = Object.entries(lastChange().items!);
    expect(key).toMatch(UUID);
    expect(change).toEqual({ title: 'Wydłużenie przerwy', recommendation: 'Odczekać 72 godziny', consequence: 'Gładź może pękać', price: '300,50', room_id: 'room2' });
    expect(screen.queryByLabelText('decision-own-form')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-own-open')); });
    fireEvent.change(screen.getByLabelText('decision-own-title'), { target: { value: 'A' } });
    fireEvent.change(screen.getByLabelText('decision-own-recommendation'), { target: { value: 'B' } });
    fireEvent.change(screen.getByLabelText('decision-own-consequence'), { target: { value: 'C' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-own-save')); });
    expect(Object.values(lastChange().items!)[0]).toEqual({ title: 'A', recommendation: 'B', consequence: 'C' });  // no price, no room: not sent
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-own-open')); });
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-own-cancel')); });
    expect(screen.queryByLabelText('decision-own-form')).toBeNull();
  });

  it('saves the note of an item when the field is left and removes an item only after a second tap', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ items: [riskItem()] }));
    vi.mocked(api.updateDecision).mockResolvedValue(protocol({ items: [riskItem()] }));
    await begin();
    const note = screen.getByLabelText('decision-note-i1');
    fireEvent.change(note, { target: { value: 'Klient był zaskoczony' } });
    expect(api.updateDecision).not.toHaveBeenCalled();
    await act(async () => { fireEvent.blur(note); });
    expect(lastChange()).toEqual({ items: { i1: { note: 'Klient był zaskoczony' } } });
    const remove = screen.getByLabelText('decision-item-remove-i1');
    expect(remove.className).toContain('min-h-11');
    await act(async () => { fireEvent.click(remove); });
    expect(api.updateDecision).toHaveBeenCalledTimes(1);
    expect(remove).toHaveTextContent('Naciśnij ponownie, aby usunąć pozycję');
    await act(async () => { fireEvent.click(remove); });
    expect(lastChange()).toEqual({ items: { i1: null } });
  });

  it('records the people present by a tap and by hand, the whole list each time', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ attendees: [{ person_id: null, name: 'Jan Sąsiad', role: 'administrator' }] }));
    vi.mocked(api.updateDecision).mockImplementation(async (_p, _id, changes) => protocol({
      attendees: (changes.attendees ?? []).map((a) => ('person_id' in a ? { person_id: a.person_id, name: 'Anna Nowak', role: 'Właścicielka' } : { person_id: null, name: a.name, role: a.role ?? null })),
    }));
    await begin();
    expect(screen.queryByLabelText('decision-person-rep2')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-person-rep1')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }] });
    expect(screen.getByLabelText('decision-extra-add')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('decision-extra'), { target: { value: 'Maria Kowalska, nadzór' } });
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-extra-add')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Jan Sąsiad', role: 'administrator' }, { name: 'Maria Kowalska', role: 'nadzór' }] });
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-extra-remove-0')); });
    expect(lastChange()).toEqual({ attendees: [{ person_id: 'rep1' }, { name: 'Maria Kowalska', role: 'nadzór' }] });
  });

  it('records the declaration of the customer or his refusal to sign, with the notes it needs', async () => {
    await begin();
    for (const [label, change] of [['decision-understood', { understood: true }], ['decision-refused', { signature_refused: true }]] as const) {
      expect(screen.getByLabelText(label).className).toContain('h-5');
      await act(async () => { fireEvent.click(screen.getByLabelText(label)); });
      expect(lastChange()).toEqual(change);
    }
    expect(screen.queryByText('Opisz okoliczności w uwagach poniżej.')).toBeNull();
    vi.mocked(api.updateDecision).mockResolvedValue(protocol({ signature_refused: true }));
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-refused')); });
    expect(await screen.findByText('Opisz okoliczności w uwagach poniżej.')).toBeInTheDocument();
    const notes = screen.getByLabelText('decision-notes');
    fireEvent.change(notes, { target: { value: 'Odmówił podpisu' } });
    await act(async () => { fireEvent.blur(notes); });
    expect(lastChange()).toEqual({ notes: 'Odmówił podpisu' });
    const day = screen.getByLabelText('decision-held-on');
    await act(async () => { fireEvent.change(day, { target: { value: '2026-10-21' } }); });
    expect(lastChange()).toEqual({ held_on: '2026-10-21' });
  });

  it('says in words what is still missing and keeps the issue button shut; a ready protocol is issued and the form closes', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ blockers: [
      { code: 'ITEM_DECISION_REQUIRED', details: { item_ids: ['i1'] } }, { code: 'ITEM_ACTION_REQUIRED', details: { item_ids: ['i1'] } },
      { code: 'DECLARATION_REQUIRED', details: null }, { code: 'REFUSAL_NOTE_REQUIRED', details: null }, { code: 'CONTRACT_REQUIRED', details: null }] }));
    await begin();
    expect(screen.getByLabelText('gate-ITEM_DECISION_REQUIRED')).toHaveTextContent('Wybierz decyzję Zamawiającego przy każdej pozycji.');
    expect(screen.getByLabelText('gate-ITEM_ACTION_REQUIRED')).toHaveTextContent('wykonasz czy odmawiasz');
    expect(screen.getByLabelText('gate-DECLARATION_REQUIRED')).toHaveTextContent('albo jego odmowę podpisania');
    expect(screen.getByLabelText('gate-REFUSAL_NOTE_REQUIRED')).toHaveTextContent('Odmowę podpisania opisz w uwagach.');
    expect(screen.getByLabelText('gate-CONTRACT_REQUIRED')).toHaveTextContent('Brak wystawionej lub podpisanej umowy');
    expect(screen.getByLabelText('issue-decision')).toBeDisabled();
    cleanup();
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ blockers: [] }));
    vi.mocked(api.issueDecision).mockResolvedValue({} as never);
    vi.mocked(api.fetchDecisions).mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValue({ items: [protocol({ status: 'ISSUED' })], total: 1 });
    await begin();
    expect(screen.getByText(/Wszystko gotowe/)).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-decision')); });
    expect(api.issueDecision).toHaveBeenCalledWith('p1', 'd1');
    await waitFor(() => expect(screen.queryByLabelText('decision-form')).toBeNull());
    expect(screen.getByLabelText('decision-note-message')).toHaveTextContent('Protokół został wystawiony');
    expect(screen.getByText('Ostatni protokół: nr 1 — wystawiony')).toBeInTheDocument();
  });

  it('a refusal of the server at issue replaces the list of what is missing', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ blockers: [] }));
    vi.mocked(api.issueDecision).mockRejectedValue(new ApiError('English', 422, 'DECISION_GATE_BLOCKED', {
      code: 'DECISION_GATE_BLOCKED', details: { blockers: [{ code: 'ITEM_RISK_GONE', details: { item_ids: ['i1'] } }] } }));
    await begin();
    await act(async () => { fireEvent.click(screen.getByLabelText('issue-decision')); });
    expect(await screen.findByLabelText('gate-ITEM_RISK_GONE')).toHaveTextContent('Któreś ryzyko nie jest już stwierdzone');
    expect(screen.getByLabelText('issue-decision')).toBeDisabled();
  });

  it.each([
    ['UNKNOWN_RISK', 'to ryzyko nie należy do obiektu'],
    ['BAD_ITEM', 'własne zalecenie wymaga'],
    ['ITEM_LOCKED', 'nie zmienia się'],
    ['BAD_MONEY', 'nieprawidłowa kwota'],
  ])('names the reason when the server refuses an entry: %s', async (reason, sentence) => {
    await begin();
    vi.mocked(api.updateDecision).mockRejectedValueOnce(new ApiError('English', 422, 'DECISION_INVALID', { code: 'DECISION_INVALID', details: { key: 'x', reason } }));
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-understood')); });
    expect(await screen.findByLabelText('decision-error')).toHaveTextContent(sentence);
  });

  it('sends the taps one at a time in order, the working version waits for them, and a draft is abandoned only after a second tap', async () => {
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ items: [riskItem()] }));
    await begin();
    let release: (value: Decision) => void = () => undefined;
    vi.mocked(api.updateDecision).mockImplementationOnce(() => new Promise<Decision>((resolve) => { release = resolve; }));
    vi.mocked(documentsApi.previewDecisionPdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 1 });
    fireEvent.click(screen.getByLabelText('decision-choice-i1-DECLINED'));
    fireEvent.click(screen.getByLabelText('decision-understood'));
    await waitFor(() => expect(api.updateDecision).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('decision-saving')).toHaveTextContent('Zapisuję…');
    await act(async () => { fireEvent.click(screen.getAllByLabelText('preview-decision')[0]); });
    expect(documentsApi.previewDecisionPdf).not.toHaveBeenCalled();
    await act(async () => { release(protocol({ items: [riskItem()] })); });
    await waitFor(() => expect(api.updateDecision).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.updateDecision).mock.calls.map((c) => Object.keys(c[2])[0])).toEqual(['items', 'understood']);
    await waitFor(() => expect(documentsApi.previewDecisionPdf).toHaveBeenCalledWith('p1'));
    expect(await screen.findByLabelText('decision-note-message')).toHaveTextContent('Wersja robocza protokołu wysłana do czatu z botem');
    vi.mocked(api.abandonDecisionDraft).mockResolvedValue(protocol({ status: 'ARCHIVED' }));
    const abandon = screen.getByLabelText('abandon-decision-draft');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonDecisionDraft).not.toHaveBeenCalled();
    expect(abandon).toHaveTextContent('Naciśnij ponownie');
    await act(async () => { fireEvent.click(abandon); });
    expect(api.abandonDecisionDraft).toHaveBeenCalledWith('p1', 'd1');
    await waitFor(() => expect(screen.queryByLabelText('decision-form')).toBeNull());
    expect(screen.getByLabelText('decision-note-message')).toHaveTextContent('Szkic odrzucony.');
  });

  it('sends the working version from the closed card and offers a retry when the load fails', async () => {
    vi.mocked(documentsApi.previewDecisionPdf).mockResolvedValue({ sent: true, pages: 2, byte_size: 1 });
    renderCard();
    const previewButton = await screen.findByLabelText('preview-decision');
    await act(async () => { fireEvent.click(previewButton); });
    expect(documentsApi.previewDecisionPdf).toHaveBeenCalledWith('p1');
    cleanup();
    vi.mocked(api.fetchDecisions).mockRejectedValueOnce(new Error('net')).mockResolvedValue({ items: [], total: 0 });
    renderCard();
    expect(await screen.findByText('Nie udało się wczytać protokołów decyzji.')).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' })); });
    expect(await screen.findByLabelText('start-decision')).toBeInTheDocument();
  });

  it('is localised in Russian and keeps every control touch-sized, also in the form of an own recommendation', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(api.openDecisionDraft).mockResolvedValue(protocol({ items: [riskItem({ decision: 'INSISTS' })] }));
    const form = await begin();
    expect(screen.getByText('Протокол информирования и решений')).toBeInTheDocument();
    expect(screen.getByLabelText('decision-choice-i1-INSISTS')).toHaveTextContent(ru.decisions.decision_options.INSISTS);
    expect(screen.getByLabelText('decision-action-i1-REFUSE')).toHaveTextContent('Отказываюсь выполнять');
    expect(screen.getByLabelText('decision-add-risk-r1')).toHaveTextContent('Критический');
    await act(async () => { fireEvent.click(screen.getByLabelText('decision-own-open')); });
    for (const control of form.querySelectorAll('input:not([type=checkbox]), select, textarea, button')) {
      expect((control as HTMLElement).className).toMatch(/min-h-11/);
    }
  });
});
