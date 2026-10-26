/** V2-14 — the owner's screen of the links for the electrician and the plumber: make, copy, send, extend, revoke, the word to the craftsman, his answers. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import * as api from '../api/tradeLinks';
import { I18nProvider } from '../hooks/useI18n';
import type { TradeAnswersResponse, TradeLinkInfo } from '../types/tradeLink';
import { ProjectTradeLinks } from './ProjectTradeLinks';

vi.mock('../api/tradeLinks', () => ({
  fetchTradeLinks: vi.fn(),
  createTradeLink: vi.fn(),
  changeTradeLinkNote: vi.fn(),
  extendTradeLink: vi.fn(),
  revokeTradeLink: vi.fn(),
  fetchTradeAnswers: vi.fn(),
}));

const TOKEN = 'abcDEF0123456789abcDEF0123456789abcDEF01234';
const LINK = (overrides: Partial<TradeLinkInfo> = {}): TradeLinkInfo => ({
  trade: 'ELECTRIC', language: 'pl', owner_note: null, created_at: '2026-10-26T10:00:00Z', expires_at: '2026-11-25T10:00:00Z', last_viewed_at: null, view_count: 0,
  expired: false, answers_count: 0, submissions_count: 0, last_submitted_at: null, ...overrides,
});
const ANSWERS = (overrides: Partial<TradeAnswersResponse> = {}): TradeAnswersResponse => ({
  trade: 'ELECTRIC', positions: [], rooms: [], submissions: [], ...overrides,
});

function show() {
  render(
    <I18nProvider>
      <ProjectTradeLinks projectId="proj1" />
    </I18nProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  delete window.Telegram;
  vi.clearAllMocks();
  vi.mocked(api.fetchTradeLinks).mockResolvedValue({ electric: null, plumbing: null });
  vi.mocked(api.fetchTradeAnswers).mockResolvedValue(ANSWERS());
});

describe('the cards', () => {
  it('shows one card for the electrician and one for the plumber, each with its own button', async () => {
    show();
    const electric = await screen.findByLabelText('trade-card-ELECTRIC');
    const plumbing = screen.getByLabelText('trade-card-PLUMBING');
    expect(within(electric).getByText('Elektryk')).toBeInTheDocument();
    expect(within(plumbing).getByText('Hydraulik')).toBeInTheDocument();
    expect(screen.getByLabelText('trade-link-create-ELECTRIC')).toBeInTheDocument();
    expect(screen.getByLabelText('trade-link-create-PLUMBING')).toBeInTheDocument();
  });

  it('makes a link for the plumber only, with the language and the word to the craftsman, and shows the address once', async () => {
    vi.mocked(api.createTradeLink).mockResolvedValue({ link: LINK({ trade: 'PLUMBING', language: 'ru', owner_note: 'Слив у окна' }), token: TOKEN });
    show();
    fireEvent.change(await screen.findByLabelText('trade-link-language-PLUMBING'), { target: { value: 'ru' } });
    fireEvent.change(screen.getByLabelText('trade-link-note-PLUMBING'), { target: { value: 'Слив у окна' } });
    fireEvent.click(screen.getByLabelText('trade-link-create-PLUMBING'));
    await waitFor(() => expect(api.createTradeLink).toHaveBeenCalledWith('proj1', 'PLUMBING', 'ru', 'Слив у окна'));
    expect(await screen.findByLabelText('trade-link-url-PLUMBING')).toHaveValue(`${window.location.origin}/m#${TOKEN}`);
    expect(screen.getByLabelText('trade-link-term-PLUMBING')).toHaveTextContent('Link działa do');
    expect(screen.getByLabelText('trade-link-create-ELECTRIC')).toBeInTheDocument();
  });

  it('shows a link made earlier without its address, with the views and what was sent', async () => {
    vi.mocked(api.fetchTradeLinks).mockResolvedValue({
      electric: LINK({ view_count: 3, last_viewed_at: '2026-10-27T09:30:00Z', submissions_count: 2, last_submitted_at: '2026-10-27T10:00:00Z' }),
      plumbing: null,
    });
    show();
    expect(await screen.findByLabelText('trade-link-hidden-ELECTRIC')).toBeInTheDocument();
    expect(screen.queryByLabelText('trade-link-url-ELECTRIC')).toBeNull();
    expect(screen.getByLabelText('trade-link-views-ELECTRIC')).toHaveTextContent('Otwarty 3 razy');
    expect(screen.getByLabelText('trade-link-sent-ELECTRIC')).toHaveTextContent('Odpowiedzi wysłano 2 razy');
  });

  it('marks an expired link', async () => {
    vi.mocked(api.fetchTradeLinks).mockResolvedValue({ electric: LINK({ expired: true }), plumbing: null });
    show();
    expect(await screen.findByLabelText('trade-link-term-ELECTRIC')).toHaveTextContent('Link wygasł');
  });
});

describe('sending the address', () => {
  it('opens the share of Telegram with the address and a text naming the trade', async () => {
    const open = vi.fn();
    window.Telegram = { WebApp: { openTelegramLink: open } } as unknown as typeof window.Telegram;
    vi.mocked(api.createTradeLink).mockResolvedValue({ link: LINK(), token: TOKEN });
    show();
    fireEvent.click(await screen.findByLabelText('trade-link-create-ELECTRIC'));
    fireEvent.click(await screen.findByLabelText('trade-link-share-ELECTRIC'));
    expect(open).toHaveBeenCalledTimes(1);
    const sent = decodeURIComponent(open.mock.calls[0][0] as string);
    expect(sent).toContain(`${window.location.origin}/m#${TOKEN}`);
    expect(sent).toContain('Elektryk');
  });
});

describe('extend, new link, revoke, the word', () => {
  beforeEach(() => {
    vi.mocked(api.fetchTradeLinks).mockResolvedValue({ electric: LINK({ owner_note: 'Stara uwaga' }), plumbing: null });
  });

  it('extends the link', async () => {
    vi.mocked(api.extendTradeLink).mockResolvedValue(LINK({ expires_at: '2026-12-01T10:00:00Z' }));
    show();
    fireEvent.click(await screen.findByLabelText('trade-link-extend-ELECTRIC'));
    await waitFor(() => expect(api.extendTradeLink).toHaveBeenCalledWith('proj1', 'ELECTRIC'));
    expect(await screen.findByText('Link przedłużony')).toBeInTheDocument();
  });

  it('asks before it makes a new link and before it revokes', async () => {
    vi.mocked(api.revokeTradeLink).mockResolvedValue(undefined);
    show();
    fireEvent.click(await screen.findByLabelText('trade-link-new-ELECTRIC'));
    expect(screen.getByText('Poprzedni link przestanie działać. Utworzyć nowy?')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('trade-link-new-cancel-ELECTRIC'));
    expect(api.createTradeLink).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('trade-link-revoke-ELECTRIC'));
    fireEvent.click(screen.getByLabelText('trade-link-revoke-yes-ELECTRIC'));
    await waitFor(() => expect(api.revokeTradeLink).toHaveBeenCalledWith('proj1', 'ELECTRIC'));
    expect(await screen.findByLabelText('trade-link-create-ELECTRIC')).toBeInTheDocument();
  });

  it('saves a changed word to the craftsman and only when it changed', async () => {
    vi.mocked(api.changeTradeLinkNote).mockResolvedValue(LINK({ owner_note: 'Nowa uwaga' }));
    show();
    const save = await screen.findByLabelText('trade-link-note-save-ELECTRIC');
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('trade-link-note-ELECTRIC'), { target: { value: 'Nowa uwaga' } });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    await waitFor(() => expect(api.changeTradeLinkNote).toHaveBeenCalledWith('proj1', 'ELECTRIC', 'Nowa uwaga'));
    expect(await screen.findByText('Komentarz zapisany')).toBeInTheDocument();
  });

  it('shows the reason in words when the server refuses', async () => {
    vi.mocked(api.extendTradeLink).mockRejectedValue(new ApiError('x', 409, 'LINK_BUSY'));
    show();
    fireEvent.click(await screen.findByLabelText('trade-link-extend-ELECTRIC'));
    expect(await screen.findByText('Link jest właśnie tworzony. Spróbuj za chwilę.')).toBeInTheDocument();
  });
});

describe('the answers', () => {
  it('shows what the craftsman answered by room, and the journal', async () => {
    vi.mocked(api.fetchTradeLinks).mockResolvedValue({ electric: LINK({ answers_count: 3, submissions_count: 1, last_submitted_at: '2026-10-27T10:00:00Z' }), plumbing: null });
    vi.mocked(api.fetchTradeAnswers).mockResolvedValue(
      ANSWERS({
        rooms: [
          { room_id: 'r1', room_name: 'Salon', updated_at: '2026-10-27T10:00:00Z',
            typical: [{ key: 'SOCKET', unit: 'PCS', quantity: '6.00', note: 'przy TV' }, { key: 'CABLE_ROUTE', unit: 'LM', quantity: '12.50', note: null }],
            own: [{ name: 'Gniazdo siłowe', quantity: '1.00', unit: 'PCS', note: null }] },
          { room_id: 'r2', room_name: 'Pusty', updated_at: null, typical: [], own: [] },
        ],
        submissions: [{ id: 's1', master_name: 'Jan Elektryk', answers_count: 3, created_at: '2026-10-27T10:00:00Z' }],
      }),
    );
    show();
    const answers = await screen.findByLabelText('trade-answers-ELECTRIC');
    expect(within(answers).getByText('Salon')).toBeInTheDocument();
    expect(within(answers).queryByText('Pusty')).toBeNull();
    expect(within(answers).getByText('Gniazdka').closest('li')).toHaveTextContent('Gniazdka: 6 szt.');
    expect(within(answers).getByText('Trasa kabli').closest('li')).toHaveTextContent('Trasa kabli: 12,50 m.b.');
    expect(within(answers).getByText('przy TV')).toBeInTheDocument();
    expect(within(answers).getByText('Gniazdo siłowe').closest('li')).toHaveTextContent('Gniazdo siłowe: 1 szt.');
    expect(within(answers).getByLabelText('trade-journal-ELECTRIC')).toHaveTextContent('Jan Elektryk · pozycji: 3');
  });

  it('says nothing was entered or sent yet', async () => {
    vi.mocked(api.fetchTradeLinks).mockResolvedValue({ electric: LINK(), plumbing: null });
    show();
    expect(await screen.findByLabelText('trade-answers-empty-ELECTRIC')).toBeInTheDocument();
    expect(screen.getByLabelText('trade-journal-empty-ELECTRIC')).toBeInTheDocument();
  });
});

describe('the load', () => {
  it('offers to try again when the links do not load', async () => {
    vi.mocked(api.fetchTradeLinks).mockRejectedValueOnce(new Error('x'));
    show();
    fireEvent.click(await screen.findByLabelText('trade-links-retry'));
    expect(await screen.findByLabelText('trade-card-ELECTRIC')).toBeInTheDocument();
  });
});
