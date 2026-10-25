import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/materials';
import * as itemsApi from '../api/priceItems';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { resetConnectionForTests } from '../offline/connection';
import type { MaterialNorm, Statement } from '../types/materials';
import { MaterialsScreen } from './MaterialsScreen';

vi.mock('../api/materials', () => ({
  fetchCalcs: vi.fn(),
  createCalc: vi.fn(),
  updateCalc: vi.fn(),
  deleteCalc: vi.fn(),
  fetchStatement: vi.fn(),
  fetchNorms: vi.fn(),
  updateNorm: vi.fn(),
  addMaterialsToEstimate: vi.fn(),
}));
vi.mock('../api/priceItems', () => ({ fetchPriceItems: vi.fn() }));

// V2-11 — the statement of the materials of an object and the owner's norms: the screen shows what the server sent and counts nothing.

const projectId = '11111111-1111-1111-1111-111111111111';
const STATEMENT: Statement = {
  calcs: [{
    id: 'c1', room_id: 'r1', room_name: 'Łazienka', package: 'TILE', title: 'Podłoga', materials: [], created_at: '', updated_at: '',
    params: { area_m2: '10.00', length_cm: '30.0', width_cm: '60.0' },
  }],
  totals: [
    { code: 'TILE_TILES', package: 'TILE', name: 'Płytki', quantity: '11.00', unit_text: 'm²', pack_size: null, packs: null, pieces: 62, billing_unit: 'M2', billing_quantity: '11.00', price_item_id: 'i1', unit_price: '89.00', amount: '979.00' },
    { code: 'TILE_ADHESIVE', package: 'TILE', name: 'Klej do płytek (worek)', quantity: '50.00', unit_text: 'kg', pack_size: '25', packs: 2, pieces: null, billing_unit: 'PCS', billing_quantity: '2.00', price_item_id: null, unit_price: null, amount: null },
  ],
  amount: '979.00',
  unpriced: 1,
};
const norm = (over: Partial<MaterialNorm>): MaterialNorm => ({
  id: 'n1', code: 'TILE_WASTE_STRAIGHT', package: 'TILE', kind: 'PARAM', name: 'TILE_WASTE_STRAIGHT', default_name: 'TILE_WASTE_STRAIGHT', unit_text: '%', value: '10', default_value: '10', minimum: '0', maximum: '100',
  billing_unit: null, price_item: null, ...over,
});
const NORMS: MaterialNorm[] = [
  norm({}),
  norm({ id: 'n2', code: 'TILE_ADHESIVE', kind: 'MATERIAL', name: 'Klej do płytek (worek)', default_name: 'Klej do płytek (worek)', value: null, default_value: null, minimum: null, maximum: null, unit_text: 'bag', billing_unit: 'PCS' }),
  norm({ id: 'n3', code: 'GK_WASTE', package: 'DRYWALL', value: '10', default_value: '10' }),
];
const ITEMS = [
  { id: 'p1', code: 'CUSTOM_A', name_key: null, display_name: 'Klej Atlas 25 kg', unit: 'PCS' },
  { id: 'p2', code: 'CUSTOM_B', name_key: null, display_name: 'Gres', unit: 'M2' },
];

function renderScreen() {
  return render(<I18nProvider><MaterialsScreen projectId={projectId} /></I18nProvider>);
}
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

beforeEach(() => {
  localStorage.setItem('locale', 'pl');
  vi.mocked(api.fetchStatement).mockResolvedValue(STATEMENT);
  vi.mocked(api.fetchNorms).mockResolvedValue(NORMS);
  vi.mocked(itemsApi.fetchPriceItems).mockResolvedValue({ items: ITEMS, total: 2 } as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  resetConnectionForTests();
});

describe('the statement of the materials of an object', () => {
  it('shows what to buy, the price of the tied item and "Do ustalenia" for the rest, and the sum the server counted', async () => {
    renderScreen();
    const tile = await screen.findByLabelText('material-total-TILE_TILES');
    expect(tile).toHaveTextContent('Płytki');
    expect(tile).toHaveTextContent('11 m²');
    expect(tile).toHaveTextContent('potrzeba 11 m² · 62 płytek');
    expect(screen.getByLabelText('material-price-TILE_TILES')).toHaveTextContent('89,00 zł / m² = 979,00 zł');
    expect(screen.getByLabelText('material-total-TILE_ADHESIVE')).toHaveTextContent('2 szt.');
    expect(screen.getByLabelText('material-price-TILE_ADHESIVE')).toHaveTextContent('Do ustalenia');
    const amount = screen.getByLabelText('materials-amount');
    expect(amount).toHaveTextContent('979,00 zł');
    expect(amount).toHaveTextContent('Bez ceny: 1');
    expect(screen.getByLabelText('materials-calcs')).toHaveTextContent('Łazienka · Podłoga');
    expect(screen.getByLabelText('materials-calcs')).toHaveTextContent('Płytki · 10 m² · 30×60 cm');
  });

  it('says there is nothing yet, and a failed read can be read again', async () => {
    vi.mocked(api.fetchStatement).mockRejectedValueOnce(new Error('down'));
    renderScreen();
    expect(await screen.findByText('Nie udało się wczytać obliczeń.')).toBeInTheDocument();
    vi.mocked(api.fetchStatement).mockResolvedValue({ calcs: [], totals: [], amount: null, unpriced: 0 });
    fireEvent.click(screen.getByLabelText('materials-retry'));
    expect(await screen.findByLabelText('materials-empty')).toHaveTextContent('Nie ma jeszcze żadnego obliczenia');
  });
});

describe('the norms of consumption', () => {
  async function openNorms() {
    renderScreen();
    fireEvent.click(await screen.findByLabelText('material-norms-toggle'));
    await screen.findByLabelText('material-norms-group-TILE');
  }

  it('asks the server for the norms only when they are opened, and shows the groups closed', async () => {
    renderScreen();
    await screen.findByLabelText('material-norms-toggle');
    expect(api.fetchNorms).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('material-norms-toggle'));
    await screen.findByLabelText('material-norms-group-TILE');
    expect(screen.queryByLabelText('material-norms-list-TILE')).toBeNull();
    fireEvent.click(screen.getByLabelText('material-norms-group-TILE'));
    expect(screen.getByLabelText('material-norms-list-TILE')).toBeInTheDocument();
    expect(screen.queryByLabelText('material-norm-GK_WASTE')).toBeNull();
  });

  it('changes a number (the point taken from a comma) and returns it to the starting one', async () => {
    vi.mocked(api.updateNorm).mockResolvedValueOnce(norm({ value: '12.5' }));
    await openNorms();
    fireEvent.click(screen.getByLabelText('material-norms-group-TILE'));
    const row = screen.getByLabelText('material-norm-TILE_WASTE_STRAIGHT');
    expect(row).toHaveTextContent('Zapas na docinanie płytek — układ prosty, %');
    expect(row).toHaveTextContent('Startowa: 10');
    expect(screen.getByLabelText('norm-save-TILE_WASTE_STRAIGHT')).toBeDisabled();
    expect(screen.getByLabelText('norm-reset-TILE_WASTE_STRAIGHT')).toBeDisabled();
    type('norm-TILE_WASTE_STRAIGHT', '12,5');
    fireEvent.click(screen.getByLabelText('norm-save-TILE_WASTE_STRAIGHT'));
    await waitFor(() => expect(api.updateNorm).toHaveBeenCalledWith('n1', { value: '12.5' }));
    await waitFor(() => expect(screen.getByLabelText('norm-reset-TILE_WASTE_STRAIGHT')).toBeEnabled());
    vi.mocked(api.updateNorm).mockResolvedValueOnce(norm({}));
    fireEvent.click(screen.getByLabelText('norm-reset-TILE_WASTE_STRAIGHT'));
    await waitFor(() => expect(api.updateNorm).toHaveBeenLastCalledWith('n1', { reset: true }));
  });

  it('refuses a number that is not one, and says what the server refused', async () => {
    await openNorms();
    fireEvent.click(screen.getByLabelText('material-norms-group-TILE'));
    type('norm-TILE_WASTE_STRAIGHT', 'abc');
    fireEvent.click(screen.getByLabelText('norm-save-TILE_WASTE_STRAIGHT'));
    expect(await screen.findByText('Liczba poza dopuszczalnym zakresem.')).toBeInTheDocument();
    expect(api.updateNorm).not.toHaveBeenCalled();
    vi.mocked(api.updateNorm).mockRejectedValueOnce(new ApiError('x', 422, 'NORM_OUT_OF_RANGE'));
    type('norm-TILE_WASTE_STRAIGHT', '500');
    fireEvent.click(screen.getByLabelText('norm-save-TILE_WASTE_STRAIGHT'));
    await waitFor(() => expect(api.updateNorm).toHaveBeenCalledWith('n1', { value: '500' }));
    expect(await screen.findByText('Liczba poza dopuszczalnym zakresem.')).toBeInTheDocument();
  });

  it('ties a material to the price item of its unit and unties it', async () => {
    vi.mocked(api.updateNorm).mockResolvedValueOnce(norm({ id: 'n2', code: 'TILE_ADHESIVE', kind: 'MATERIAL', name: 'Klej Atlas', default_name: 'Klej do płytek (worek)', value: null, billing_unit: 'PCS',
      price_item: { id: 'p1', code: 'CUSTOM_A', name_key: null, display_name: 'Klej Atlas 25 kg', category: 'MATERIAL', unit: 'PCS', price: '42.50', is_archived: false } }));
    await openNorms();
    fireEvent.click(screen.getByLabelText('material-norms-group-TILE'));
    const select = screen.getByLabelText('norm-item-TILE_ADHESIVE');
    expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toEqual(['— bez ceny —', 'Klej Atlas 25 kg']); // the item in m2 is not offered
    fireEvent.change(select, { target: { value: 'p1' } });
    type('norm-name-TILE_ADHESIVE', ' Klej Atlas ');
    fireEvent.click(screen.getByLabelText('norm-save-TILE_ADHESIVE'));
    await waitFor(() => expect(api.updateNorm).toHaveBeenCalledWith('n2', { name: 'Klej Atlas', price_item_id: 'p1' }));
    await waitFor(() => expect((screen.getByLabelText('norm-item-TILE_ADHESIVE') as HTMLSelectElement).value).toBe('p1'));
    expect(within(screen.getByLabelText('material-norm-TILE_ADHESIVE')).getByLabelText('norm-reset-TILE_ADHESIVE')).toBeEnabled();
  });

  it('says why a material cannot be tied to an item of another unit', async () => {
    vi.mocked(api.updateNorm).mockRejectedValueOnce(new ApiError('x', 422, 'NORM_ITEM_UNIT_MISMATCH'));
    await openNorms();
    fireEvent.click(screen.getByLabelText('material-norms-group-TILE'));
    fireEvent.change(screen.getByLabelText('norm-item-TILE_ADHESIVE'), { target: { value: 'p1' } });
    fireEvent.click(screen.getByLabelText('norm-save-TILE_ADHESIVE'));
    expect(await screen.findByText('Jednostka tej pozycji nie pasuje do materiału.')).toBeInTheDocument();
  });
});
