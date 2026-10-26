import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/materials';
import * as tradesApi from '../api/trades';
import { resetTrades } from '../hooks/useTrades';
import { CATALOG } from '../test/tradesFixture';
import { I18nProvider } from '../hooks/useI18n';
import { reportNetworkFailure, resetConnectionForTests } from '../offline/connection';
import type { MaterialCalc, MaterialLine } from '../types/materials';
import { EstimateMaterialsAction } from './EstimateMaterialsAction';
import { RoomMaterialsSection } from './RoomMaterialsSection';

vi.mock('../api/materials', () => ({
  fetchCalcs: vi.fn(),
  fetchRouteTotals: vi.fn(),
  createCalc: vi.fn(),
  updateCalc: vi.fn(),
  deleteCalc: vi.fn(),
  fetchStatement: vi.fn(),
  fetchNorms: vi.fn(),
  updateNorm: vi.fn(),
  addMaterialsToEstimate: vi.fn(),
}));

vi.mock('../api/trades', () => ({ fetchTrades: vi.fn(), saveTrades: vi.fn() }));

// V2-11 — the calculations of materials of a room and the button of the estimate: the screen sends the data and shows what the server counted.

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const AREAS = { floor: '4.320', ceiling: 4.32, walls: '21.840', perimeter: '8.400', height: '2.600' }; // the server counts a room to three places
const lines: MaterialLine[] = [
  { code: 'TILE_TILES', name: 'Płytki', quantity: '11.00', unit_text: 'm²', pack_size: null, packs: null, pieces: 62, billing_unit: 'M2', billing_quantity: '11.00' },
  { code: 'TILE_ADHESIVE', name: 'Klej do płytek (worek)', quantity: '50.00', unit_text: 'kg', pack_size: '25', packs: 2, pieces: null, billing_unit: 'PCS', billing_quantity: '2.00' },
];
const calc = (over: Partial<MaterialCalc> = {}): MaterialCalc => ({
  id: 'c1', room_id: roomId, package: 'TILE', title: 'Podłoga łazienki',
  params: { area_m2: '10.00', length_cm: '30.0', width_cm: '60.0', thickness_mm: '8.0', joint_mm: '3.0', layout: 'STRAIGHT', waterproof: false, waterproof_area_m2: null, tape_m: null },
  materials: lines, created_at: '2026-10-30T10:00:00Z', updated_at: '2026-10-30T10:00:00Z', ...over,
});

function renderSection() {
  return render(<I18nProvider><RoomMaterialsSection projectId={projectId} roomId={roomId} areas={AREAS} /></I18nProvider>);
}
async function open() {
  fireEvent.click(screen.getByLabelText('room-materials-toggle'));
  await screen.findByLabelText('room-materials');
}
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

beforeEach(() => {
  localStorage.setItem('locale', 'pl');
  vi.mocked(api.fetchCalcs).mockResolvedValue([calc()]);
  vi.mocked(api.fetchRouteTotals).mockResolvedValue({ electrical_m: '12.50', plumbing_m: '0.00' });
});
afterEach(() => {
  resetTrades();
  cleanup();
  vi.clearAllMocks();
  resetConnectionForTests();
});

describe('the calculations of materials of a room', () => {
  it('asks the server for nothing until it is opened', () => {
    renderSection();
    expect(screen.getByLabelText('room-materials-toggle')).toHaveAttribute('aria-expanded', 'false');
    expect(api.fetchCalcs).not.toHaveBeenCalled();
  });

  it('shows a calculation with what to buy, as the server counted it', async () => {
    renderSection();
    await open();
    const card = await screen.findByLabelText('material-calc-c1');
    expect(card).toHaveTextContent('Podłoga łazienki');
    expect(card).toHaveTextContent('10 m² · 30×60 cm');
    const rows = screen.getByLabelText('material-lines-c1');
    expect(rows).toHaveTextContent('Płytki');
    expect(rows).toHaveTextContent('11 m²');
    expect(rows).toHaveTextContent('potrzeba 11 m² · 62 płytek');
    expect(rows).toHaveTextContent('Klej do płytek (worek)');
    expect(rows).toHaveTextContent('2 szt.');
    expect(rows).toHaveTextContent('potrzeba 50 kg · opak. 25 kg');
  });

  it('says so when there is none, and a failed read can be read again', async () => {
    vi.mocked(api.fetchCalcs).mockRejectedValueOnce(new Error('down'));
    renderSection();
    await open();
    expect(await screen.findByText('Nie udało się wczytać obliczeń.')).toBeInTheDocument();
    vi.mocked(api.fetchCalcs).mockResolvedValue([]);
    fireEvent.click(screen.getByLabelText('room-materials-retry'));
    expect(await screen.findByLabelText('room-materials-empty')).toBeInTheDocument();
  });

  it('sends a tile calculation with the area taken from the room with one tap and the numbers with points', async () => {
    vi.mocked(api.createCalc).mockResolvedValue(calc());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-use-Podłoga 4,32 m²'));
    expect((screen.getByLabelText('material-area') as HTMLInputElement).value).toBe('4,32');
    type('material-length', '30');
    type('material-width', '60,5');
    fireEvent.click(screen.getByLabelText('material-layout-DIAGONAL'));
    fireEvent.click(screen.getByLabelText('material-waterproof-on'));
    type('material-tape', '8,4');
    type('material-title', ' Podłoga ');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.createCalc).toHaveBeenCalledTimes(1));
    expect(api.createCalc).toHaveBeenCalledWith(projectId, roomId, {
      package: 'TILE', title: 'Podłoga',
      params: { area_m2: '4.32', length_cm: '30', width_cm: '60.5', thickness_mm: '8', joint_mm: '3', layout: 'DIAGONAL', waterproof: true, waterproof_area_m2: null, tape_m: '8.4' },
    });
    expect(await screen.findByRole('status')).toHaveTextContent('Zapisano.');
  });

  it('takes the area from two sides in metres when that way is chosen, and only one way is on at a time', async () => {
    vi.mocked(api.createCalc).mockResolvedValue(calc());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    expect(screen.getByLabelText('material-area-mode-AREA')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('material-area-mode-DIMS')).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(screen.getByLabelText('material-area-mode-DIMS'));
    expect(screen.getByLabelText('material-area-mode-AREA')).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByLabelText('material-area')).toBeNull();
    expect(screen.queryByLabelText('material-area-chips')).toBeNull();
    type('material-surface_length', '3,2');
    type('material-surface_width', '4,55');
    expect(screen.getByLabelText('material-area-result')).toHaveTextContent('Powierzchnia: 14,56 m²');
    type('material-length', '30');
    type('material-width', '60');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.createCalc).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.createCalc).mock.calls[0][2].params).toMatchObject({ area_m2: '14.56' });
  });

  it('asks for both sides, and the chips come back with the way of the area', async () => {
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-area-mode-DIMS'));
    type('material-surface_length', '3');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    expect(await screen.findByText('Wpisz szerokość większą od zera.')).toBeInTheDocument();
    expect(screen.queryByText('Wpisz długość większą od zera.')).toBeNull();
    expect(api.createCalc).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('material-area-mode-AREA'));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByLabelText('material-area-chips')).toBeInTheDocument();
  });

  it('sends the drywall area from two sides too', async () => {
    vi.mocked(api.createCalc).mockResolvedValue(calc());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-package-DRYWALL'));
    fireEvent.click(screen.getByLabelText('material-area-mode-DIMS'));
    type('material-surface_length', '5');
    type('material-surface_width', '2,6');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.createCalc).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.createCalc).mock.calls[0][2].params).toMatchObject({ kind: 'WALL', area_m2: '13.00' });
  });

  it('sends an electrical calculation with whole counts, the route of the room taken with one tap', async () => {
    vi.mocked(api.createCalc).mockResolvedValue(calc());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-package-ELECTRIC'));
    expect(screen.queryByLabelText('material-area')).toBeNull();
    expect(screen.queryByLabelText('material-area-mode-AREA')).toBeNull();
    type('material-sockets', '4');
    type('material-switches', '2');
    type('material-lights', '3');
    type('material-circuits', '2');
    fireEvent.click(await screen.findByLabelText('material-use-routes'));
    expect((screen.getByLabelText('material-route_m') as HTMLInputElement).value).toBe('12,50');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.createCalc).toHaveBeenCalledTimes(1));
    expect(api.createCalc).toHaveBeenCalledWith(projectId, roomId, {
      package: 'ELECTRIC', title: null, params: { sockets: 4, switches: 2, lights: 3, circuits: 2, route_m: '12.50' },
    });
  });

  it('sends a plumbing calculation, with no route button when the room has no pipe routes', async () => {
    vi.mocked(api.createCalc).mockResolvedValue(calc());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-package-PLUMBING'));
    await waitFor(() => expect(api.fetchRouteTotals).toHaveBeenCalled());
    expect(screen.queryByLabelText('material-use-routes')).toBeNull();
    type('material-water_points', '3');
    type('material-drain_points', '2');
    type('material-outlets', '4');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.createCalc).toHaveBeenCalledTimes(1));
    expect(api.createCalc).toHaveBeenCalledWith(projectId, roomId, {
      package: 'PLUMBING', title: null, params: { water_points: 3, drain_points: 2, manifold_outlets: 4, pipe_m: null },
    });
  });

  it('asks for a point, a circuit or a route, and for whole numbers', async () => {
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-package-ELECTRIC'));
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    expect(await screen.findByText('Wpisz co najmniej jeden punkt, obwód albo długość trasy.')).toBeInTheDocument();
    type('material-sockets', '2,5');
    type('material-route_m', '-3');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    expect(await screen.findAllByText('Wpisz liczbę całkowitą, 0 lub więcej.')).toHaveLength(1);
    expect(screen.getByText('Wpisz długość większą od zera.')).toBeInTheDocument();
    expect(api.createCalc).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('material-package-PLUMBING'));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('opens a saved electrical calculation with its numbers', async () => {
    vi.mocked(api.fetchCalcs).mockResolvedValue([calc({ package: 'ELECTRIC', title: null, params: { sockets: 4, switches: 0, lights: 3, circuits: 2, route_m: null } })]);
    vi.mocked(api.updateCalc).mockResolvedValue(calc());
    renderSection();
    await open();
    expect(await screen.findByText(/Gniazda: 4 · Światła: 3 · Obwody: 2/)).toBeInTheDocument();
    expect(screen.getByText('Elektryka')).toBeInTheDocument(); // the heading of an untitled calculation is its package
    fireEvent.click(await screen.findByLabelText('material-calc-edit-c1'));
    expect((screen.getByLabelText('material-sockets') as HTMLInputElement).value).toBe('4');
    expect((screen.getByLabelText('material-switches') as HTMLInputElement).value).toBe('');
    type('material-switches', '1');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.updateCalc).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.updateCalc).mock.calls[0][3]).toEqual({ title: null, params: { sockets: 4, switches: 1, lights: 3, circuits: 2, route_m: null } });
  });

  it('offers the perimeter of the room for the tape', async () => {
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-waterproof-on'));
    fireEvent.click(screen.getByLabelText('material-use-perimeter'));
    expect((screen.getByLabelText('material-tape') as HTMLInputElement).value).toBe('8,40');
  });

  it('sends a wall of drywall with the height of the room, and a ceiling with its perimeter', async () => {
    vi.mocked(api.createCalc).mockResolvedValue(calc());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-package-DRYWALL'));
    expect((screen.getByLabelText('material-height') as HTMLInputElement).value).toBe('2,60');
    fireEvent.click(screen.getByLabelText('material-use-Ściany 21,84 m²'));
    fireEvent.click(screen.getByLabelText('material-layers-2'));
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.createCalc).toHaveBeenLastCalledWith(projectId, roomId, { package: 'DRYWALL', title: null, params: { kind: 'WALL', area_m2: '21.84', layers: 2, height_m: '2.60', perimeter_m: null } }));
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-package-DRYWALL'));
    fireEvent.click(screen.getByLabelText('material-kind-CEILING'));
    expect((screen.getByLabelText('material-perimeter') as HTMLInputElement).value).toBe('8,40');
    expect(screen.queryByLabelText('material-height')).toBeNull();
    type('material-area', '10');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.createCalc).toHaveBeenLastCalledWith(projectId, roomId, { package: 'DRYWALL', title: null, params: { kind: 'CEILING', area_m2: '10', layers: 1, height_m: null, perimeter_m: '8.40' } }));
  });

  it('refuses a form with a missing or wrong number and sends nothing', async () => {
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    expect(await screen.findByText('Wpisz powierzchnię większą od zera.')).toBeInTheDocument();
    expect(screen.getByText('Wpisz długość płytki.')).toBeInTheDocument();
    expect(screen.getByText('Wpisz szerokość płytki.')).toBeInTheDocument();
    type('material-area', '5');
    type('material-length', '30,15');
    type('material-width', '0');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    expect(await screen.findByText('Wpisz długość płytki.')).toBeInTheDocument();
    expect(api.createCalc).not.toHaveBeenCalled();
  });

  it('takes the number said into the microphone panel', async () => {
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    fireEvent.click(screen.getByLabelText('voice-material-area'));
    fireEvent.change(screen.getByLabelText('voice-text-material-area'), { target: { value: 'dziesięć i pół' } });
    fireEvent.click(screen.getByLabelText('voice-insert-material-area'));
    expect((screen.getByLabelText('material-area') as HTMLInputElement).value).toBe('10,5');
  });

  it('opens a calculation with its values and sends the data whole', async () => {
    vi.mocked(api.updateCalc).mockResolvedValue(calc());
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-edit-c1'));
    expect(screen.queryByLabelText('material-package-TILE')).toBeNull();
    expect((screen.getByLabelText('material-length') as HTMLInputElement).value).toBe('30,0');
    type('material-area', '12');
    fireEvent.click(screen.getByLabelText('material-calc-save'));
    await waitFor(() => expect(api.updateCalc).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.updateCalc).mock.calls[0].slice(0, 3)).toEqual([projectId, roomId, 'c1']);
    expect(vi.mocked(api.updateCalc).mock.calls[0][3]).toMatchObject({ title: 'Podłoga łazienki', params: { area_m2: '12', length_cm: '30.0', width_cm: '60.0' } });
  });

  it('deletes only after a second tap', async () => {
    vi.mocked(api.deleteCalc).mockResolvedValue(undefined);
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-delete-c1'));
    expect(api.deleteCalc).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('material-calc-delete-no-c1'));
    fireEvent.click(screen.getByLabelText('material-calc-delete-c1'));
    fireEvent.click(screen.getByLabelText('material-calc-delete-yes-c1'));
    await waitFor(() => expect(api.deleteCalc).toHaveBeenCalledWith(projectId, roomId, 'c1'));
  });

  it('cannot be changed without the signal', async () => {
    renderSection();
    await open();
    await screen.findByLabelText('material-calc-c1');
    reportNetworkFailure();
    await waitFor(() => expect(screen.getByLabelText('material-calc-add')).toBeDisabled());
    expect(screen.getByLabelText('material-calc-edit-c1')).toBeDisabled();
  });
});

describe('the button of the estimate (materials)', () => {
  function renderAction(onMessage = vi.fn(), onAdded = vi.fn(), message = null as never) {
    render(<I18nProvider><EstimateMaterialsAction projectId={projectId} estimateId="e1" message={message} onMessage={onMessage} onAdded={onAdded} /></I18nProvider>);
    return { onMessage, onAdded };
  }

  it('adds the materials, says how many, and has the estimate read again', async () => {
    vi.mocked(api.addMaterialsToEstimate).mockResolvedValue({ added: 4, already: 2, skipped: ['TILE_ADHESIVE'] });
    const { onMessage, onAdded } = renderAction();
    fireEvent.click(screen.getByLabelText('estimate-add-materials-action'));
    await waitFor(() => expect(onAdded).toHaveBeenCalledTimes(1));
    expect(api.addMaterialsToEstimate).toHaveBeenCalledWith(projectId, 'e1');
    expect(onMessage).toHaveBeenLastCalledWith({ kind: 'ok', text: 'Dodano pozycji: 4. Już w kosztorysie: 2. Pominięto: 1 (pozycja cennika w archiwum lub zmieniona jednostka).' });
  });

  it('says when there is nothing to add, and why a finished estimate refuses', async () => {
    vi.mocked(api.addMaterialsToEstimate).mockResolvedValueOnce({ added: 0, already: 0, skipped: [] });
    const { onMessage, onAdded } = renderAction();
    fireEvent.click(screen.getByLabelText('estimate-add-materials-action'));
    await waitFor(() => expect(onMessage).toHaveBeenLastCalledWith({ kind: 'ok', text: 'Nie ma materiałów do dodania. Dodaj obliczenia w pomieszczeniach.' }));
    expect(onAdded).not.toHaveBeenCalled();
    const { ApiError } = await import('../api/http');
    vi.mocked(api.addMaterialsToEstimate).mockRejectedValueOnce(new ApiError('x', 409, 'ESTIMATE_NOT_DRAFT'));
    fireEvent.click(screen.getByLabelText('estimate-add-materials-action'));
    await waitFor(() => expect(onMessage).toHaveBeenLastCalledWith({ kind: 'error', text: 'Pozycje można dodawać tylko do wersji roboczej kosztorysu.' }));
  });
});

describe('the trades of the owner (V2-13)', () => {
  const packages = () => ['TILE', 'DRYWALL', 'ELECTRIC', 'PLUMBING'].filter((p) => screen.queryByLabelText(`material-package-${p}`));

  it('offers only the packages of the trades that are on, and starts on the first of them', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING', 'DRYWALL', 'PLUMBING'] });
    renderSection();
    await open();
    await waitFor(() => expect(tradesApi.fetchTrades).toHaveBeenCalled());
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    await waitFor(() => expect(packages()).toEqual(['DRYWALL', 'PLUMBING']));
    expect(screen.getByLabelText('material-package-DRYWALL')).toHaveAttribute('aria-pressed', 'true'); // not on the tile: that trade is off
  });

  it('with every package trade off and no calculation the section is not there at all', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING', 'MICROCEMENT'] });
    vi.mocked(api.fetchCalcs).mockResolvedValue([]);
    renderSection();
    await waitFor(() => expect(api.fetchCalcs).toHaveBeenCalled()); // it looks once for calculations that must not be hidden
    await waitFor(() => expect(screen.queryByLabelText('room-materials-section')).toBeNull());
  });

  it('with every package trade off but a calculation already there the section stays, and a new one may take any package', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING'] });
    renderSection();
    await open();
    fireEvent.click(await screen.findByLabelText('material-calc-add'));
    await waitFor(() => expect(packages()).toEqual(['TILE', 'DRYWALL', 'ELECTRIC', 'PLUMBING']));
  });

  it('still lists the calculation of a package that is off', async () => {
    vi.mocked(tradesApi.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING'] });
    renderSection();
    await open();
    expect(await screen.findByLabelText('material-calc-edit-c1')).toBeInTheDocument();
  });
});
