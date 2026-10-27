/** V2-14a — carrying the answers of a craftsman over into the rooms: the preview, the choice of the price book item, the button, the states. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import * as pointsApi from '../api/roomPoints';
import * as api from '../api/tradeLinks';
import { I18nProvider } from '../hooks/useI18n';
import type { TransferCandidate, TransferPreview } from '../types/tradeLink';
import { TradeTransferPanel } from './TradeTransferPanel';

vi.mock('../api/roomPoints', () => ({ makePointsPack: vi.fn() }));
vi.mock('../api/tradeLinks', () => ({
  previewTradeTransfer: vi.fn(),
  runTradeTransfer: vi.fn(),
}));

const CAND = (id: string, name: string, unit: 'PCS' | 'LM' = 'PCS'): TransferCandidate => ({
  id, code: `CUSTOM_${id}`, name_key: null, display_name: name, category: 'ELECTRICAL', unit, price: null, is_archived: false, relevant: true,
});
const POINT = CAND('i1', 'Punkt elektryczny - gniazdko / włącznik');
const PREMIUM = CAND('i2', 'Gniazdo premium');
const STAIR = { ...CAND('i9', 'Mikrocement na schody'), category: 'MICROCEMENT', relevant: false };
const CABLE = CAND('i3', 'Ułożenie przewodu elektrycznego', 'LM');

const PREVIEW = (overrides: Partial<TransferPreview> = {}): TransferPreview => ({
  trade: 'ELECTRIC',
  positions: [
    { key: 'SOCKET', unit: 'PCS', goes_to_points: true, answered_rooms: 2, item_id: 'i1', default_item_id: 'i1', candidates: [POINT, PREMIUM, STAIR] },
    { key: 'LIGHT_POINT', unit: 'PCS', goes_to_points: true, answered_rooms: 1, item_id: null, default_item_id: null, candidates: [POINT, PREMIUM] },
    { key: 'CIRCUIT', unit: 'PCS', goes_to_points: false, answered_rooms: 1, item_id: null, default_item_id: null, candidates: [] },
    { key: 'CABLE_ROUTE', unit: 'LM', goes_to_points: true, answered_rooms: 1, item_id: 'i3', default_item_id: 'i3', candidates: [CABLE] },
  ],
  rooms: [
    {
      room_id: 'r1', room_name: 'Salon',
      rows: [
        { kind: 'NEW', item_id: 'i1', quantity: '8.00', was_quantity: null, note: 'przy TV' },
        { kind: 'CHANGE', item_id: 'i3', quantity: '12.50', was_quantity: '10.00', note: null },
      ],
      material: { kind: 'NEW', package: 'ELECTRIC', numbers: { sockets: '6', circuits: '2', route_m: '12.50' } },
    },
    { room_id: 'r2', room_name: 'Łazienka', rows: [{ kind: 'REMOVE', item_id: 'i1', quantity: '2.00', was_quantity: null, note: null }], material: { kind: 'NONE', package: 'ELECTRIC', numbers: {} } },
    { room_id: 'r3', room_name: 'Pusty', rows: [], material: { kind: 'NONE', package: 'ELECTRIC', numbers: {} } },
  ],
  own_not_carried: 2,
  nothing: false,
  offer_pack: false,
  ...overrides,
});

function show(onClose = vi.fn()) {
  render(
    <I18nProvider>
      <TradeTransferPanel projectId="proj1" trade="ELECTRIC" onClose={onClose} />
    </I18nProvider>,
  );
  return onClose;
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(api.previewTradeTransfer).mockResolvedValue(PREVIEW());
});

describe('the preview', () => {
  it('asks the server first with no choice of the owner and writes nothing', async () => {
    show();
    expect(await screen.findByLabelText('trade-transfer-rooms-ELECTRIC')).toBeInTheDocument();
    expect(api.previewTradeTransfer).toHaveBeenCalledWith('proj1', 'ELECTRIC', {});
    expect(api.runTradeTransfer).not.toHaveBeenCalled();
  });

  it('shows what happens in each room, hides a room with nothing, and names the numbers of the materials in the language', async () => {
    show();
    const rooms = await screen.findByLabelText('trade-transfer-rooms-ELECTRIC');
    expect(within(rooms).getByText('Salon')).toBeInTheDocument();
    expect(within(rooms).getByText('Łazienka')).toBeInTheDocument();
    expect(within(rooms).queryByText('Pusty')).toBeNull();
    expect(within(rooms).getByText(/Punkt elektryczny - gniazdko \/ włącznik: 8 szt\./)).toBeInTheDocument();
    expect(within(rooms).getByText(/Ułożenie przewodu elektrycznego: 12,50 m\.b\. \(było 10,00\)/)).toBeInTheDocument();
    expect(within(rooms).getByText(/Gniazdka 6 · Obwody \(zabezpieczenia\) 2 · Trasa kabli 12,50/)).toBeInTheDocument();
    expect(within(rooms).getAllByText('nowe').length).toBe(2);
    expect(within(rooms).getByText('zmiana')).toBeInTheDocument();
    expect(within(rooms).getByText('usunąć')).toBeInTheDocument();
  });

  it('offers a choice of the price book item only for the answered positions that have one, with the default chosen', async () => {
    show();
    const socket = await screen.findByLabelText('trade-transfer-item-ELECTRIC-SOCKET');
    expect(socket).toHaveValue('i1');
    expect(within(socket).getAllByRole('option').map((o) => o.textContent)).toEqual(['— nie przenoś —', 'Punkt elektryczny - gniazdko / włącznik', 'Gniazdo premium']); // the stair item is not of this trade
    expect(screen.getByLabelText('trade-transfer-item-ELECTRIC-LIGHT_POINT')).toHaveValue('');
    expect(screen.getByText(/Brak pozycji w cenniku/)).toBeInTheDocument();
    expect(screen.queryByLabelText('trade-transfer-item-ELECTRIC-CIRCUIT')).toBeNull(); // the circuits have no item: the materials only
  });

  it('says how many own positions of the craftsman stay out', async () => {
    show();
    expect(await screen.findByLabelText('trade-transfer-own-ELECTRIC')).toHaveTextContent('Własne pozycje mistrza (2) nie są przenoszone');
  });

  it('shows the preview again with the choice of the owner when he picks another item or none', async () => {
    show();
    fireEvent.change(await screen.findByLabelText('trade-transfer-item-ELECTRIC-SOCKET'), { target: { value: 'i2' } });
    await waitFor(() => expect(api.previewTradeTransfer).toHaveBeenLastCalledWith('proj1', 'ELECTRIC', { SOCKET: 'i2' }));
    fireEvent.change(screen.getByLabelText('trade-transfer-item-ELECTRIC-LIGHT_POINT'), { target: { value: '' } });
    await waitFor(() => expect(api.previewTradeTransfer).toHaveBeenLastCalledWith('proj1', 'ELECTRIC', { SOCKET: 'i2', LIGHT_POINT: null }));
  });

  it('offers to try again when the preview does not load', async () => {
    vi.mocked(api.previewTradeTransfer).mockRejectedValueOnce(new ApiError('x', 500));
    show();
    fireEvent.click(await screen.findByLabelText('trade-transfer-retry-ELECTRIC'));
    expect(await screen.findByLabelText('trade-transfer-rooms-ELECTRIC')).toBeInTheDocument();
  });

  it('says there is nothing to carry over and keeps the button off', async () => {
    vi.mocked(api.previewTradeTransfer).mockResolvedValue(PREVIEW({ rooms: [], nothing: true, own_not_carried: 0 }));
    show();
    expect(await screen.findByLabelText('trade-transfer-empty-ELECTRIC')).toBeInTheDocument();
    expect(screen.getByLabelText('trade-transfer-run-ELECTRIC')).toBeDisabled();
  });
});

describe('the items of the price book', () => {
  it('shows the items of the trade first, the others only on request', async () => {
    show();
    const socket = await screen.findByLabelText('trade-transfer-item-ELECTRIC-SOCKET');
    expect(within(socket).queryByText('Mikrocement na schody')).toBeNull();
    fireEvent.click(screen.getByLabelText('trade-transfer-show-all-ELECTRIC'));
    expect(within(socket).getByText('Mikrocement na schody')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('trade-transfer-show-all-ELECTRIC'));
    expect(within(socket).queryByText('Mikrocement na schody')).toBeNull();
  });

  it('keeps an item that is chosen even if it is not of the trade', async () => {
    const chosen = PREVIEW();
    chosen.positions[0].item_id = 'i9';
    vi.mocked(api.previewTradeTransfer).mockResolvedValue(chosen);
    show();
    const socket = await screen.findByLabelText('trade-transfer-item-ELECTRIC-SOCKET');
    expect(within(socket).getByText('Mikrocement na schody')).toBeInTheDocument();
  });

  it('makes the typical items from the panel and reads the preview again', async () => {
    vi.mocked(api.previewTradeTransfer).mockResolvedValue(PREVIEW({ offer_pack: true }));
    vi.mocked(pointsApi.makePointsPack).mockResolvedValue({ created: 12, existing: 0 });
    show();
    expect(await screen.findByLabelText('trade-transfer-pack-ELECTRIC')).toBeInTheDocument();
    vi.mocked(api.previewTradeTransfer).mockResolvedValue(PREVIEW({ offer_pack: false }));
    fireEvent.click(screen.getByLabelText('trade-transfer-pack-run-ELECTRIC'));
    expect(await screen.findByText('Dodano pozycji do cennika: 12.')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByLabelText('trade-transfer-pack-ELECTRIC')).toBeNull());
    expect(api.previewTradeTransfer).toHaveBeenCalledTimes(2);
  });

  it('offers no pack when every answered position has its item', async () => {
    show();
    await screen.findByLabelText('trade-transfer-rooms-ELECTRIC');
    expect(screen.queryByLabelText('trade-transfer-pack-ELECTRIC')).toBeNull();
  });
});

describe('carrying over', () => {
  it('sends the choice and both options, says what was done and reads the preview again', async () => {
    vi.mocked(api.runTradeTransfer).mockResolvedValue({ points_added: 2, points_changed: 1, points_removed: 1, materials_added: 1, materials_changed: 0, materials_removed: 0 });
    show();
    fireEvent.change(await screen.findByLabelText('trade-transfer-item-ELECTRIC-SOCKET'), { target: { value: 'i2' } });
    await waitFor(() => expect(api.previewTradeTransfer).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByLabelText('trade-transfer-run-ELECTRIC'));
    await waitFor(() => expect(api.runTradeTransfer).toHaveBeenCalledWith('proj1', 'ELECTRIC', { SOCKET: 'i2' }, true, true));
    expect(await screen.findByText('Punkty: dodano 2, zmieniono 1, usunięto 1. Materiały: dodano 1, zmieniono 0, usunięto 0.')).toBeInTheDocument();
    await waitFor(() => expect(api.previewTradeTransfer).toHaveBeenCalledTimes(3));
  });

  it('says so when nothing changed (a second press)', async () => {
    vi.mocked(api.runTradeTransfer).mockResolvedValue({ points_added: 0, points_changed: 0, points_removed: 0, materials_added: 0, materials_changed: 0, materials_removed: 0 });
    show();
    fireEvent.click(await screen.findByLabelText('trade-transfer-run-ELECTRIC'));
    expect(await screen.findByText('Wszystko już jest przeniesione — nic się nie zmieniło.')).toBeInTheDocument();
  });

  it('carries only the points, or only the materials, as the options say; with both off the button is off', async () => {
    vi.mocked(api.runTradeTransfer).mockResolvedValue({ points_added: 1, points_changed: 0, points_removed: 0, materials_added: 0, materials_changed: 0, materials_removed: 0 });
    show();
    fireEvent.click(await screen.findByLabelText('trade-transfer-materials-ELECTRIC'));
    fireEvent.click(screen.getByLabelText('trade-transfer-run-ELECTRIC'));
    await waitFor(() => expect(api.runTradeTransfer).toHaveBeenLastCalledWith('proj1', 'ELECTRIC', {}, true, false));
    await screen.findByText(/Punkty: dodano 1/);
    fireEvent.click(screen.getByLabelText('trade-transfer-materials-ELECTRIC'));
    fireEvent.click(screen.getByLabelText('trade-transfer-points-ELECTRIC'));
    expect(screen.getByLabelText('trade-transfer-run-ELECTRIC')).not.toBeDisabled();
    fireEvent.click(screen.getByLabelText('trade-transfer-materials-ELECTRIC'));
    expect(screen.getByLabelText('trade-transfer-run-ELECTRIC')).toBeDisabled();
  });

  it('keeps the rows of the points out of the list while the points are switched off', async () => {
    show();
    const rooms = await screen.findByLabelText('trade-transfer-rooms-ELECTRIC');
    fireEvent.click(screen.getByLabelText('trade-transfer-points-ELECTRIC'));
    expect(within(rooms).queryByText(/Punkt elektryczny/)).toBeNull();
    expect(within(rooms).getByText(/Gniazdka 6/)).toBeInTheDocument();
  });

  it('warns about a number that a calculation cannot hold and still lets the points go', async () => {
    const bad = PREVIEW();
    bad.rooms[0].material = { kind: 'INVALID', package: 'ELECTRIC', numbers: { circuits: '150' } };
    vi.mocked(api.previewTradeTransfer).mockResolvedValue(bad);
    show();
    expect(await screen.findByText(/Liczba poza zakresem obliczenia/)).toBeInTheDocument();
    expect(screen.getByText(/Jedna z liczb jest za duża/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('trade-transfer-materials-ELECTRIC'));
    expect(screen.queryByText(/Jedna z liczb jest za duża/)).toBeNull();
    expect(screen.getByLabelText('trade-transfer-run-ELECTRIC')).not.toBeDisabled();
  });

  it('shows the reason in words when the server refuses, and closes on request', async () => {
    vi.mocked(api.runTradeTransfer).mockRejectedValue(new ApiError('x', 422, 'TRANSFER_MATERIALS_INVALID'));
    const onClose = show();
    fireEvent.click(await screen.findByLabelText('trade-transfer-run-ELECTRIC'));
    expect(await screen.findByText('Liczba w odpowiedzi jest poza zakresem obliczenia materiałów.')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('trade-transfer-close-ELECTRIC'));
    expect(onClose).toHaveBeenCalled();
  });
});
