import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as pointsApi from '../api/roomPoints';
import * as itemsApi from '../api/priceItems';
import * as tradesApi from '../api/trades';
import { resetTrades } from '../hooks/useTrades';
import { CATALOG } from '../test/tradesFixture';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { reportNetworkFailure, resetConnectionForTests } from '../offline/connection';
import type { PriceItem } from '../types/priceItem';
import type { RoomPoint } from '../types/roomPoints';
import { EstimatePointsAction } from './EstimatePointsAction';
import { RoomPointsSection } from './RoomPointsSection';

vi.mock('../api/roomPoints', () => ({
  fetchRoomPoints: vi.fn(),
  createRoomPoint: vi.fn(),
  updateRoomPoint: vi.fn(),
  deleteRoomPoint: vi.fn(),
  addPointsToEstimate: vi.fn(),
  makePointsPack: vi.fn(),
}));
vi.mock('../api/priceItems', () => ({ fetchPriceItems: vi.fn() }));
vi.mock('../api/trades', () => ({ fetchTrades: vi.fn(), saveTrades: vi.fn() }));

// V2-10 — the list "Punkty i trasy" of a room and the button of the estimate: the screen shows what the server sent and counts nothing.

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const item = (over: Partial<PriceItem>): PriceItem => ({
  id: 'i1', code: 'CUSTOM_AAA', name_key: null, display_name: 'Gniazdko', category: 'ELECTRICAL', unit: 'PCS', price: '45.00', currency: 'PLN', price_scope: 'LABOR',
  quality_level: null, is_archived: false, created_at: '2026-10-29T10:00:00Z', updated_at: '2026-10-29T10:00:00Z', ...over,
} as PriceItem);
const SOCKET = item({});
const CHASE = item({ id: 'i2', code: 'CUSTOM_BBB', display_name: 'Bruzda', unit: 'LM' });
const AREA = item({ id: 'i3', code: 'CUSTOM_CCC', display_name: 'Układanie', unit: 'M2', category: 'TILE' });
const AREA_OTHER = item({ id: 'i5', code: 'CENNIK_PAINT_2K-01', display_name: 'Malowanie', unit: 'M2', category: 'PAINTING' });
const BUILT_IN = item({ id: 'i4', code: 'CENNIK_GK_CORNER-01', display_name: null, name_key: 'pricebook.seed.gk_corner', unit: 'LM', category: 'DRYWALL' });
const row = (over: Partial<RoomPoint> = {}): RoomPoint => ({
  id: 'r1', room_id: roomId, quantity: '12.00', note: 'przy oknie',
  item: { id: 'i1', code: 'CUSTOM_AAA', name_key: null, display_name: 'Gniazdko', category: 'ELECTRICAL', unit: 'PCS', price: '45.00', is_archived: false },
  created_at: '2026-10-29T10:00:00Z', updated_at: '2026-10-29T10:00:00Z', ...over,
});

function renderSection() {
  return render(<I18nProvider><RoomPointsSection projectId={projectId} roomId={roomId} /></I18nProvider>);
}
async function open() {
  fireEvent.click(screen.getByLabelText('room-points-toggle'));
  await screen.findByLabelText('room-points');
}
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

beforeEach(() => {
  localStorage.setItem('locale', 'pl');
  vi.mocked(pointsApi.fetchRoomPoints).mockResolvedValue([row()]);
  vi.mocked(itemsApi.fetchPriceItems).mockResolvedValue({ items: [SOCKET, CHASE, AREA, BUILT_IN], total: 4 } as never);
});
afterEach(() => {
  resetTrades();
  cleanup();
  vi.clearAllMocks();
  resetConnectionForTests();
});

describe('the list of the points and routes of a room', () => {
  it('asks the server for nothing until it is opened', () => {
    renderSection();
    expect(screen.getByLabelText('room-points-toggle')).toHaveAttribute('aria-expanded', 'false');
    expect(pointsApi.fetchRoomPoints).not.toHaveBeenCalled();
    expect(itemsApi.fetchPriceItems).not.toHaveBeenCalled();
  });

  it('shows the rows with the unit of the item and the note, as the server sent them', async () => {
    renderSection();
    await open();
    expect(await screen.findByLabelText('room-point-r1')).toHaveTextContent('Gniazdko');
    expect(screen.getByLabelText('room-point-quantity-r1')).toHaveTextContent('12 szt.');
    expect(screen.getByLabelText('room-point-r1')).toHaveTextContent('przy oknie');
    expect(pointsApi.fetchRoomPoints).toHaveBeenCalledWith(projectId, roomId);
  });

  it('shows a route in metres and the built-in name of an item in the language of the screen', async () => {
    vi.mocked(pointsApi.fetchRoomPoints).mockResolvedValue([row({ id: 'r2', quantity: '7.50', note: null, item: { ...row().item, id: 'i4', display_name: null, name_key: 'pricebook.seed.gk_corner', unit: 'LM' } })]);
    renderSection();
    await open();
    expect(await screen.findByLabelText('room-point-quantity-r2')).toHaveTextContent('7,5 mb');
    expect(screen.getByLabelText('room-point-r2')).toHaveTextContent('Wykończenie naroży zewnętrznych g-k');
  });

  it('says so when the room has none, and when the list cannot be read it can be read again', async () => {
    vi.mocked(pointsApi.fetchRoomPoints).mockRejectedValueOnce(new Error('down'));
    renderSection();
    await open();
    expect(await screen.findByText('Nie udało się wczytać punktów i tras.')).toBeInTheDocument();
    vi.mocked(pointsApi.fetchRoomPoints).mockResolvedValue([]);
    fireEvent.click(screen.getByLabelText('room-points-retry'));
    expect(await screen.findByLabelText('room-points-empty')).toBeInTheDocument();
  });

  it('offers only the items in pieces or in metres, and adds a row with the quantity with a point', async () => {
    vi.mocked(pointsApi.createRoomPoint).mockResolvedValue(row());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('room-point-add'));
    const options = Array.from(screen.getByLabelText('room-point-item').querySelectorAll('option')).map((o) => o.textContent);
    expect(options).toEqual(['Wybierz pozycję…', 'Gniazdko · szt.', 'Bruzda · mb', 'Wykończenie naroży zewnętrznych g-k (kątownik + szpachla) · mb']);
    fireEvent.change(screen.getByLabelText('room-point-item'), { target: { value: 'i2' } });
    expect(screen.getByText('Długość, mb')).toBeInTheDocument();
    type('room-point-quantity', '7,5');
    type('room-point-note', '  pod sufitem ');
    fireEvent.click(screen.getByLabelText('room-point-save'));
    await waitFor(() => expect(pointsApi.createRoomPoint).toHaveBeenCalledWith(projectId, roomId, { price_item_id: 'i2', quantity: '7.5', note: 'pod sufitem' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Zapisano.');
  });

  it('refuses a form with no item or with a quantity that is not above zero, and sends nothing', async () => {
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('room-point-add'));
    fireEvent.click(screen.getByLabelText('room-point-save'));
    expect(await screen.findByText('Wybierz pozycję cennika.')).toBeInTheDocument();
    expect(screen.getByText(/Wpisz ilość większą od zera/)).toBeInTheDocument();
    for (const bad of ['0', '1,234', 'x', '-2']) {
      fireEvent.change(screen.getByLabelText('room-point-item'), { target: { value: 'i1' } });
      type('room-point-quantity', bad);
      fireEvent.click(screen.getByLabelText('room-point-save'));
      expect(await screen.findByText(/Wpisz ilość większą od zera/)).toBeInTheDocument();
    }
    expect(pointsApi.createRoomPoint).not.toHaveBeenCalled();
  });

  it('takes the number said into the microphone panel', async () => {
    vi.mocked(pointsApi.createRoomPoint).mockResolvedValue(row());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('room-point-add'));
    fireEvent.change(screen.getByLabelText('room-point-item'), { target: { value: 'i1' } });
    fireEvent.click(screen.getByLabelText('voice-room-point-quantity'));
    fireEvent.change(screen.getByLabelText('voice-text-room-point-quantity'), { target: { value: 'siedem i pół' } });
    fireEvent.click(screen.getByLabelText('voice-insert-room-point-quantity'));
    expect((screen.getByLabelText('room-point-quantity') as HTMLInputElement).value).toBe('7,5');
  });

  it('opens a row with its values and sends the change', async () => {
    vi.mocked(pointsApi.updateRoomPoint).mockResolvedValue(row({ quantity: '14.00' }));
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('room-point-edit-r1'));
    expect((screen.getByLabelText('room-point-item') as HTMLSelectElement).value).toBe('i1');
    expect((screen.getByLabelText('room-point-quantity') as HTMLInputElement).value).toBe('12,00');
    type('room-point-quantity', '14');
    fireEvent.click(screen.getByLabelText('room-point-save'));
    await waitFor(() => expect(pointsApi.updateRoomPoint).toHaveBeenCalledWith(projectId, roomId, 'r1', { price_item_id: 'i1', quantity: '14', note: 'przy oknie' }));
  });

  it('keeps an item that has left the list chosen in the form of its row', async () => {
    vi.mocked(itemsApi.fetchPriceItems).mockResolvedValue({ items: [CHASE], total: 1 } as never);
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('room-point-edit-r1'));
    expect((screen.getByLabelText('room-point-item') as HTMLSelectElement).value).toBe('i1');
  });

  it('says what the server refused, in the words of the screen', async () => {
    vi.mocked(pointsApi.createRoomPoint).mockRejectedValue(new ApiError('x', 422, 'POINT_UNIT_INVALID'));
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('room-point-add'));
    fireEvent.change(screen.getByLabelText('room-point-item'), { target: { value: 'i1' } });
    type('room-point-quantity', '2');
    fireEvent.click(screen.getByLabelText('room-point-save'));
    expect(await screen.findByText('Tylko pozycja w szt. lub w mb może być punktem albo trasą.')).toBeInTheDocument();
  });

  it('deletes only after a second tap', async () => {
    vi.mocked(pointsApi.deleteRoomPoint).mockResolvedValue(undefined);
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('room-point-delete-r1'));
    expect(pointsApi.deleteRoomPoint).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('room-point-delete-no-r1'));
    fireEvent.click(screen.getByLabelText('room-point-delete-r1'));
    fireEvent.click(screen.getByLabelText('room-point-delete-yes-r1'));
    await waitFor(() => expect(pointsApi.deleteRoomPoint).toHaveBeenCalledWith(projectId, roomId, 'r1'));
  });

  it('offers the typical items while the price book has none of the trades, with the add button when other items exist', async () => {
    vi.mocked(pointsApi.fetchRoomPoints).mockResolvedValue([]);
    vi.mocked(itemsApi.fetchPriceItems).mockResolvedValue({ items: [BUILT_IN, AREA_OTHER], total: 2 } as never);
    vi.mocked(pointsApi.makePointsPack).mockResolvedValue({ created: 12, existing: 0 });
    renderSection();
    await open();
    expect(await screen.findByLabelText('room-points-pack-card')).toHaveTextContent('nie ma jeszcze pozycji dla elektryka');
    expect(screen.getByLabelText('room-point-add')).toBeInTheDocument();
    vi.mocked(itemsApi.fetchPriceItems).mockResolvedValue({ items: [BUILT_IN, SOCKET], total: 2 } as never);
    fireEvent.click(screen.getByLabelText('room-points-pack'));
    expect(await screen.findByText('Dodano pozycji do cennika: 12.')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByLabelText('room-points-pack-card')).toBeNull());
  });

  it('says there is no item in pieces or metres at all, and shows no add button then', async () => {
    vi.mocked(pointsApi.fetchRoomPoints).mockResolvedValue([]);
    vi.mocked(itemsApi.fetchPriceItems).mockResolvedValue({ items: [AREA_OTHER], total: 1 } as never);
    renderSection();
    await open();
    expect(await screen.findByLabelText('room-points-pack-card')).toHaveTextContent('W cenniku nie ma pozycji w szt. ani w mb.');
    expect(screen.queryByLabelText('room-point-add')).toBeNull();
  });

  it('does not offer the typical items once the price book has an item of a trade', async () => {
    renderSection();
    await open();
    await screen.findByLabelText('room-point-add');
    expect(screen.queryByLabelText('room-points-pack-card')).toBeNull();
  });

  it('cannot be changed without the signal', async () => {
    renderSection();
    await open();
    reportNetworkFailure();
    await waitFor(() => expect(screen.getByLabelText('room-point-add')).toBeDisabled());
    expect(screen.getByLabelText('room-point-edit-r1')).toBeDisabled();
    expect(screen.getByLabelText('room-points-offline')).toBeInTheDocument();
  });
});

describe('the button of the estimate', () => {
  function renderAction(onMessage = vi.fn(), onAdded = vi.fn(), message = null as never) {
    render(<I18nProvider><EstimatePointsAction projectId={projectId} estimateId="e1" message={message} onMessage={onMessage} onAdded={onAdded} /></I18nProvider>);
    return { onMessage, onAdded };
  }

  it('adds the rows, says how many, and has the estimate read again when something was added', async () => {
    vi.mocked(pointsApi.addPointsToEstimate).mockResolvedValue({ added: 3, already: 1, skipped: [{ point_id: 'p', code: 'POINT_ITEM_ARCHIVED' }] });
    const { onMessage, onAdded } = renderAction();
    fireEvent.click(screen.getByLabelText('estimate-add-points-action'));
    await waitFor(() => expect(onAdded).toHaveBeenCalledTimes(1));
    expect(pointsApi.addPointsToEstimate).toHaveBeenCalledWith(projectId, 'e1');
    expect(onMessage).toHaveBeenLastCalledWith({ kind: 'ok', text: 'Dodano pozycji: 3. Już w kosztorysie: 1. Pominięto: 1 (pozycja w archiwum lub zmieniona jednostka).' });
  });

  it('does not read the estimate again when nothing was added, and says when there is nothing to add', async () => {
    vi.mocked(pointsApi.addPointsToEstimate).mockResolvedValue({ added: 0, already: 0, skipped: [] });
    const { onMessage, onAdded } = renderAction();
    fireEvent.click(screen.getByLabelText('estimate-add-points-action'));
    await waitFor(() => expect(onMessage).toHaveBeenLastCalledWith({ kind: 'ok', text: 'Nie ma punktów ani tras do dodania.' }));
    expect(onAdded).not.toHaveBeenCalled();
  });

  it('says why when the estimate is not a draft any more, and when the server fails', async () => {
    vi.mocked(pointsApi.addPointsToEstimate).mockRejectedValueOnce(new ApiError('x', 409, 'ESTIMATE_NOT_DRAFT'));
    const { onMessage } = renderAction();
    fireEvent.click(screen.getByLabelText('estimate-add-points-action'));
    await waitFor(() => expect(onMessage).toHaveBeenLastCalledWith({ kind: 'error', text: 'Pozycje można dodawać tylko do wersji roboczej kosztorysu.' }));
    vi.mocked(pointsApi.addPointsToEstimate).mockRejectedValueOnce(new Error('boom'));
    fireEvent.click(screen.getByLabelText('estimate-add-points-action'));
    await waitFor(() => expect(onMessage).toHaveBeenLastCalledWith({ kind: 'error', text: 'Nie udało się dodać punktów i tras.' }));
  });

  it('shows the message it was given and is off without the signal', async () => {
    renderAction(vi.fn(), vi.fn(), { kind: 'ok', text: 'Dodano.' } as never);
    expect(screen.getByRole('status')).toHaveTextContent('Dodano.');
    reportNetworkFailure();
    await waitFor(() => expect(screen.getByLabelText('estimate-add-points-action')).toBeDisabled());
  });
});

describe('the trades of the owner (V2-13)', () => {
  it('offers in the form only the items of the trades that are on, and keeps the item of a row that is already there', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING', 'TILE'] });
    vi.mocked(itemsApi.fetchPriceItems).mockResolvedValue({ items: [SOCKET, CHASE, BUILT_IN, item({ id: 'i6', code: 'CUSTOM_DDD', display_name: 'Punkt płytek', unit: 'PCS', category: 'TILE' })], total: 4 } as never);
    renderSection();
    await open();
    await waitFor(() => expect(tradesApi.fetchTrades).toHaveBeenCalled());
    fireEvent.click(await screen.findByLabelText('room-point-add'));
    await waitFor(() => {
      const names = Array.from(screen.getByLabelText('room-point-item').querySelectorAll('option')).map((o) => o.textContent ?? '');
      expect(names.some((n) => n.includes('Punkt płytek'))).toBe(true);
      expect(names.some((n) => n.includes('Gniazdko') || n.includes('Bruzda'))).toBe(false); // the electrician's items: the trade is off
    });
    cleanup();
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('room-point-edit-r1'));
    const names = Array.from(screen.getByLabelText('room-point-item').querySelectorAll('option')).map((o) => o.textContent ?? '');
    expect(names.some((n) => n.includes('Gniazdko'))).toBe(true); // the row being edited keeps its own item
  });

  it('is not there for an owner without a trade of the points and routes, unless the room already has rows', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING', 'MICROCEMENT'] });
    vi.mocked(pointsApi.fetchRoomPoints).mockResolvedValue([]);
    renderSection();
    await waitFor(() => expect(pointsApi.fetchRoomPoints).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByLabelText('room-points-section')).toBeNull());
    cleanup();
    resetTrades();
    vi.mocked(pointsApi.fetchRoomPoints).mockResolvedValue([row()]);
    renderSection();
    await waitFor(() => expect(pointsApi.fetchRoomPoints).toHaveBeenCalledTimes(2)); // the room is looked at once for rows that must not be hidden
    expect(await screen.findByLabelText('room-points-section')).toBeInTheDocument();
  });
});
