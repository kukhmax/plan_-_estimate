/** V2-14 — the open page of the electrician and the plumber: the rooms, the checklist, own positions, saving, sending, the states of a link that does not work. */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import * as api from '../api/tradePortal';
import { I18nProvider } from '../hooks/useI18n';
import type { PortalTradePage } from '../types/tradeLink';
import { isMasterPagePath, MasterPage } from './MasterPage';

vi.mock('../api/tradePortal', () => ({
  fetchTradePage: vi.fn(),
  saveTradeRoom: vi.fn(),
  submitTradeAnswers: vi.fn(),
}));

const TOKEN = 'M'.repeat(43);
const ELECTRIC_POSITIONS = [
  { key: 'SOCKET', unit: 'PCS' as const },
  { key: 'SWITCH', unit: 'PCS' as const },
  { key: 'LIGHT_POINT', unit: 'PCS' as const },
  { key: 'CIRCUIT', unit: 'PCS' as const },
  { key: 'CABLE_ROUTE', unit: 'LM' as const },
];
const PAGE = (overrides: Partial<PortalTradePage> = {}): PortalTradePage => ({
  link: { expires_at: '2026-11-25T10:00:00Z', language: 'pl' },
  lang: 'pl',
  trade: 'ELECTRIC',
  contractor: { name: 'Vvv Remonty', phone: '+48600100200', email: null, city: 'Kraków' },
  project_name: 'Mieszkanie 50 m²',
  owner_note: null,
  positions: ELECTRIC_POSITIONS,
  rooms: [
    { id: 'r1', name: 'Salon', length: '5.00', width: '4.00', height: '2.60', floor_area: '20.00', perimeter: '18.00', typical: [], own: [], photos: [], route_map: [] },
    { id: 'r2', name: 'Łazienka', length: null, width: null, height: null, floor_area: null, perimeter: null, typical: [], own: [], photos: [], route_map: [] },
  ],
  submissions_count: 0,
  last_submitted_at: null,
  photos_expire_at: null,
  ...overrides,
});

function show(token = TOKEN) {
  render(
    <I18nProvider persist={false}>
      <MasterPage token={token} />
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
  it('knows the path of the page', () => {
    expect(isMasterPagePath('/m')).toBe(true);
    expect(isMasterPagePath('/m/')).toBe(true);
    expect(isMasterPagePath('/')).toBe(false);
    expect(isMasterPagePath('/c')).toBe(false);
    expect(isMasterPagePath('/m/abc')).toBe(false);
    expect(isMasterPagePath('/materials')).toBe(false);
  });
});

describe('the page', () => {
  it('shows the trade, the object, the contractor, the owner note and the rooms with their sizes — and no money', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE({ owner_note: 'Gniazda przy blacie na 110 cm' }));
    show();
    expect(await screen.findByText('Elektryk — punkty i trasy')).toBeInTheDocument();
    expect(screen.getByText('Mieszkanie 50 m²')).toBeInTheDocument();
    expect(screen.getByText('Vvv Remonty')).toBeInTheDocument();
    expect(screen.getByLabelText('master-call')).toHaveAttribute('href', 'tel:+48600100200');
    expect(screen.getByLabelText('master-owner-note')).toHaveTextContent('Gniazda przy blacie na 110 cm');
    expect(screen.getByText('Salon')).toBeInTheDocument();
    expect(screen.getByText(/5,00 × 4,00 m × h 2,60 m/)).toBeInTheDocument();
    expect(screen.getByLabelText('master-qty-r1-SOCKET')).toBeInTheDocument();
    expect(screen.getByLabelText('master-qty-r2-CABLE_ROUTE')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/zł|PLN/);
    expect(api.fetchTradePage).toHaveBeenCalledWith(TOKEN, null);
  });

  it('asks the browser not to index and not to send a referrer', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    show();
    await screen.findByText('Salon');
    expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow');
    expect(document.head.querySelector('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer');
  });

  it('uses the keyboard of numbers for pieces and of decimals for metres, and keeps only digits in pieces', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    show();
    const pieces = await screen.findByLabelText('master-qty-r1-SOCKET');
    expect(pieces).toHaveAttribute('inputmode', 'numeric');
    expect(screen.getByLabelText('master-qty-r1-CABLE_ROUTE')).toHaveAttribute('inputmode', 'decimal');
    fireEvent.change(pieces, { target: { value: '4,5' } });
    expect(pieces).toHaveValue('45');
  });

  it('shows the words of the owner language and lets the craftsman change it', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE({ lang: 'ru' }));
    show();
    expect(await screen.findByText('Электрик — точки и трассы')).toBeInTheDocument();
    expect(screen.getAllByText('Розетки').length).toBeGreaterThan(0);
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE({ lang: 'en' }));
    fireEvent.change(screen.getByLabelText('master-language'), { target: { value: 'en' } });
    expect(await screen.findByText('Electrician — points and routes')).toBeInTheDocument();
    expect(api.fetchTradePage).toHaveBeenLastCalledWith(TOKEN, 'en');
  });

  it('names the plumber positions for the plumber link', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(
      PAGE({ trade: 'PLUMBING', positions: [{ key: 'WATER_POINT', unit: 'PCS' }, { key: 'PIPE_ROUTE', unit: 'LM' }] }),
    );
    show();
    expect(await screen.findByText('Hydraulik — punkty i trasy')).toBeInTheDocument();
    expect(screen.getAllByText('Trasa rur').length).toBe(2);
    expect(screen.queryByLabelText('master-qty-r1-SOCKET')).toBeNull();
  });

  it('says there are no rooms and offers nothing to send', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE({ rooms: [] }));
    show();
    expect(await screen.findByLabelText('master-no-rooms')).toBeInTheDocument();
    expect(screen.queryByLabelText('master-submit-form')).toBeNull();
  });

  it('shows the answers that are already there, without trailing zeros', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(
      PAGE({
        rooms: [
          {
            id: 'r1', name: 'Salon', length: null, width: null, height: null, floor_area: null, perimeter: null,
            typical: [{ key: 'SOCKET', unit: 'PCS', quantity: '6.00', note: 'przy TV' }, { key: 'CABLE_ROUTE', unit: 'LM', quantity: '12.50', note: null }],
            own: [{ name: 'Gniazdo siłowe', quantity: '1.00', unit: 'PCS', note: null }],
            photos: [], route_map: [],
          },
        ],
        submissions_count: 1,
        last_submitted_at: '2026-10-27T09:30:00Z',
      }),
    );
    show();
    expect(await screen.findByLabelText('master-qty-r1-SOCKET')).toHaveValue('6');
    expect(screen.getByLabelText('master-qty-r1-CABLE_ROUTE')).toHaveValue('12.5');
    expect(screen.getByLabelText('master-note-r1-SOCKET')).toHaveValue('przy TV');
    expect(screen.getByLabelText('master-own-name-r1-0')).toHaveValue('Gniazdo siłowe');
    expect(screen.getByLabelText('master-last-sent')).toBeInTheDocument();
  });
});

describe('the photos', () => {
  it('shows the photos of a room and the route map of the trade inside its card', async () => {
    const photo = { id: 'p1', thumb_url: 'https://f.example/p1/t', url: 'https://f.example/p1/d', width: 100, height: 100, place: 'Ściana A', markers: [{ x: 0.5, y: 0.5, label: null, utility: 'CABLE', depth_cm: null, from_floor_cm: 110, from_corner_cm: null }] };
    const page = PAGE();
    page.rooms[0].photos = [{ ...photo, id: 'p0', place: null, markers: [] }];
    page.rooms[0].route_map = [photo];
    vi.mocked(api.fetchTradePage).mockResolvedValue(page);
    show();
    expect(await screen.findByLabelText('master-room-photos-Salon')).toBeInTheDocument();
    expect(screen.getByLabelText('master-route-map-Salon')).toBeInTheDocument();
    expect(screen.queryByLabelText('master-room-photos-Łazienka')).toBeNull();
    expect(screen.getByText('Przewód elektryczny · od podłogi 110 cm')).toBeInTheDocument();
  });

  it('reads the page again when the link of a picture has run out', async () => {
    const page = PAGE();
    page.rooms[0].photos = [{ id: 'p0', thumb_url: 'https://f.example/t', url: 'https://f.example/d', width: 10, height: 10, place: null, markers: [] }];
    vi.mocked(api.fetchTradePage).mockResolvedValue(page);
    show();
    fireEvent.click(await screen.findByLabelText('master-photo-p0'));
    fireEvent.error(screen.getByRole('dialog').querySelector('img') as HTMLImageElement);
    fireEvent.click(screen.getByLabelText('master-photo-reload'));
    await waitFor(() => expect(api.fetchTradePage).toHaveBeenCalledTimes(2));
  });
});

describe('saving a room', () => {
  it('sends only the answered positions and the own ones, then shows the room as saved', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    const saved = PAGE({
      rooms: [
        { id: 'r1', name: 'Salon', length: null, width: null, height: null, floor_area: null, perimeter: null,
          typical: [{ key: 'SOCKET', unit: 'PCS', quantity: '6.00', note: null }, { key: 'CABLE_ROUTE', unit: 'LM', quantity: '12.50', note: null }],
          own: [{ name: 'Gniazdo siłowe', quantity: '1.00', unit: 'PCS', note: null }], photos: [], route_map: [] },
        PAGE().rooms[1],
      ],
    });
    vi.mocked(api.saveTradeRoom).mockResolvedValue(saved);
    show();
    expect(await screen.findByLabelText('master-room-save-r1')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('master-qty-r1-SOCKET'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('master-qty-r1-CABLE_ROUTE'), { target: { value: '12,5' } });
    fireEvent.click(screen.getByLabelText('master-own-add-r1'));
    fireEvent.change(screen.getByLabelText('master-own-name-r1-0'), { target: { value: 'Gniazdo siłowe' } });
    fireEvent.change(screen.getByLabelText('master-own-qty-r1-0'), { target: { value: '1' } });
    expect(screen.getByText('Zmiany nie są jeszcze zapisane.')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('master-room-save-r1'));
    await waitFor(() =>
      expect(api.saveTradeRoom).toHaveBeenCalledWith(TOKEN, 'r1', 'pl', {
        typical: [{ key: 'SOCKET', quantity: '6', note: null }, { key: 'CABLE_ROUTE', quantity: '12,5', note: null }],
        own: [{ name: 'Gniazdo siłowe', quantity: '1', unit: 'PCS', note: null }],
      }),
    );
    expect(await screen.findByText('Pomieszczenie zapisane.')).toBeInTheDocument();
    expect(screen.getByLabelText('master-room-save-r1')).toBeDisabled();
  });

  it('lets the craftsman add a note to a position and remove an own position', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    show();
    fireEvent.click(await screen.findByLabelText('master-note-add-r1-SOCKET'));
    fireEvent.change(screen.getByLabelText('master-note-r1-SOCKET'), { target: { value: 'przy TV' } });
    expect(screen.getByLabelText('master-note-r1-SOCKET')).toHaveValue('przy TV');
    fireEvent.click(screen.getByLabelText('master-own-add-r1'));
    expect(screen.getByLabelText('master-own-name-r1-0')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('master-own-remove-r1-0'));
    expect(screen.queryByLabelText('master-own-name-r1-0')).toBeNull();
  });

  it('shows the reason in the words of the language when the server refuses', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    vi.mocked(api.saveTradeRoom).mockRejectedValue(new ApiError('bad', 422, 'QUANTITY_INVALID'));
    show();
    fireEvent.change(await screen.findByLabelText('master-qty-r1-CABLE_ROUTE'), { target: { value: '1.2.3' } });
    fireEvent.click(screen.getByLabelText('master-room-save-r1'));
    expect(await screen.findByText('Wpisz liczbę, np. 4 lub 12,5.')).toBeInTheDocument();
    expect(screen.getByLabelText('master-room-save-r1')).not.toBeDisabled();
  });

  it('keeps the typing of a room when the page is loaded again in another language', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    show();
    fireEvent.change(await screen.findByLabelText('master-qty-r1-SOCKET'), { target: { value: '3' } });
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE({ lang: 'en' }));
    fireEvent.change(screen.getByLabelText('master-language'), { target: { value: 'en' } });
    expect(await screen.findByText('Electrician — points and routes')).toBeInTheDocument();
    expect(screen.getByLabelText('master-qty-r1-SOCKET')).toHaveValue('3');
  });
});

describe('sending', () => {
  it('needs a name and at least one answered position', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    show();
    expect(await screen.findByLabelText('master-submit')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('master-qty-r1-SOCKET'), { target: { value: '2' } });
    expect(screen.getByLabelText('master-submit')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('master-name'), { target: { value: 'Jan Elektryk' } });
    expect(screen.getByLabelText('master-submit')).not.toBeDisabled();
  });

  it('saves the rooms that were changed, then sends, and says so', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    vi.mocked(api.saveTradeRoom).mockResolvedValue(PAGE());
    vi.mocked(api.submitTradeAnswers).mockResolvedValue(PAGE({ submissions_count: 1, last_submitted_at: '2026-10-27T09:30:00Z' }));
    show();
    fireEvent.change(await screen.findByLabelText('master-qty-r1-SOCKET'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('master-name'), { target: { value: 'Jan Elektryk' } });
    fireEvent.click(screen.getByLabelText('master-submit'));
    expect(await screen.findByLabelText('master-submitted')).toBeInTheDocument();
    expect(api.saveTradeRoom).toHaveBeenCalledTimes(1);
    expect(api.submitTradeAnswers).toHaveBeenCalledWith(TOKEN, 'pl', 'Jan Elektryk');
    const saveOrder = vi.mocked(api.saveTradeRoom).mock.invocationCallOrder[0];
    expect(saveOrder).toBeLessThan(vi.mocked(api.submitTradeAnswers).mock.invocationCallOrder[0]);
  });

  it('does not send when a room cannot be saved', async () => {
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    vi.mocked(api.saveTradeRoom).mockRejectedValue(new ApiError('bad', 422, 'QUANTITY_TOO_BIG'));
    show();
    fireEvent.change(await screen.findByLabelText('master-qty-r1-SOCKET'), { target: { value: '9999' } });
    fireEvent.change(screen.getByLabelText('master-name'), { target: { value: 'Jan' } });
    fireEvent.click(screen.getByLabelText('master-submit'));
    expect(await screen.findByText('Najpierw popraw błąd w pomieszczeniu powyżej.')).toBeInTheDocument();
    expect(api.submitTradeAnswers).not.toHaveBeenCalled();
  });
});

describe('a link that does not work', () => {
  it('says the link is wrong for an empty secret without asking the server', async () => {
    show('');
    expect(await screen.findByLabelText('master-not_found')).toBeInTheDocument();
    expect(api.fetchTradePage).not.toHaveBeenCalled();
  });

  it.each([
    [404, 'master-not_found'],
    [410, 'master-inactive'],
    [429, 'master-limited'],
    [500, 'master-error'],
  ])('shows the state for the status %s', async (status, label) => {
    vi.mocked(api.fetchTradePage).mockRejectedValue(new ApiError('x', status));
    show();
    expect(await screen.findByLabelText(label)).toBeInTheDocument();
  });

  it('offers to try again after a network failure', async () => {
    vi.mocked(api.fetchTradePage).mockRejectedValueOnce(new ApiError('network', 0, 'NETWORK'));
    show();
    vi.mocked(api.fetchTradePage).mockResolvedValue(PAGE());
    fireEvent.click(await screen.findByLabelText('master-retry'));
    expect(await screen.findByText('Salon')).toBeInTheDocument();
  });
});
