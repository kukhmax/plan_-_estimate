/** V2-8 — the owner's screen of the link for the client: make, copy, send, extend, revoke; the proposals; the journal. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/clientLink';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { ClientConsent, ClientLinkInfo, ClientProposal } from '../types/clientLink';
import { ProjectClientLink } from './ProjectClientLink';

vi.mock('../api/clientLink', () => ({
  fetchClientLink: vi.fn(),
  createClientLink: vi.fn(),
  extendClientLink: vi.fn(),
  revokeClientLink: vi.fn(),
  listClientProposals: vi.fn(),
  createClientProposal: vi.fn(),
  withdrawClientProposal: vi.fn(),
  fetchClientJournal: vi.fn(),
}));

const TOKEN = 'abcDEF0123456789abcDEF0123456789abcDEF01234';
const LINK = (overrides: Partial<ClientLinkInfo> = {}): ClientLinkInfo => ({
  id: 'l1', language: 'pl', created_at: '2026-10-26T10:00:00Z', expires_at: '2026-11-25T10:00:00Z', last_viewed_at: null, view_count: 0, expired: false, ...overrides,
});
const PROPOSAL = (overrides: Partial<ClientProposal> = {}): ClientProposal => ({
  id: 'p1', sequence: 1, title: 'Gruntowanie sufitu', description: 'Dodatkowa warstwa', amount: '450.50', currency: 'PLN', extra_days: 2, status: 'OPEN',
  created_at: '2026-10-26T10:00:00Z', decided_at: null, ...overrides,
});
const CONSENT = (overrides: Partial<ClientConsent> = {}): ClientConsent => ({
  id: 'c1', kind: 'ESTIMATE_ACCEPTED', estimate_id: 'e1', estimate_version: 2, proposal_id: null, subject_hash: 'h'.repeat(64), amount: '3489.66', currency: 'PLN',
  statement: 'Zatwierdzam wycenę nr 2.', statement_lang: 'pl', signer_name: 'Jan Kowalski', created_at: '2026-10-27T09:30:00Z', ...overrides,
});

function show() {
  render(
    <I18nProvider>
      <ProjectClientLink projectId="proj1" />
    </I18nProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  delete window.Telegram;
  vi.clearAllMocks();
  vi.mocked(api.fetchClientLink).mockResolvedValue({ link: null });
  vi.mocked(api.listClientProposals).mockResolvedValue({ items: [], max_proposals: 20 });
  vi.mocked(api.fetchClientJournal).mockResolvedValue({ items: [] });
});

describe('the link', () => {
  it('offers to make a link, in a language of the owner\'s choice, and shows the address once it is made', async () => {
    vi.mocked(api.createClientLink).mockResolvedValue({ link: LINK({ language: 'uk' }), token: TOKEN });
    show();
    fireEvent.change(await screen.findByLabelText('client-link-language'), { target: { value: 'uk' } });
    fireEvent.click(screen.getByLabelText('client-link-create'));
    await waitFor(() => expect(api.createClientLink).toHaveBeenCalledWith('proj1', 'uk'));
    const url = await screen.findByLabelText('client-link-url');
    expect(url).toHaveValue(`${window.location.origin}/c#${TOKEN}`);
    expect(screen.getByLabelText('client-link-term')).toHaveTextContent('Link działa do');
    expect(screen.getByLabelText('client-link-views')).toHaveTextContent('Klient jeszcze nie otworzył linku');
    expect(screen.getByRole('status')).toHaveTextContent('Link utworzony');
  });

  it('never shows the address of a link that was made earlier: only its term and its openings', async () => {
    vi.mocked(api.fetchClientLink).mockResolvedValue({ link: LINK({ view_count: 3, last_viewed_at: '2026-10-27T08:00:00Z' }) });
    show();
    expect(await screen.findByLabelText('client-link-hidden')).toHaveTextContent('Adres jest pokazywany tylko zaraz po utworzeniu');
    expect(screen.queryByLabelText('client-link-url')).toBeNull();
    expect(screen.getByLabelText('client-link-views')).toHaveTextContent('Otwarty 3 razy');
  });

  it('says in red that the link has expired and still lets the owner extend it', async () => {
    vi.mocked(api.fetchClientLink).mockResolvedValue({ link: LINK({ expired: true }) });
    vi.mocked(api.extendClientLink).mockResolvedValue({ link: LINK({ expired: false }) });
    show();
    expect(await screen.findByLabelText('client-link-term')).toHaveTextContent('Link wygasł');
    expect(screen.getByLabelText('client-link-term').className).toContain('text-red-700');
    fireEvent.click(screen.getByLabelText('client-link-extend'));
    await waitFor(() => expect(api.extendClientLink).toHaveBeenCalledWith('proj1'));
    await waitFor(() => expect(screen.getByLabelText('client-link-term')).toHaveTextContent('Link działa do'));
  });

  it('asks twice before it replaces the link and before it revokes it', async () => {
    vi.mocked(api.fetchClientLink).mockResolvedValue({ link: LINK() });
    vi.mocked(api.createClientLink).mockResolvedValue({ link: LINK({ id: 'l2' }), token: TOKEN });
    vi.mocked(api.revokeClientLink).mockResolvedValue(undefined);
    show();
    fireEvent.click(await screen.findByLabelText('client-link-new'));
    expect(screen.getByText('Poprzedni link przestanie działać. Utworzyć nowy?')).toBeInTheDocument();
    expect(api.createClientLink).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('client-link-new-cancel'));
    expect(api.createClientLink).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('client-link-new'));
    fireEvent.click(screen.getByLabelText('client-link-new-yes'));
    await waitFor(() => expect(api.createClientLink).toHaveBeenCalledWith('proj1', 'pl'));
    expect(await screen.findByLabelText('client-link-url')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('client-link-revoke'));
    expect(api.revokeClientLink).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('client-link-revoke-yes'));
    await waitFor(() => expect(api.revokeClientLink).toHaveBeenCalledWith('proj1'));
    expect(await screen.findByLabelText('client-link-create')).toBeInTheDocument();
    expect(screen.queryByLabelText('client-link-url')).toBeNull();
  });

  it('copies the address and says so', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    vi.mocked(api.createClientLink).mockResolvedValue({ link: LINK(), token: TOKEN });
    show();
    fireEvent.click(await screen.findByLabelText('client-link-create'));
    fireEvent.click(await screen.findByLabelText('client-link-copy'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/c#${TOKEN}`));
    expect(await screen.findByText('Skopiowano')).toBeInTheDocument();
  });

  it('sends the address through the share dialog of Telegram inside Telegram', async () => {
    const openTelegramLink = vi.fn();
    window.Telegram = { WebApp: { openTelegramLink } } as unknown as typeof window.Telegram;
    vi.mocked(api.createClientLink).mockResolvedValue({ link: LINK(), token: TOKEN });
    show();
    fireEvent.click(await screen.findByLabelText('client-link-create'));
    fireEvent.click(await screen.findByLabelText('client-link-share'));
    expect(openTelegramLink).toHaveBeenCalledTimes(1);
    const shared = String(openTelegramLink.mock.calls[0][0]);
    expect(shared.startsWith('https://t.me/share/url?url=')).toBe(true);
    expect(decodeURIComponent(shared)).toContain(`/c#${TOKEN}`);
  });

  it('says that the link could not be made', async () => {
    vi.mocked(api.createClientLink).mockRejectedValue(new ApiError('x', 409, 'LINK_BUSY'));
    show();
    fireEvent.click(await screen.findByLabelText('client-link-create'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Link jest właśnie tworzony');
  });
});

describe('the proposals', () => {
  it('writes a proposal and puts it first', async () => {
    vi.mocked(api.listClientProposals).mockResolvedValue({ items: [PROPOSAL({ id: 'old', title: 'Stara', status: 'DECLINED' })], max_proposals: 20 });
    vi.mocked(api.createClientProposal).mockResolvedValue(PROPOSAL({ id: 'new', title: 'Nowa praca' }));
    show();
    fireEvent.click(await screen.findByLabelText('client-proposal-add'));
    fireEvent.change(screen.getByLabelText('client-proposal-title'), { target: { value: 'Nowa praca' } });
    fireEvent.change(screen.getByLabelText('client-proposal-amount'), { target: { value: '450,50' } });
    fireEvent.change(screen.getByLabelText('client-proposal-days'), { target: { value: '2x' } });
    fireEvent.click(screen.getByLabelText('client-proposal-save'));
    await waitFor(() =>
      expect(api.createClientProposal).toHaveBeenCalledWith('proj1', { title: 'Nowa praca', description: null, amount: '450.50', extra_days: 2 }),
    );
    const items = within(await screen.findByLabelText('client-proposals-list')).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Nowa praca');
    expect(items[1]).toHaveTextContent('Stara');
    expect(items[1]).toHaveTextContent('Klient odrzucił');
  });

  it('keeps the save button off until there is a name and an amount, and uses the right keyboards', async () => {
    show();
    fireEvent.click(await screen.findByLabelText('client-proposal-add'));
    expect(screen.getByLabelText('client-proposal-save')).toBeDisabled();
    expect(screen.getByLabelText('client-proposal-amount')).toHaveAttribute('inputmode', 'decimal');
    expect(screen.getByLabelText('client-proposal-days')).toHaveAttribute('inputmode', 'numeric');
    fireEvent.change(screen.getByLabelText('client-proposal-title'), { target: { value: 'X' } });
    expect(screen.getByLabelText('client-proposal-save')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('client-proposal-amount'), { target: { value: '10' } });
    expect(screen.getByLabelText('client-proposal-save')).toBeEnabled();
  });

  it('says in words what the server refused', async () => {
    vi.mocked(api.createClientProposal).mockRejectedValue(new ApiError('x', 422, 'TOO_MANY_PROPOSALS'));
    show();
    fireEvent.click(await screen.findByLabelText('client-proposal-add'));
    fireEvent.change(screen.getByLabelText('client-proposal-title'), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText('client-proposal-amount'), { target: { value: '10' } });
    fireEvent.click(screen.getByLabelText('client-proposal-save'));
    expect(await screen.findByRole('alert')).toHaveTextContent('limit 20 propozycji');
  });

  it('withdraws an open proposal after a second tap, and only an open one', async () => {
    vi.mocked(api.listClientProposals).mockResolvedValue({
      items: [PROPOSAL(), PROPOSAL({ id: 'p2', sequence: 2, title: 'Zgoda', status: 'ACCEPTED' })],
      max_proposals: 20,
    });
    vi.mocked(api.withdrawClientProposal).mockResolvedValue(PROPOSAL({ status: 'WITHDRAWN' }));
    show();
    fireEvent.click(await screen.findByLabelText('client-proposal-withdraw-p1'));
    expect(screen.queryByLabelText('client-proposal-withdraw-p2')).toBeNull();
    expect(api.withdrawClientProposal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('client-proposal-withdraw-yes-p1'));
    await waitFor(() => expect(api.withdrawClientProposal).toHaveBeenCalledWith('proj1', 'p1'));
    expect(await screen.findByText('Wycofana')).toBeInTheDocument();
    expect(screen.queryByLabelText('client-proposal-withdraw-p1')).toBeNull();
  });

  it('says that there are no proposals yet', async () => {
    show();
    expect(await screen.findByLabelText('client-proposals-empty')).toHaveTextContent('Brak propozycji');
  });
});

describe('the journal', () => {
  it('says that nothing was decided yet', async () => {
    show();
    expect(await screen.findByLabelText('client-journal-empty')).toBeInTheDocument();
  });

  it('lists what the client agreed to with the name, the sum and the exact words', async () => {
    vi.mocked(api.fetchClientJournal).mockResolvedValue({
      items: [
        CONSENT(),
        CONSENT({ id: 'c2', kind: 'PROPOSAL_DECLINED', estimate_id: null, estimate_version: null, proposal_id: 'p1', amount: '450.50', signer_name: 'Ewa Nowak', statement: 'Nie akceptuję pracy.' }),
      ],
    });
    show();
    const first = await screen.findByLabelText('client-journal-c1');
    expect(first).toHaveTextContent('Wycena zatwierdzona');
    expect(first).toHaveTextContent('3489,66 PLN');
    expect(first).toHaveTextContent('wersja 2');
    expect(first).toHaveTextContent('Podpisał(a): Jan Kowalski');
    expect(first).toHaveTextContent('Zatwierdzam wycenę nr 2.');
    const second = screen.getByLabelText('client-journal-c2');
    expect(second).toHaveTextContent('Odrzucona praca dodatkowa');
    expect(second).not.toHaveTextContent('wersja');
  });
});

describe('loading and the phone', () => {
  it('offers a retry when the screen could not be loaded', async () => {
    vi.mocked(api.fetchClientLink).mockRejectedValueOnce(new Error('down'));
    show();
    fireEvent.click(await screen.findByLabelText('client-link-retry'));
    expect(await screen.findByLabelText('client-link-create')).toBeInTheDocument();
  });

  it('has full-width controls of at least 44 px', async () => {
    vi.mocked(api.fetchClientLink).mockResolvedValue({ link: LINK() });
    show();
    for (const label of ['client-link-extend', 'client-link-new', 'client-link-revoke', 'client-proposal-add']) {
      const el = await screen.findByLabelText(label);
      expect(el.className).toContain('min-h-11');
      expect(el.className).toContain('w-full');
    }
  });

  it('speaks the four languages of the application', async () => {
    for (const [lang, words] of [['pl', 'Dodaj propozycję'], ['ru', 'Добавить предложение'], ['uk', 'Додати пропозицію'], ['en', 'Add a proposal']] as const) {
      localStorage.setItem('locale', lang);
      const { unmount } = render(
        <I18nProvider>
          <ProjectClientLink projectId="proj1" />
        </I18nProvider>,
      );
      expect(await screen.findByLabelText('client-proposal-add')).toHaveTextContent(words);
      unmount();
    }
  });
});
