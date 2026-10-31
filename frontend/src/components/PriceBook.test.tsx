import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as coefficientsApi from '../api/coefficients';
import * as priceItemsApi from '../api/priceItems';
import { I18nProvider } from '../hooks/useI18n';
import { PriceItem } from '../types/priceItem';
import { PriceBook } from './PriceBook';

vi.mock('../api/priceItems', () => ({
  fetchPriceItems: vi.fn(),
  createPriceItem: vi.fn(),
  updatePriceItem: vi.fn(),
  archivePriceItem: vi.fn(),
  restorePriceItem: vi.fn(),
}));

vi.mock('../api/coefficients', () => ({
  fetchCoefficientGroups: vi.fn(),
}));

const seedPrep: PriceItem = {
  id: 'item-1',
  code: 'CENNIK_PREP_WALLP-01',
  name_key: 'pricebook.seed.prep_wallp',
  display_name: null,
  category: 'PREPARATION',
  unit: 'M2',
  price: '1.11',
  currency: 'PLN',
  price_scope: 'LABOR',
  quality_level: null,
  is_archived: false,
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
};

const seedPaint: PriceItem = {
  id: 'item-2',
  code: 'CENNIK_PAINT_2K-01',
  name_key: 'pricebook.seed.paint_2k',
  display_name: null,
  category: 'PAINTING',
  unit: 'M2',
  price: '2.22',
  currency: 'PLN',
  price_scope: 'LABOR',
  quality_level: null,
  is_archived: false,
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
};

const custom: PriceItem = {
  id: 'item-3',
  code: 'CUSTOM_AB1234CD5678',
  name_key: null,
  display_name: 'Malowanie lateksowe dwukrotnie',
  category: 'PAINTING',
  unit: 'M2',
  price: '9.99',
  currency: 'PLN',
  price_scope: 'LABOR_AND_MATERIAL',
  quality_level: 'Q3',
  is_archived: false,
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
};

const flatItem: PriceItem = {
  id: 'item-5',
  code: 'CUSTOM_FLAT00AABB',
  name_key: null,
  display_name: 'Sprzątanie po remoncie',
  category: 'OTHER',
  unit: 'FLAT',
  price: '250',
  currency: 'PLN',
  price_scope: 'LABOR',
  quality_level: null,
  is_archived: false,
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
};

const archived: PriceItem = {
  id: 'item-4',
  code: 'CUSTOM_ARCH0000FFFF',
  name_key: null,
  display_name: 'Praca sprzed roku',
  category: 'PAINTING',
  unit: 'LM',
  price: '5.55',
  currency: 'PLN',
  price_scope: 'LABOR',
  quality_level: null,
  is_archived: true,
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
};

function renderHub() {
  return render(
    <I18nProvider>
      <PriceBook />
    </I18nProvider>,
  );
}

// The price opens as a hub of three tiles (16K.6): most tests are about the positions, so they go through that tile.
function renderBook() {
  const view = renderHub();
  fireEvent.click(screen.getByLabelText('pricebook-maintab-items'));
  return view;
}

describe('PriceBook — list and cards', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
  });

  it('keeps the price screen readable on a phone and in the dark theme (Stage 16K.4, 16K.6): theme title, 44 px tiles and controls', async () => {
    renderHub();
    await screen.findByLabelText('pricebook-hub');
    expect(screen.queryByRole('heading', { name: 'Cennik' })).toBeNull(); // the header of the application names the section (usability U-2)
    for (const name of ['pricebook-maintab-items', 'pricebook-maintab-coefficients', 'pricebook-maintab-processes']) {
      expect(screen.getByLabelText(name).className).toContain('min-h-14');
    }
    fireEvent.click(screen.getByLabelText('pricebook-maintab-items'));
    for (const name of ['back-to-pricebook', 'pricebook-tab-active', 'pricebook-tab-archived', 'pricebook-search', 'pricebook-category-filter', 'add-price-item']) {
      expect(screen.getByLabelText(name).className).toContain('min-h-11');
    }
  });

  it('opens as a hub of three tiles: positions, coefficients, processes — and loads nothing until one is opened (16K.6)', async () => {
    renderHub();
    const hub = await screen.findByLabelText('pricebook-hub');
    expect(Array.from(hub.children).map((tile) => tile.textContent?.replace('›', '').replace(/\p{Extended_Pictographic}️?/gu, '').trim())).toEqual(['Pozycje cennika', 'Współczynniki', 'Procesy']);
    expect(screen.queryByLabelText('pricebook-tabs')).toBeNull();
    expect(screen.queryByLabelText('add-price-item')).toBeNull();
    expect(priceItemsApi.fetchPriceItems).not.toHaveBeenCalled();
    expect(coefficientsApi.fetchCoefficientGroups).not.toHaveBeenCalled();
  });

  it('a tile opens its screen with the way back: "Cennik / Pozycje cennika", the count, and the hub again (16K.6)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [seedPrep], total: 7 });
    renderHub();
    fireEvent.click(await screen.findByLabelText('pricebook-maintab-items'));
    const nav = await screen.findByLabelText('pricebook-navigation');
    expect(nav.textContent).toContain('Cennik');
    expect(nav.textContent).toContain('Pozycje cennika');
    await waitFor(() => expect(nav.textContent).toContain('7'));
    expect(screen.queryByLabelText('pricebook-hub')).toBeNull();
    fireEvent.click(screen.getByLabelText('back-to-pricebook'));
    expect(screen.getByLabelText('pricebook-hub')).toBeInTheDocument();
  });

  it('the Telegram BackButton leads from a screen of the price back to the hub, and the menu returns to the hub too (16K.6)', async () => {
    let handler: (() => void) | undefined;
    (window as unknown as { Telegram: unknown }).Telegram = {
      WebApp: { BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn((cb: () => void) => { handler = cb; }), offClick: vi.fn() } },
    };
    const view = renderHub();
    fireEvent.click(await screen.findByLabelText('pricebook-maintab-processes'));
    expect(handler).toBeDefined();
    act(() => handler?.());
    expect(screen.getByLabelText('pricebook-hub')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('pricebook-maintab-items'));
    view.rerender(<I18nProvider><PriceBook resetSignal={1} /></I18nProvider>);
    expect(screen.getByLabelText('pricebook-hub')).toBeInTheDocument();
    delete (window as unknown as { Telegram?: unknown }).Telegram;
  });

  it('renders the initial active catalog with localized seed names', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedPrep, seedPaint, custom],
      total: 3,
    });
    renderBook();

    expect(await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)')).toBeInTheDocument();
    expect(screen.getByText('Malowanie ścian — 2 warstwy (standard)')).toBeInTheDocument();
    expect(screen.getByText('Malowanie lateksowe dwukrotnie')).toBeInTheDocument();
    expect(priceItemsApi.fetchPriceItems).toHaveBeenCalledWith(
      expect.objectContaining({ archived: 'active' }),
    );
  });

  it('emphasizes price and unit with comma decimals and the PLN symbol', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [flatItem, seedPrep],
      total: 2,
    });
    renderBook();

    await screen.findByText('Sprzątanie po remoncie');
    expect(screen.getByText('250,00 zł')).toBeInTheDocument();
    expect(screen.getByText(/ryczałt/)).toBeInTheDocument();
    expect(screen.getByText('1,11 zł')).toBeInTheDocument();
    expect(screen.getByText(/ m²/)).toBeInTheDocument();
  });

  it('never shows machine code, name_key, or internal ids', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedPrep, custom],
      total: 2,
    });
    renderBook();

    await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)');
    expect(screen.queryByText(/CENNIK_PREP_WALLP-01/)).not.toBeInTheDocument();
    expect(screen.queryByText(/pricebook\.seed\./)).not.toBeInTheDocument();
    expect(screen.queryByText(/CUSTOM_AB1234CD5678/)).not.toBeInTheDocument();
    expect(screen.queryByText(/item-1/)).not.toBeInTheDocument();
  });

  it('shows quality level and non-default scope labels on the card', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [custom],
      total: 1,
    });
    renderBook();

    await screen.findByText('Malowanie lateksowe dwukrotnie');
    fireEvent.click(screen.getByLabelText(`price-item-toggle-${custom.id}`)); // owner 2026-10-31: in the details of the line
    expect(screen.getByText('Klasa Q3')).toBeInTheDocument();
    expect(screen.getByText(/Robocizna i materiał/)).toBeInTheDocument();
  });

  it('does not render the Archived tab items in the active view', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedPrep, custom],
      total: 2,
    });
    renderBook();

    await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)');
    expect(screen.queryByText('Praca sprzed roku')).not.toBeInTheDocument();
  });

  it('a very long PL name is rendered in full (wraps, no truncate on the card name)', async () => {
    const longName =
      'Szpachlowanie gładzią gipsową całopowierzchniowo z przeszlifowaniem pod oświetlenie smugowe';
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [{ ...custom, display_name: longName }],
      total: 1,
    });
    renderBook();

    const name = await screen.findByText(longName);
    expect(name).toBeInTheDocument();
    expect(name.className).not.toContain('truncate');
  });

  it('localizes the catalog in RU', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedPrep, custom],
      total: 2,
    });
    renderBook();

    expect(await screen.findByText('Снятие обоев (сдирание, утилизация)')).toBeInTheDocument();
    expect(screen.getByText('Прайс')).toBeInTheDocument();
    expect(screen.getByText('9,99 zł')).toBeInTheDocument();
  });
});

describe('PriceBook — filters', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
  });

  it('searches the names the owner sees, not the server (UX walk A1: catalogue rows have only a key)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [seedPrep, seedPaint, custom], total: 3 });
    renderBook();
    await screen.findByLabelText('price-item-item-1');
    fireEvent.change(screen.getByLabelText('pricebook-search'), { target: { value: 'tapet' } });
    expect(screen.getByLabelText('price-item-item-1')).toBeInTheDocument();
    expect(screen.queryByLabelText('price-item-item-2')).toBeNull();
    expect(priceItemsApi.fetchPriceItems).not.toHaveBeenCalledWith(expect.objectContaining({ search: expect.anything() }));
    // without the Polish letters, and two words in any order
    fireEvent.change(screen.getByLabelText('pricebook-search'), { target: { value: 'scian malowanie' } });
    expect(screen.getByLabelText('price-item-item-2')).toBeInTheDocument();
    expect(screen.queryByLabelText('price-item-item-1')).toBeNull();
    // the owner's own name and the code still count
    fireEvent.change(screen.getByLabelText('pricebook-search'), { target: { value: 'lateks' } });
    expect(screen.getByLabelText('price-item-item-3')).toBeInTheDocument();
    expect(screen.queryByLabelText('price-item-item-2')).toBeNull();
    fireEvent.change(screen.getByLabelText('pricebook-search'), { target: { value: 'nic takiego' } });
    expect(screen.queryByLabelText('pricebook-list')).toBeNull();
  });

  it('finds a catalogue row by its Russian name, and by its Polish one on a Russian screen', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [seedPrep, seedPaint], total: 2 });
    renderBook();
    await screen.findByLabelText('price-item-item-2');
    fireEvent.change(screen.getByLabelText('pricebook-search'), { target: { value: 'покраска' } });
    expect(screen.getByLabelText('price-item-item-2')).toBeInTheDocument();
    expect(screen.queryByLabelText('price-item-item-1')).toBeNull();
    fireEvent.change(screen.getByLabelText('pricebook-search'), { target: { value: 'tapety' } });
    expect(screen.queryByLabelText('price-item-item-1')).toBeNull(); // "tapety" is not in "tapet (zdzieranie" -- a word must be contained
    fireEvent.change(screen.getByLabelText('pricebook-search'), { target: { value: 'tapet' } });
    expect(screen.getByLabelText('price-item-item-1')).toBeInTheDocument();
  });

  it('requests the backend category filter', async () => {
    renderBook();
    fireEvent.change(screen.getByLabelText('pricebook-category-filter'), {
      target: { value: 'PAINTING' },
    });
    await waitFor(() =>
      expect(priceItemsApi.fetchPriceItems).toHaveBeenLastCalledWith(
        expect.objectContaining({ category: 'PAINTING' }),
      ),
    );
  });

  it('switches to the Archived tab and shows archived-only items', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems)
      .mockResolvedValueOnce({ items: [seedPrep], total: 1 })
      .mockResolvedValueOnce({ items: [archived], total: 1 });
    renderBook();

    fireEvent.click(await screen.findByLabelText('pricebook-tab-archived'));
    expect(await screen.findByText('Praca sprzed roku')).toBeInTheDocument();
    expect(priceItemsApi.fetchPriceItems).toHaveBeenLastCalledWith(
      expect.objectContaining({ archived: 'archived' }),
    );
    expect(screen.getByText('Zarchiwizowana')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(`price-item-toggle-${archived.id}`));
    expect(screen.getByLabelText(`restore-price-item-${archived.id}`)).toBeInTheDocument();
  });
});

describe('PriceBook — create custom item', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(custom);
  });

  it('creates a custom item with a normalized price and renders the server item', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems)
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({ items: [custom], total: 1 });
    renderBook();

    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Malowanie lateksowe dwukrotnie' },
    });
    fireEvent.change(screen.getByLabelText('price-item-price'), {
      target: { value: '45,5' },
    });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    await waitFor(() =>
      expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
        expect.objectContaining({
          display_name: 'Malowanie lateksowe dwukrotnie',
          price: '45.5',
          category: 'PREPARATION',
          unit: 'M2',
          price_scope: 'LABOR',
        }),
      ),
    );
    expect(await screen.findByText('Malowanie lateksowe dwukrotnie')).toBeInTheDocument();
  });

  it('never reveals the server-generated code', async () => {
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Nowa pozycja' },
    });
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: '10' } });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    await waitFor(() => expect(priceItemsApi.createPriceItem).toHaveBeenCalled());
    expect(screen.queryByText(/CUSTOM_AB1234CD5678/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/code/i)).not.toBeInTheDocument();
  });
});

describe('PriceBook — edit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValue(custom);
  });

  async function openEdit(itemLabel: string) {
    fireEvent.click(await screen.findByLabelText(`edit-price-item-${itemLabel}`));
  }

  it('opens the full form for a custom row (not the inline catalog editor)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [custom],
      total: 1,
    });
    renderBook();
    await openEdit('item-3');

    expect(screen.getByLabelText('price-item-form')).toBeInTheDocument();
    expect(screen.getByLabelText('price-item-display-name')).toHaveValue(
      'Malowanie lateksowe dwukrotnie',
    );
    expect(screen.getByLabelText('price-item-price')).toHaveValue('9.99');
    expect(screen.queryByLabelText('inline-price-edit-item-3')).not.toBeInTheDocument();
  });

  it('submits edited price and name for a custom row', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [custom],
      total: 1,
    });
    renderBook();
    await openEdit('item-3');

    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Farby lateksowe' },
    });
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: '3.33' } });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith(
        'item-3',
        expect.objectContaining({ display_name: 'Farby lateksowe', price: '3.33' }),
      ),
    );
  });

  it('keeps the unit, category and quality editable on a custom row', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [custom],
      total: 1,
    });
    renderBook();
    await openEdit('item-3');

    const form = screen.getByLabelText('price-item-form');
    expect(within(form).getByLabelText('price-item-unit')).toHaveValue('M2');
    expect(within(form).getByLabelText('price-item-category')).toHaveValue('PAINTING');
    expect(within(form).getByLabelText('price-item-quality')).toHaveValue('Q3');

    fireEvent.change(within(form).getByLabelText('price-item-unit'), {
      target: { value: 'LM' },
    });
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: '3.33' } });
    fireEvent.submit(form);

    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith(
        'item-3',
        expect.objectContaining({ unit: 'LM' }),
      ),
    );
  });

  it('rejects a blank name on a custom row without calling the API', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [custom],
      total: 1,
    });
    renderBook();
    await openEdit('item-3');

    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: '   ' },
    });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    expect(screen.getByText('Pozycja własna wymaga nazwy.')).toBeInTheDocument();
    expect(priceItemsApi.updatePriceItem).not.toHaveBeenCalled();
  });
});

describe('PriceBook — a catalogue row in the one form of every item (owner 2026-10-31)', () => {
  const zeroCatalog: PriceItem = {
    id: 'item-6',
    code: 'CENNIK_PRIM_STD-01',
    name_key: 'pricebook.seed.prim_std',
    display_name: null,
    category: 'PREPARATION',
    unit: 'M2',
    price: '0.00',
    currency: 'PLN',
    price_scope: 'LABOR',
    quality_level: null,
    is_archived: false,
    created_at: '2026-09-13T10:00:00Z',
    updated_at: '2026-09-13T10:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValue(seedPrep);
  });

  it('opens the same form as an own row, right under the line, with the catalogue name kept by an empty field', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [seedPrep, custom], total: 2 });
    renderBook();
    await screen.findByText('Usuwanie tapet (zdzieranie, utylizacja)');

    fireEvent.click(screen.getByLabelText('edit-price-item-item-1'));

    const form = screen.getByLabelText('price-item-form');
    expect(within(screen.getByLabelText('price-item-item-1')).getByLabelText('price-item-form')).toBe(form); // under its own line
    expect(within(form).getByLabelText('price-item-display-name')).toHaveValue('');
    expect(within(form).getByLabelText('price-item-display-name')).toHaveAttribute('placeholder', 'Usuwanie tapet (zdzieranie, utylizacja)');
    expect(within(form).getByText('Puste pole = nazwa z katalogu.')).toBeInTheDocument();
    // the category and the unit of a catalogue row are fixed
    expect(within(form).getByLabelText('price-item-unit').tagName).toBe('P');
    expect(within(form).getByLabelText('price-item-category').tagName).toBe('P');
    expect(within(form).getByLabelText('price-item-price')).toHaveValue('1.11');
  });

  it('saves the price with the catalogue name kept (an empty name) and keeps an explicit 0.00 a payable zero', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [zeroCatalog], total: 1 });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValue(zeroCatalog);
    renderBook();
    fireEvent.click(await screen.findByLabelText('edit-price-item-item-6'));
    expect(screen.getByLabelText('price-item-price')).toHaveValue('0.00');
    fireEvent.submit(screen.getByLabelText('price-item-form'));
    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith('item-6', expect.objectContaining({ price: '0.00', display_name: '', unit: 'M2', category: 'PREPARATION' })),
    );
    await waitFor(() => expect(screen.queryByLabelText('price-item-form')).toBeNull());
  });

  it('cancels without any API call', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [seedPrep], total: 1 });
    renderBook();
    fireEvent.click(await screen.findByLabelText('edit-price-item-item-1'));
    fireEvent.click(within(screen.getByLabelText('price-item-form')).getByRole('button', { name: /Anuluj/ }));
    expect(screen.queryByLabelText('price-item-form')).toBeNull();
    expect(priceItemsApi.updatePriceItem).not.toHaveBeenCalled();
  });

  it('blocks a malformed price', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [seedPrep], total: 1 });
    renderBook();
    fireEvent.click(await screen.findByLabelText('edit-price-item-item-1'));
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: '12,345' } });
    fireEvent.submit(screen.getByLabelText('price-item-form'));
    expect(priceItemsApi.updatePriceItem).not.toHaveBeenCalled();
  });

  it('offers restore only (no edit) on an archived catalogue row, in its details', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [{ ...seedPrep, is_archived: true }], total: 1 });
    renderBook();
    fireEvent.click(await screen.findByLabelText('price-item-toggle-item-1'));
    expect(screen.getByLabelText('restore-price-item-item-1')).toBeInTheDocument();
    expect(screen.queryByLabelText('edit-price-item-item-1')).toBeNull();
  });

  it('is one line per item -- name, price, ✏️ -- and a tap opens the details (owner 2026-10-31)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [seedPrep], total: 1 });
    renderBook();
    const toggle = await screen.findByLabelText('price-item-toggle-item-1');
    expect(toggle).toHaveClass('min-h-11');
    expect(screen.getByLabelText('price-item-price-item-1')).toHaveTextContent('1,11 zł');
    expect(screen.queryByLabelText('price-item-details-item-1')).toBeNull();
    expect(screen.queryByLabelText('archive-price-item-item-1')).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByLabelText('price-item-details-item-1')).toBeInTheDocument();
    expect(screen.getByLabelText('archive-price-item-item-1')).toBeInTheDocument();
    expect(screen.getByLabelText('edit-price-item-item-1')).toHaveClass('min-h-11', 'min-w-11');
  });
});

describe('PriceBook — form labels (Stage 9E.8)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
  });

  async function openForm() {
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    return screen.getByLabelText('price-item-form');
  }

  it('labels the name field "Nazwa pozycji", the category "Kategoria" and the scope "Cena obejmuje" in PL', async () => {
    renderBook();
    const form = await openForm();

    expect(within(form).getByText('Nazwa pozycji')).toBeInTheDocument();
    expect(within(form).getByText('Kategoria')).toBeInTheDocument();
    expect(within(form).getByText('Cena obejmuje')).toBeInTheDocument();
  });

  it('labels the name field "Название позиции", the category "Категория" and the scope "Цена включает" in RU', async () => {
    localStorage.setItem('locale', 'ru');
    renderBook();
    const form = await openForm();

    expect(within(form).getByText('Название позиции')).toBeInTheDocument();
    expect(within(form).getByText('Категория')).toBeInTheDocument();
    expect(within(form).getByText('Цена включает')).toBeInTheDocument();
  });

  it('does not infer an S or Q quality class from the selected category', async () => {
    renderBook();
    const form = await openForm();

    const quality = within(form).getByLabelText('price-item-quality');
    expect(quality).toHaveValue('');

    fireEvent.change(within(form).getByLabelText('price-item-category'), {
      target: { value: 'SKIM_COAT' },
    });
    expect(within(form).getByLabelText('price-item-quality')).toHaveValue('');
  });

  it('groups the S and Q quality options under separate, explained groups', async () => {
    renderBook();
    const form = await openForm();

    const quality = within(form).getByLabelText('price-item-quality');
    const groups = quality.querySelectorAll('optgroup');
    expect(groups).toHaveLength(2);
    expect(groups[0]).toHaveAttribute('label', 'Klasy S — tynki, beton');
    expect(groups[1]).toHaveAttribute('label', 'Klasy Q — płyty g-k');
    expect(form).toHaveTextContent(
      'Klasy S i Q zależą od rodzaju podłoża i systemu. Wybierz klasę tylko wtedy, gdy jest ustalona.',
    );
  });
});

describe('PriceBook — opened form visibility (Stage 9E.7.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValue(custom);
  });

  // jsdom does not implement scrollIntoView; the component guards the call, so
  // stub it to observe that opening the form actually brings it into view.
  function stubScrollIntoView() {
    const spy = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = spy;
    return {
      spy,
      restore: () => {
        Element.prototype.scrollIntoView = original;
      },
    };
  }

  it('scrolls the form into view when Edit is tapped on a custom row', async () => {
    const { spy, restore } = stubScrollIntoView();
    try {
      vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
        items: [custom],
        total: 1,
      });
      renderBook();
      await screen.findByText('Malowanie lateksowe dwukrotnie');
      expect(spy).not.toHaveBeenCalled();

      fireEvent.click(screen.getByLabelText('edit-price-item-item-3'));

      const form = screen.getByLabelText('price-item-form');
      await waitFor(() =>
        expect(spy).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' }),
      );
      expect(spy.mock.instances[0]).toBe(form);
    } finally {
      restore();
    }
  });

  it('also scrolls the form into view when Add is tapped', async () => {
    const { spy, restore } = stubScrollIntoView();
    try {
      renderBook();
      await screen.findByLabelText('add-price-item');
      expect(spy).not.toHaveBeenCalled();

      fireEvent.click(screen.getByLabelText('add-price-item'));

      await waitFor(() =>
        expect(spy).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' }),
      );
    } finally {
      restore();
    }
  });
});

describe('PriceBook — money input contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue(custom);
  });

  async function openCreateWithPrice(price: string, name = 'Pozycja testowa') {
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: name },
    });
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: price } });
    fireEvent.submit(screen.getByLabelText('price-item-form'));
  }

  it.each(['45', '45.5', '45.50', '0', '0.00', '45,5', '45,50'])(
    'accepts "%s" and submits the canonical value',
    async (raw) => {
      const expected =
        raw === '45,5' ? '45.5' : raw === '45,50' ? '45.50' : raw;
      renderBook();
      await openCreateWithPrice(raw);
      await waitFor(() =>
        expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
          expect.objectContaining({ price: expected }),
        ),
      );
    },
  );

  it.each(['45.555', '45,555'])(
    'shows an inline precision error for "%s" and never calls the API',
    async (raw) => {
      renderBook();
      await openCreateWithPrice(raw);
      expect(
        await screen.findByText('Maksymalnie 2 miejsca po przecinku.'),
      ).toBeInTheDocument();
      expect(priceItemsApi.createPriceItem).not.toHaveBeenCalled();
    },
  );

  it('rejects a negative price inline without an API call', async () => {
    renderBook();
    await openCreateWithPrice('-5');
    expect(
      await screen.findByText('Cena nie może być ujemna.'),
    ).toBeInTheDocument();
    expect(priceItemsApi.createPriceItem).not.toHaveBeenCalled();
  });

  it('rejects malformed text inline without an API call', async () => {
    renderBook();
    await openCreateWithPrice('abc');
    expect(await screen.findByText('Wpisz poprawną cenę.')).toBeInTheDocument();
    expect(priceItemsApi.createPriceItem).not.toHaveBeenCalled();
  });

  it('disables the save button while the price is invalid', async () => {
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: '45.555' } });
    expect(screen.getByRole('button', { name: 'Zapisz' })).toBeDisabled();
  });

  it('prompts for a required price on an empty create without an API call', async () => {
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Bez ceny' },
    });
    fireEvent.submit(screen.getByLabelText('price-item-form'));
    expect(await screen.findByText('Podaj cenę.')).toBeInTheDocument();
    expect(priceItemsApi.createPriceItem).not.toHaveBeenCalled();
  });
});

describe('PriceBook — archive / restore lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(priceItemsApi.archivePriceItem).mockResolvedValue(archived);
    vi.mocked(priceItemsApi.restorePriceItem).mockResolvedValue(custom);
  });

  it('archives directly from the card and removes the item from the active view', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems)
      .mockResolvedValueOnce({ items: [seedPrep, custom], total: 2 })
      .mockResolvedValueOnce({ items: [seedPrep], total: 1 });
    renderBook();

    fireEvent.click(await screen.findByLabelText(`price-item-toggle-${custom.id}`));
    fireEvent.click(screen.getByLabelText(`archive-price-item-${custom.id}`));

    await waitFor(() =>
      expect(priceItemsApi.archivePriceItem).toHaveBeenCalledWith(custom.id),
    );
    await waitFor(() =>
      expect(screen.queryByText('Malowanie lateksowe dwukrotnie')).not.toBeInTheDocument(),
    );
    expect(screen.getByText('Usuwanie tapet (zdzieranie, utylizacja)')).toBeInTheDocument();
  });

  it('restores from the Archived tab back to the active list', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems)
      .mockResolvedValueOnce({ items: [seedPrep], total: 1 })
      .mockResolvedValueOnce({ items: [archived], total: 1 })
      .mockResolvedValueOnce({ items: [], total: 0 });
    renderBook();

    fireEvent.click(await screen.findByLabelText('pricebook-tab-archived'));
    fireEvent.click(await screen.findByLabelText(`price-item-toggle-${archived.id}`));
    const restore = await screen.findByLabelText(`restore-price-item-${archived.id}`);
    fireEvent.click(restore);

    await waitFor(() =>
      expect(priceItemsApi.restorePriceItem).toHaveBeenCalledWith(archived.id),
    );
    expect(await screen.findByText('Brak zarchiwizowanych pozycji')).toBeInTheDocument();
  });
});

describe('PriceBook — localized error states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('shows a localized load error without leaking status text', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockRejectedValueOnce(
      new Error('Failed to fetch price items: 500'),
    );
    renderBook();

    expect(await screen.findByText('Nie udało się wczytać cennika.')).toBeInTheDocument();
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();
  });

  it('shows a localized save error without leaking status text', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(priceItemsApi.createPriceItem).mockRejectedValueOnce(
      new Error('Failed to create price item: 422'),
    );
    renderBook();

    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Nieudana pozycja' },
    });
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: '10' } });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    expect(await screen.findByText('Nie udało się zapisać pozycji.')).toBeInTheDocument();
    expect(screen.queryByText(/422/)).not.toBeInTheDocument();
  });

  it('shows a localized archive failure', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [custom],
      total: 1,
    });
    vi.mocked(priceItemsApi.archivePriceItem).mockRejectedValueOnce(
      new Error('Failed to archive price item: 500'),
    );
    renderBook();

    fireEvent.click(await screen.findByLabelText(`price-item-toggle-${custom.id}`));
    fireEvent.click(screen.getByLabelText(`archive-price-item-${custom.id}`));

    expect(await screen.findByText('Nie udało się zarchiwizować pozycji.')).toBeInTheDocument();
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Stage 10G.4 — explicit "Cena do ustalenia" (unresolved price) toggle
// ---------------------------------------------------------------------------

describe('PriceBook — Cena do ustalenia toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue({ ...custom, price: null });
  });

  it('is unchecked by default and requires a numeric price', async () => {
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    expect(screen.getByLabelText('price-item-price-unresolved')).not.toBeChecked();
    expect(screen.getByLabelText('price-item-price')).toBeInTheDocument();
  });

  it('checking it hides the numeric price input and sends price: null', async () => {
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Szpachlowanie ościeży' },
    });

    fireEvent.click(screen.getByLabelText('price-item-price-unresolved'));
    expect(screen.queryByLabelText('price-item-price')).toBeNull();

    fireEvent.submit(screen.getByLabelText('price-item-form'));

    await waitFor(() =>
      expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
        expect.objectContaining({ price: null }),
      ),
    );
  });

  it('an explicit 0.00 still sends a real zero, never null', async () => {
    vi.mocked(priceItemsApi.createPriceItem).mockResolvedValue({ ...custom, price: '0.00' });
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Zero cenowe' },
    });
    fireEvent.change(screen.getByLabelText('price-item-price'), { target: { value: '0.00' } });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    await waitFor(() =>
      expect(priceItemsApi.createPriceItem).toHaveBeenCalledWith(
        expect.objectContaining({ price: '0.00' }),
      ),
    );
  });

  it('an empty numeric price without the toggle remains a validation error, never sent as null', async () => {
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Bez ceny' },
    });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    expect(await screen.findByText('Podaj cenę.')).toBeInTheDocument();
    expect(priceItemsApi.createPriceItem).not.toHaveBeenCalled();
  });

  it('switching the toggle back off restores the numeric-price requirement', async () => {
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.change(screen.getByLabelText('price-item-display-name'), {
      target: { value: 'Praca' },
    });

    const toggle = screen.getByLabelText('price-item-price-unresolved');
    fireEvent.click(toggle); // on — price hidden
    fireEvent.click(toggle); // off — price required again
    expect(screen.getByLabelText('price-item-price')).toBeInTheDocument();

    fireEvent.submit(screen.getByLabelText('price-item-form'));
    expect(await screen.findByText('Podaj cenę.')).toBeInTheDocument();
    expect(priceItemsApi.createPriceItem).not.toHaveBeenCalled();
  });

  it('an existing custom item with price=null opens the edit form pre-checked "Cena do ustalenia"', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [{ ...custom, price: null }],
      total: 1,
    });
    renderBook();
    fireEvent.click(await screen.findByLabelText(`edit-price-item-${custom.id}`));

    expect(screen.getByLabelText('price-item-price-unresolved')).toBeChecked();
    expect(screen.queryByLabelText('price-item-price')).toBeNull();
  });

  it('explicitly re-checking "Cena do ustalenia" on an already-priced custom item clears it back to null via PATCH', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [custom],
      total: 1,
    });
    vi.mocked(priceItemsApi.updatePriceItem).mockResolvedValue({ ...custom, price: null });
    renderBook();
    fireEvent.click(await screen.findByLabelText(`edit-price-item-${custom.id}`));

    fireEvent.click(screen.getByLabelText('price-item-price-unresolved'));
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith(
        custom.id,
        expect.objectContaining({ price: null }),
      ),
    );
  });

  it('labels the toggle "Cena do ustalenia" in PL and "Цена уточняется" in RU', async () => {
    renderBook();
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    expect(screen.getByText('Cena do ustalenia')).toBeInTheDocument();

    localStorage.setItem('locale', 'ru');
    renderBook();
    fireEvent.click((await screen.findAllByLabelText('add-price-item'))[1]);
    expect(screen.getByText('Цена уточняется')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Stage 10G.4 — localized LM unit label on the Cennik card
// ---------------------------------------------------------------------------

describe('PriceBook — localized LM unit label', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders an LM item as "mb" on the card, never raw "LM"', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [archived],
      total: 1,
    });
    renderBook();
    const card = await screen.findByLabelText(`price-item-${archived.id}`);
    expect(card.textContent).toContain('mb');
    expect(card.textContent).not.toMatch(/\bLM\b/);
  });
});
describe('PriceBook — coefficient tab (Stage 12F)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(coefficientsApi.fetchCoefficientGroups).mockResolvedValue({ items: [], total: 0 });
  });

  it('switches between price items and the coefficient catalog', async () => {
    renderHub();
    const coefficientsTab = screen.getByLabelText('pricebook-maintab-coefficients');
    expect(coefficientsTab.className).toContain('min-h-14');
    expect(coefficientsApi.fetchCoefficientGroups).not.toHaveBeenCalled();

    fireEvent.click(coefficientsTab);
    // Lazy-loaded tab: wait for the settled catalog, not a transient pre-fetch render.
    await waitFor(() => expect(coefficientsApi.fetchCoefficientGroups).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByText('Brak zdefiniowanych grup współczynników.')).toBeInTheDocument(),
    );
    expect(screen.queryByLabelText('pricebook-tabs')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('back-to-pricebook'));
    fireEvent.click(screen.getByLabelText('pricebook-maintab-items'));
    expect(screen.getByLabelText('pricebook-tabs')).toBeInTheDocument();
  });
});
