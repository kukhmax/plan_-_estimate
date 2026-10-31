/** V2-8 — the open page of the client: the estimate with its sums, the approval, the proposals, the states of a link that does not work. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/clientPortal';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { PortalEstimate, PortalPage, PortalProposal } from '../types/clientLink';
import { ClientPage, isClientPagePath, tokenFromHash } from './ClientPage';

vi.mock('../api/clientPortal', () => ({
  fetchPortalPage: vi.fn(),
  decidePortalEstimate: vi.fn(),
  decidePortalProposal: vi.fn(),
  fetchPortalWhy: vi.fn(),
}));

const TOKEN = 'T'.repeat(43);
const STATEMENT = { pl: 'Zatwierdzam wycenę nr 1 na kwotę 3489,66 PLN.', text: 'Zatwierdzam wycenę nr 1 na kwotę 3489,66 PLN.' };
const DECLINE = { pl: 'Nie zatwierdzam wyceny nr 1 na kwotę 3489,66 PLN.', text: 'Nie zatwierdzam wyceny nr 1 na kwotę 3489,66 PLN.' };

const ESTIMATE = (overrides: Partial<PortalEstimate> = {}): PortalEstimate => ({
  id: 'e1', version: 1, status: 'FINAL', name: null, currency: 'PLN', total: '2837.12', vat_mode: 'RATE', vat_rate_percent: 23, vat_amount: '652.54',
  gross_total: '3489.66', hash: 'h'.repeat(64), consent: null, accept_statement: STATEMENT, decline_statement: DECLINE,
  lines: [
    { position: 1, room_name: 'Salon', surface_name: 'Ściana 1', description: 'Gruntowanie ścian', unit: 'M2', quantity: '45.760', unit_price: '7.00', amount: '320.32' },
    { position: 2, room_name: 'Łazienka', surface_name: null, description: 'Gładź dwuwarstwowa', unit: 'M2', quantity: '45.760', unit_price: '35.00', amount: '1601.60' },
    { position: 3, room_name: 'Salon', surface_name: 'Ściana 2', description: 'Wywóz odpadów', unit: 'FLAT', quantity: '1.000', unit_price: '100.00', amount: '100.00' },
  ],
  ...overrides,
});
const PROPOSAL = (overrides: Partial<PortalProposal> = {}): PortalProposal => ({
  id: 'p1', sequence: 1, title: 'Gruntowanie sufitu', description: 'Dodatkowa warstwa', amount: '450.50', currency: 'PLN', extra_days: 2, status: 'OPEN',
  hash: 'p'.repeat(64), created_at: '2026-10-26T10:00:00Z', consent: null,
  accept_statement: { pl: 'Zatwierdzam pracę „Gruntowanie sufitu”.', text: 'Zatwierdzam pracę „Gruntowanie sufitu”.' },
  decline_statement: { pl: 'Nie akceptuję pracy „Gruntowanie sufitu”.', text: 'Nie akceptuję pracy „Gruntowanie sufitu”.' },
  ...overrides,
});
const PAGE = (overrides: Partial<PortalPage> = {}): PortalPage => ({
  link: { expires_at: '2026-11-25T10:00:00Z', language: 'pl' }, lang: 'pl',
  contractor: { name: 'Vvv Remonty', phone: '+48600100200', email: 'biuro@vvv.pl', city: 'Kraków' },
  project: { name: 'Mieszkanie 50 m²', address: 'ul. Długa 5', city: 'Kraków', postal_code: '30-001' },
  estimate: ESTIMATE(), proposals: [], ...overrides,
});

/** The estimate waits for a decision: the first step is the choice. */
const choose = async (label = 'client-estimate-agree') => {
  fireEvent.click(await screen.findByLabelText(label));
};

function show(token = TOKEN) {
  render(
    <I18nProvider persist={false}>
      <ClientPage token={token} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('pl-PL');
  document.head.querySelectorAll('meta[name="robots"], meta[name="referrer"]').forEach((el) => el.remove());
});

describe('the address', () => {
  it('keeps the secret after the # and knows the path of the page', () => {
    expect(tokenFromHash('#abc')).toBe('abc');
    expect(tokenFromHash('')).toBe('');
    expect(tokenFromHash('# abc ')).toBe('abc');
    expect(isClientPagePath('/c')).toBe(true);
    expect(isClientPagePath('/c/')).toBe(true);
    expect(isClientPagePath('/')).toBe(false);
    expect(isClientPagePath('/c/abc')).toBe(false);
    expect(isClientPagePath('/clients')).toBe(false);
  });
});

describe('the estimate', () => {
  it('shows the net taken out of a gross sum when the prices include the VAT', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({
      estimate: ESTIMATE({ total: '2837.12', vat_rate_percent: 8, vat_included: true, net_total: '2626.96', vat_amount: '210.16', gross_total: '2837.12' }),
    }));
    show();
    expect(await screen.findByLabelText('client-total-net')).toHaveTextContent('2626,96 PLN');
    expect(screen.getByLabelText('client-total-vat')).toHaveTextContent('210,16 PLN');
    expect(screen.getByLabelText('client-total-gross')).toHaveTextContent('2837,12 PLN');
  });

  it('shows the contractor, the object, the lines by room and the sums', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    show();
    expect(await screen.findByLabelText('client-estimate')).toHaveTextContent('Wycena nr 1');
    expect(screen.getByLabelText('client-contractor')).toHaveTextContent('Vvv Remonty');
    expect(screen.getByLabelText('client-contractor')).toHaveTextContent('ul. Długa 5, 30-001 Kraków');
    expect(screen.getByLabelText('client-call')).toHaveAttribute('href', 'tel:+48600100200');
    expect(screen.getByLabelText('client-mail')).toHaveAttribute('href', 'mailto:biuro@vvv.pl');
    const estimate = screen.getByLabelText('client-estimate');
    expect(within(estimate).getByText('Salon')).toBeInTheDocument();
    expect(within(estimate).getByText('Ściana 2')).toBeInTheDocument();
    // a room's lines are together even when the estimate interleaves them with another room's
    const headings = within(estimate).getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(headings.filter((h) => h === 'Salon')).toHaveLength(1);
    expect(headings.slice(0, 2)).toEqual(['Salon', 'Łazienka']);
    expect(within(estimate).getByText('Gruntowanie ścian')).toBeInTheDocument();
    expect(within(estimate).getByText('45,76 m² × 7,00')).toBeInTheDocument();
    expect(screen.getByLabelText('client-total-net')).toHaveTextContent('2837,12 PLN');
    expect(screen.getByLabelText('client-total-vat')).toHaveTextContent('652,54 PLN');
    expect(screen.getByLabelText('client-total-gross')).toHaveTextContent('3489,66 PLN');
    expect(screen.getByLabelText('client-expires')).toHaveTextContent('Link ważny do');
    expect(api.fetchPortalPage).toHaveBeenCalledWith(TOKEN, null);
  });

  it('shows one total when the estimate has no VAT and says so when the sale is exempt', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ estimate: ESTIMATE({ vat_mode: null, vat_rate_percent: null, vat_amount: null, gross_total: null }) }));
    show();
    expect(await screen.findByLabelText('client-total')).toHaveTextContent('2837,12 PLN');
    expect(screen.queryByLabelText('client-total-gross')).toBeNull();
  });

  it('says that there is no estimate yet', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ estimate: null }));
    show();
    expect(await screen.findByLabelText('client-no-estimate')).toHaveTextContent('nie przygotował jeszcze wyceny');
  });

  it('marks the page noindex and without a referrer, and writes nothing to the storage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    show();
    await screen.findByLabelText('client-estimate');
    expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow');
    expect(document.head.querySelector('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer');
    fireEvent.change(screen.getByLabelText('client-language'), { target: { value: 'ru' } });
    await waitFor(() => expect(api.fetchPortalPage).toHaveBeenCalledWith(TOKEN, 'ru'));
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});

describe('approving the estimate', () => {
  it('needs the name and the box, sends what the client saw, and shows the approval', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    const accepted = PAGE({
      estimate: ESTIMATE({ status: 'ACCEPTED', accept_statement: null, consent: { kind: 'ESTIMATE_ACCEPTED', signer_name: 'Jan Kowalski', comment: null, created_at: '2026-10-26T11:00:00Z' } }),
    });
    vi.mocked(api.decidePortalEstimate).mockResolvedValue(accepted);
    show();
    await choose();
    expect(await screen.findByLabelText('client-estimate-statement')).toHaveTextContent('Zatwierdzam wycenę nr 1');
    fireEvent.change(screen.getByLabelText('client-estimate-name'), { target: { value: 'Jan Kowalski' } });
    fireEvent.click(screen.getByLabelText('client-estimate-agree'));
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    await waitFor(() =>
      expect(api.decidePortalEstimate).toHaveBeenCalledWith(TOKEN, 'pl', {
        estimate_id: 'e1', version: 1, hash: 'h'.repeat(64), decision: 'ACCEPT', signer_name: 'Jan Kowalski', agree: true, comment: null,
      }),
    );
    const done = await screen.findByLabelText('client-estimate-accepted');
    expect(done).toHaveTextContent('Wycena zatwierdzona');
    expect(done).toHaveTextContent('Jan Kowalski');
    expect(screen.queryByLabelText('client-estimate-form')).toBeNull();
  });

  it.each([
    ['AGREE_REQUIRED', 422, 'Zaznacz pole zgody.'],
    ['NAME_REQUIRED', 422, 'Wpisz imię i nazwisko.'],
    ['ESTIMATE_CHANGED', 409, 'Wycena została zmieniona'],
    ['ALREADY_DECIDED', 409, 'Ta decyzja jest już zapisana'],
    ['RATE_LIMITED', 429, 'Zbyt wiele prób'],
  ])('says in words what the server refused (%s)', async (code, status, words) => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    vi.mocked(api.decidePortalEstimate).mockRejectedValue(new ApiError('x', status, code));
    show();
    await choose();
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    expect(await screen.findByRole('alert')).toHaveTextContent(words);
    expect(screen.getByLabelText('client-estimate-form')).toBeInTheDocument();
  });

  it('says that there is no connection', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    vi.mocked(api.decidePortalEstimate).mockRejectedValue(new ApiError('network', 0, 'NETWORK'));
    show();
    await choose();
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia');
  });

  it('shows an approved estimate without the form', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(
      PAGE({ estimate: ESTIMATE({ status: 'ACCEPTED', accept_statement: null, consent: { kind: 'ESTIMATE_ACCEPTED', signer_name: 'Ewa Nowak', comment: null, created_at: '2026-10-26T11:00:00Z' } }) }),
    );
    show();
    expect(await screen.findByLabelText('client-estimate-accepted')).toHaveTextContent('Ewa Nowak');
    expect(screen.queryByLabelText('client-estimate-submit')).toBeNull();
  });

  it('says what comes next after the approval and how to reach the contractor (UX walk)', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(
      PAGE({ estimate: ESTIMATE({ status: 'ACCEPTED', accept_statement: null, consent: { kind: 'ESTIMATE_ACCEPTED', signer_name: 'Ewa Nowak', comment: null, created_at: '2026-10-26T11:00:00Z' } }) }),
    );
    show();
    const next = await screen.findByLabelText('client-what-next');
    expect(next).toHaveTextContent('Co dalej?');
    expect(screen.getByLabelText('client-next-call')).toHaveAttribute('href', 'tel:+48600100200');
    expect(screen.getByLabelText('client-next-mail')).toHaveAttribute('href', 'mailto:biuro@vvv.pl');
  });

  it('shows one line per work in a room with the walls added up (UX walk)', async () => {
    const lines = [
      { position: 1, room_name: 'Salon', surface_name: 'Ściana 1', description: 'Malowanie', unit: 'M2', quantity: '10.500', unit_price: '20.00', amount: '210.00' },
      { position: 2, room_name: 'Salon', surface_name: 'Ściana 2', description: 'Malowanie', unit: 'M2', quantity: '12.250', unit_price: '20.00', amount: '245.00' },
      { position: 3, room_name: 'Kuchnia', surface_name: 'Ściana 1', description: 'Malowanie', unit: 'M2', quantity: '8.000', unit_price: '20.00', amount: '160.00' },
    ];
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ estimate: ESTIMATE({ lines }) }));
    show();
    await screen.findByLabelText('client-estimate');
    const items = screen.getAllByRole('listitem').filter((li) => li.textContent?.includes('Malowanie'));
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('22,75');
    expect(items[0]).toHaveTextContent('455,00');
    expect(items[0]).not.toHaveTextContent('Ściana 1');
    expect(items[1]).toHaveTextContent('Ściana 1');
  });

  it('reads "why these works" only on a tap and shows the standard, the reasons and the photos (owner 2026-10-31)', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    vi.mocked(api.fetchPortalWhy).mockResolvedValue({
      rooms: [{
        room_name: 'Salon',
        quality_target: 'S2',
        reasons: [{
          surface_name: 'Ściana 1', work_name_key: null, work_name: 'Naprawa rys', reason_key: 'risk.crack_risk_basic.title', inspected_on: '2026-10-30',
          photos: [{ thumb_url: 'https://files.example/t1', url: 'https://files.example/d1', width: 800, height: 600 }],
        }],
      }],
    });
    show();
    const button = await screen.findByLabelText('client-why');
    expect(api.fetchPortalWhy).not.toHaveBeenCalled();
    fireEvent.click(button);
    const panel = await screen.findByLabelText('client-why-panel');
    expect(api.fetchPortalWhy).toHaveBeenCalledWith(TOKEN);
    expect(panel).toHaveTextContent('Standard wykończenia: S2 — Standard malarski');
    expect(panel).toHaveTextContent('Ściana 1: Naprawa rys');
    expect(panel).toHaveTextContent('oględziny 30.10.2026');
    expect(screen.getByLabelText('client-why-photo-0-0-0')).toHaveAttribute('href', 'https://files.example/d1');
    expect(screen.getByLabelText('client-why-photo-0-0-0')).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('offers the name of the client in the form and puts the materials in a group of their own (UX walk)', async () => {
    const lines = [
      ...ESTIMATE().lines,
      { position: 4, room_name: null, surface_name: null, description: 'Klej do płytek', unit: 'PCS', quantity: '3.000', unit_price: '40.00', amount: '120.00', scope: 'MATERIAL' },
      { position: 5, room_name: null, surface_name: null, description: 'Sprzątanie', unit: 'FLAT', quantity: '1.000', unit_price: '50.00', amount: '50.00', scope: 'LABOR' },
    ];
    vi.mocked(api.fetchPortalPage).mockResolvedValue(
      PAGE({ project: { ...PAGE().project, client_name: 'Anna Nowak' }, estimate: ESTIMATE({ lines }) }),
    );
    show();
    const headings = (await screen.findAllByRole('heading', { level: 2 })).map((h) => h.textContent);
    expect(headings).toEqual(expect.arrayContaining(['Pozostałe prace', 'Materiały']));
    expect(headings.indexOf('Materiały')).toBeGreaterThan(headings.indexOf('Pozostałe prace'));
    await choose();
    expect(screen.getByLabelText('client-estimate-name')).toHaveValue('Anna Nowak');
  });

  it('says that an estimate approved in the contract needs no approval, and shows no form', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ estimate: ESTIMATE({ status: 'ACCEPTED', accept_statement: null, consent: null }) }));
    show();
    expect(await screen.findByLabelText('client-estimate-approved-by-contract')).toHaveTextContent('już zatwierdzona w umowie');
    expect(screen.queryByLabelText('client-estimate-form')).toBeNull();
    expect(screen.queryByLabelText('client-estimate-accepted')).toBeNull();
  });

  it('shows the binding Polish text under a translation', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(
      PAGE({ lang: 'en', estimate: ESTIMATE({ accept_statement: { pl: 'Zapoznałem/am się z wyceną.', text: 'I have read the estimate.' } }) }),
    );
    show();
    await choose();
    expect(await screen.findByLabelText('client-estimate-statement')).toHaveTextContent('I have read the estimate.');
    expect(screen.getByLabelText('client-estimate')).toHaveTextContent('Zapoznałem/am się z wyceną.');
  });
});

describe('declining the estimate', () => {
  it('offers the two ways first, shows the words of a refusal with a field for the reason, and sends the refusal', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    const declined = PAGE({
      estimate: ESTIMATE({
        accept_statement: null, decline_statement: null,
        consent: { kind: 'ESTIMATE_DECLINED', signer_name: 'Jan Kowalski', comment: 'Za drogo', created_at: '2026-10-26T11:00:00Z' },
      }),
    });
    vi.mocked(api.decidePortalEstimate).mockResolvedValue(declined);
    show();
    expect(await screen.findByLabelText('client-estimate-agree')).toHaveTextContent('Zatwierdzam wycenę');
    expect(screen.getByLabelText('client-estimate-decline')).toHaveTextContent('Nie zatwierdzam wyceny');
    expect(screen.queryByLabelText('client-estimate-form')).toBeNull();
    fireEvent.click(screen.getByLabelText('client-estimate-decline'));
    expect(screen.getByLabelText('client-estimate-statement')).toHaveTextContent('Nie zatwierdzam wyceny nr 1');
    expect(screen.getByLabelText('client-estimate-comment')).toHaveAttribute('maxlength', '500');
    fireEvent.change(screen.getByLabelText('client-estimate-name'), { target: { value: 'Jan Kowalski' } });
    fireEvent.change(screen.getByLabelText('client-estimate-comment'), { target: { value: 'Za drogo' } });
    fireEvent.click(screen.getByLabelText('client-estimate-agree'));
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    await waitFor(() =>
      expect(api.decidePortalEstimate).toHaveBeenCalledWith(TOKEN, 'pl', {
        estimate_id: 'e1', version: 1, hash: 'h'.repeat(64), decision: 'DECLINE', signer_name: 'Jan Kowalski', agree: true, comment: 'Za drogo',
      }),
    );
    const card = await screen.findByLabelText('client-estimate-declined');
    expect(card).toHaveTextContent('Wycena odrzucona');
    expect(card).toHaveTextContent('Twoja uwaga: Za drogo');
    expect(card).toHaveTextContent('Poczekaj na nową wersję');
    expect(screen.queryByLabelText('client-estimate-accepted')).toBeNull();
  });

  it('has no field for a reason when the client approves, and sends no reason', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    vi.mocked(api.decidePortalEstimate).mockResolvedValue(PAGE());
    show();
    await choose();
    expect(screen.queryByLabelText('client-estimate-comment')).toBeNull();
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    await waitFor(() => expect(api.decidePortalEstimate).toHaveBeenCalled());
    expect(vi.mocked(api.decidePortalEstimate).mock.calls[0][2]).toMatchObject({ decision: 'ACCEPT', comment: null });
  });

  it('does not carry a typed reason over to an approval after the client changes their mind', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    vi.mocked(api.decidePortalEstimate).mockResolvedValue(PAGE());
    show();
    await choose('client-estimate-decline');
    fireEvent.change(screen.getByLabelText('client-estimate-comment'), { target: { value: 'Za drogo' } });
    fireEvent.click(screen.getByLabelText('client-estimate-back'));
    await choose();
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    await waitFor(() => expect(api.decidePortalEstimate).toHaveBeenCalled());
    expect(vi.mocked(api.decidePortalEstimate).mock.calls[0][2]).toMatchObject({ decision: 'ACCEPT', comment: null });
  });

  it('says in words that a reason is too long or the estimate is approved already', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    vi.mocked(api.decidePortalEstimate).mockRejectedValueOnce(new ApiError('x', 422, 'COMMENT_TOO_LONG')).mockRejectedValueOnce(new ApiError('x', 409, 'ESTIMATE_ALREADY_APPROVED'));
    show();
    await choose('client-estimate-decline');
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Powód jest za długi');
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('już zatwierdzona w umowie'));
  });

  it('shows the reason of a refused proposal and gives its refusal a field for the reason', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ proposals: [PROPOSAL()] }));
    vi.mocked(api.decidePortalProposal).mockResolvedValue(
      PAGE({
        proposals: [PROPOSAL({ status: 'DECLINED', accept_statement: null, decline_statement: null, consent: { kind: 'PROPOSAL_DECLINED', signer_name: 'Jan Kowalski', comment: 'Nie potrzebuję', created_at: '2026-10-26T12:00:00Z' } })],
      }),
    );
    show();
    fireEvent.click(await screen.findByLabelText('client-proposal-agree-p1'));
    expect(screen.queryByLabelText('client-decide-p1-comment')).toBeNull();
    fireEvent.click(screen.getByLabelText('client-decide-p1-back'));
    fireEvent.click(screen.getByLabelText('client-proposal-decline-p1'));
    fireEvent.change(screen.getByLabelText('client-decide-p1-name'), { target: { value: 'Jan Kowalski' } });
    fireEvent.change(screen.getByLabelText('client-decide-p1-comment'), { target: { value: 'Nie potrzebuję' } });
    fireEvent.click(screen.getByLabelText('client-decide-p1-agree'));
    fireEvent.click(screen.getByLabelText('client-decide-p1-submit'));
    await waitFor(() =>
      expect(api.decidePortalProposal).toHaveBeenCalledWith(TOKEN, 'p1', 'pl', { decision: 'DECLINE', hash: 'p'.repeat(64), signer_name: 'Jan Kowalski', agree: true, comment: 'Nie potrzebuję' }),
    );
    expect(await screen.findByLabelText('client-proposal-decided-p1')).toHaveTextContent('Twoja uwaga: Nie potrzebuję');
  });
});

describe('the proposals of extra work', () => {
  it('lets the client choose, shows the words of that choice and sends the decision', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ proposals: [PROPOSAL()] }));
    const after = PAGE({
      proposals: [PROPOSAL({ status: 'DECLINED', accept_statement: null, decline_statement: null, consent: { kind: 'PROPOSAL_DECLINED', signer_name: 'Jan Kowalski', comment: null, created_at: '2026-10-26T12:00:00Z' } })],
    });
    vi.mocked(api.decidePortalProposal).mockResolvedValue(after);
    show();
    const card = await screen.findByLabelText('client-proposal-p1');
    expect(card).toHaveTextContent('450,50 PLN');
    expect(card).toHaveTextContent('Termin przesunięty o 2 dni');
    fireEvent.click(screen.getByLabelText('client-proposal-decline-p1'));
    expect(screen.getByLabelText('client-decide-p1-statement')).toHaveTextContent('Nie akceptuję');
    fireEvent.change(screen.getByLabelText('client-decide-p1-name'), { target: { value: 'Jan Kowalski' } });
    fireEvent.click(screen.getByLabelText('client-decide-p1-agree'));
    fireEvent.click(screen.getByLabelText('client-decide-p1-submit'));
    await waitFor(() =>
      expect(api.decidePortalProposal).toHaveBeenCalledWith(TOKEN, 'p1', 'pl', { decision: 'DECLINE', hash: 'p'.repeat(64), signer_name: 'Jan Kowalski', agree: true, comment: null }),
    );
    expect(await screen.findByLabelText('client-proposal-decided-p1')).toHaveTextContent('Odrzucono');
  });

  it('shows the words of agreeing when the client agrees, and can step back', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ proposals: [PROPOSAL()] }));
    show();
    fireEvent.click(await screen.findByLabelText('client-proposal-agree-p1'));
    expect(screen.getByLabelText('client-decide-p1-statement')).toHaveTextContent('Zatwierdzam pracę');
    fireEvent.click(screen.getByLabelText('client-decide-p1-back'));
    expect(screen.getByLabelText('client-proposal-agree-p1')).toBeInTheDocument();
    expect(api.decidePortalProposal).not.toHaveBeenCalled();
  });

  it('lists the open proposals first and shows a decided one without buttons', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(
      PAGE({
        proposals: [
          PROPOSAL({ id: 'p1', title: 'Stara', status: 'ACCEPTED', accept_statement: null, decline_statement: null, consent: { kind: 'PROPOSAL_ACCEPTED', signer_name: 'Jan Kowalski', comment: null, created_at: '2026-10-26T12:00:00Z' } }),
          PROPOSAL({ id: 'p2', sequence: 2, title: 'Nowa' }),
        ],
      }),
    );
    show();
    const cards = await screen.findAllByRole('article');
    expect(cards[0]).toHaveTextContent('Nowa');
    expect(cards[1]).toHaveTextContent('Stara');
    expect(within(cards[1]).getByLabelText('client-proposal-decided-p1')).toHaveTextContent('Zatwierdzono');
    expect(within(cards[1]).queryByLabelText('client-proposal-agree-p1')).toBeNull();
  });

  it('shows no block of proposals when there are none', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    show();
    await screen.findByLabelText('client-estimate');
    expect(screen.queryByLabelText('client-proposals')).toBeNull();
  });
});

describe('a link that does not work', () => {
  it.each([
    [404, 'client-not_found', 'Nieprawidłowy link'],
    [410, 'client-inactive', 'Link wygasł lub został odwołany'],
    [429, 'client-limited', 'Zbyt wiele prób'],
  ])('answers %s with its own screen and no data', async (status, label, title) => {
    vi.mocked(api.fetchPortalPage).mockRejectedValue(new ApiError('x', status));
    show();
    expect(await screen.findByLabelText(label)).toHaveTextContent(title);
    expect(screen.queryByLabelText('client-estimate')).toBeNull();
    expect(screen.queryByLabelText('client-contractor')).toBeNull();
  });

  it('speaks the language of the browser while the language of the link is not known yet', async () => {
    vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('uk-UA');
    vi.mocked(api.fetchPortalPage).mockRejectedValue(new ApiError('x', 410));
    show();
    expect(await screen.findByLabelText('client-inactive')).toHaveTextContent('Термін посилання минув або його відкликано');
  });

  it('offers a retry when the page could not be loaded', async () => {
    vi.mocked(api.fetchPortalPage).mockRejectedValueOnce(new ApiError('network', 0, 'NETWORK')).mockResolvedValueOnce(PAGE());
    show();
    fireEvent.click(await screen.findByLabelText('client-retry'));
    expect(await screen.findByLabelText('client-estimate')).toBeInTheDocument();
  });

  it('does not even ask the server without a secret', async () => {
    show('');
    expect(await screen.findByLabelText('client-not_found')).toBeInTheDocument();
    expect(api.fetchPortalPage).not.toHaveBeenCalled();
  });

  it('shows the inactive screen when the link dies during a press', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    vi.mocked(api.decidePortalEstimate).mockRejectedValue(new ApiError('x', 410, 'LINK_INACTIVE'));
    show();
    await choose();
    fireEvent.click(screen.getByLabelText('client-estimate-submit'));
    expect(await screen.findByLabelText('client-inactive')).toBeInTheDocument();
  });
});

describe('the language', () => {
  it('starts in the language of the link, speaks all four and asks the server for the matching words', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ lang: 'uk' }));
    show();
    await screen.findByLabelText('client-estimate');
    expect(screen.getByLabelText('client-estimate')).toHaveTextContent('Кошторис № 1');
    expect(screen.getByLabelText('client-language')).toHaveValue('uk');
    for (const [code, words] of [['en', 'Estimate no. 1'], ['ru', 'Смета № 1'], ['pl', 'Wycena nr 1']] as const) {
      vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ lang: code }));
      fireEvent.change(screen.getByLabelText('client-language'), { target: { value: code } });
      await waitFor(() => expect(screen.getByLabelText('client-estimate')).toHaveTextContent(words));
      expect(api.fetchPortalPage).toHaveBeenLastCalledWith(TOKEN, code);
    }
  });

  it('keeps the page and the typed name while the words change', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE());
    show();
    await choose();
    fireEvent.change(screen.getByLabelText('client-estimate-name'), { target: { value: 'Jan' } });
    fireEvent.change(screen.getByLabelText('client-language'), { target: { value: 'en' } });
    expect(screen.getByLabelText('client-estimate')).toBeInTheDocument();
    expect(screen.getByLabelText('client-estimate-name')).toHaveValue('Jan');
  });
});

describe('the phone', () => {
  it('has controls of at least 48 px and nothing that forces a sideways scroll', async () => {
    vi.mocked(api.fetchPortalPage).mockResolvedValue(PAGE({ proposals: [PROPOSAL()] }));
    show();
    await screen.findByLabelText('client-estimate');
    for (const label of ['client-estimate-agree', 'client-estimate-decline', 'client-proposal-agree-p1', 'client-proposal-decline-p1']) {
      expect(screen.getByLabelText(label).className).toContain('min-h-12');
    }
    expect(screen.getByLabelText('client-page').className).toContain('overflow-x-hidden');
    expect(screen.getByLabelText('client-page').className).toContain('max-w-xl');
    expect(screen.getByLabelText('client-language').className).toContain('min-h-11');
  });
});
