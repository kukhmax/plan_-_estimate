import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

function renderBook() {
  return render(
    <I18nProvider>
      <PriceBook />
    </I18nProvider>,
  );
}

describe('PriceBook — list and cards', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
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

  it('requests the backend search parameter on typing', async () => {
    renderBook();
    fireEvent.change(screen.getByLabelText('pricebook-search'), {
      target: { value: 'lateks' },
    });
    await waitFor(() =>
      expect(priceItemsApi.fetchPriceItems).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'lateks' }),
      ),
    );
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
    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.click(screen.getByLabelText(`price-item-options-${itemLabel}`));
    fireEvent.click(screen.getByLabelText(`edit-price-item-${itemLabel}`));
  }

  it('opens an existing item pre-filled (with the seeded identity hint)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedPaint],
      total: 1,
    });
    renderBook();
    await openEdit('item-2');

    expect(screen.getByLabelText('price-item-display-name')).toHaveValue('');
    expect(screen.getByLabelText('price-item-price')).toHaveValue('2.22');
    expect(screen.getByLabelText('price-item-category')).toHaveValue('PAINTING');
    expect(
      screen.getByText(`Nazwa bazowa: ${'Malowanie ścian — 2 warstwy (standard)'}`),
    ).toBeInTheDocument();
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

  it('clearing the name on a seeded row sends an empty override (revert to name_key)', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
      items: [seedPaint],
      total: 1,
    });
    renderBook();
    await openEdit('item-2');

    const nameInput = screen.getByLabelText('price-item-display-name');
    fireEvent.change(nameInput, { target: { value: 'Tymczasowa nazwa' } });
    fireEvent.change(nameInput, { target: { value: '' } });
    fireEvent.submit(screen.getByLabelText('price-item-form'));

    await waitFor(() =>
      expect(priceItemsApi.updatePriceItem).toHaveBeenCalledWith(
        'item-2',
        expect.objectContaining({ display_name: '' }),
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

  it('scrolls the form into view when Edit is tapped on a catalog row', async () => {
    const { spy, restore } = stubScrollIntoView();
    try {
      vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValueOnce({
        items: [custom],
        total: 1,
      });
      renderBook();
      await screen.findByText('Malowanie lateksowe dwukrotnie');
      expect(spy).not.toHaveBeenCalled();

      fireEvent.click(screen.getByLabelText('price-item-options-item-3'));
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

  it('archives via Opcje and removes the item from the active view', async () => {
    vi.mocked(priceItemsApi.fetchPriceItems)
      .mockResolvedValueOnce({ items: [seedPrep, custom], total: 2 })
      .mockResolvedValueOnce({ items: [seedPrep], total: 1 });
    renderBook();

    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.click(screen.getByLabelText(`price-item-options-${custom.id}`));
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

    fireEvent.click(await screen.findByLabelText('add-price-item'));
    fireEvent.click(screen.getByLabelText(`price-item-options-${custom.id}`));
    fireEvent.click(screen.getByLabelText(`archive-price-item-${custom.id}`));

    expect(await screen.findByText('Nie udało się zarchiwizować pozycji.')).toBeInTheDocument();
    expect(screen.queryByText(/500/)).not.toBeInTheDocument();
  });
});