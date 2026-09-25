import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api/http';
import * as openingsApi from './api/openings';
import * as revealWorksApi from './api/revealWorks';
import * as priceItemsApi from './api/priceItems';
import { OpeningList } from './components/OpeningList';
import { I18nProvider } from './hooks/useI18n';
import { OpeningType } from './types/opening';

vi.mock('./api/openings', () => ({
  fetchOpenings: vi.fn(),
  createOpening: vi.fn(),
  updateOpening: vi.fn(),
  archiveOpening: vi.fn(),
  restoreOpening: vi.fn(),
}));

vi.mock('./api/revealWorks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/revealWorks')>();
  return {
    ...actual,
    fetchRevealWorks: vi.fn(),
    putRevealWorks: vi.fn(),
  };
});

vi.mock('./api/priceItems', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/priceItems')>();
  return {
    ...actual,
    fetchPriceItems: vi.fn(),
  };
});

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const surfaceId = '33333333-3333-3333-3333-333333333333';

const openingDoor: OpeningType = {
  id: '44444444-4444-4444-4444-444444444444',
  surface_id: surfaceId,
  opening_type: 'DOOR',
  name: 'Drzwi pokojowe',
  width: 0.9,
  height: 2.0,
  quantity: 1,
  single_area: '1.800',
  total_area: '1.800',
  description: 'Standardowe drzwi',
  reveal_enabled: false,
  reveal_depth: null,
  reveal_left: true,
  reveal_right: true,
  reveal_top: true,
  reveal_bottom: false,
  reveal_single_length: null,
  reveal_single_area: null,
  reveal_total_length: null,
  reveal_total_area: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const openingWindow: OpeningType = {
  id: '55555555-5555-5555-5555-555555555555',
  surface_id: surfaceId,
  opening_type: 'WINDOW',
  name: 'Okno dwuskrzydłowe',
  width: 1.5,
  height: 1.4,
  quantity: 2,
  single_area: '2.100',
  total_area: '4.200',
  description: null,
  reveal_enabled: false,
  reveal_depth: null,
  reveal_left: true,
  reveal_right: true,
  reveal_top: true,
  reveal_bottom: false,
  reveal_single_length: null,
  reveal_single_area: null,
  reveal_total_length: null,
  reveal_total_area: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

function renderOpenings(onOpeningChanged = vi.fn()) {
  return render(
    <I18nProvider>
      <OpeningList
        projectId={projectId}
        roomId={roomId}
        surfaceId={surfaceId}
        onOpeningChanged={onOpeningChanged}
      />
    </I18nProvider>,
  );
}

describe('OpeningList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingDoor], total: 1 });
  });

  it('renders openings list with types, dimensions, and total area', async () => {
    renderOpenings();

    await waitFor(() => expect(screen.getByText('Drzwi')).toBeInTheDocument());
    expect(screen.getByText('(Drzwi pokojowe)')).toBeInTheDocument();
    expect(screen.getByText(/0\.90 × 2\.00 m/)).toBeInTheDocument();
    expect(screen.getByText(/1\.80 m²/)).toBeInTheDocument();
    expect(screen.getByText('Standardowe drzwi')).toBeInTheDocument();
  });

  it('renders quantity badge and total area for multi-unit openings', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWindow], total: 1 });
    renderOpenings();

    await waitFor(() => expect(screen.getByText('Okno')).toBeInTheDocument());
    expect(screen.getByText('×2')).toBeInTheDocument();
    expect(screen.getByText(/1\.50 × 1\.40 m/)).toBeInTheDocument();
    expect(screen.getByText(/4\.20 m²/)).toBeInTheDocument();
  });

  it('calculates live area preview when filling opening dimensions and quantity', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2' } });

    const preview = screen.getByLabelText('opening-preview-area');
    expect(preview).toBeInTheDocument();
    expect(preview).toHaveTextContent('1.80 m²');

    // Change quantity to 2 -> shows total preview
    fireEvent.change(screen.getByLabelText('opening-quantity'), { target: { value: '2' } });
    expect(preview).toHaveTextContent('3.60 m²');
  });

  it('creates an opening and notifies parent via onOpeningChanged', async () => {
    const onOpeningChanged = vi.fn();
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(openingsApi.createOpening).mockResolvedValue(openingDoor);
    renderOpenings(onOpeningChanged);

    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'DOOR' } });
    fireEvent.change(screen.getByLabelText('opening-name'), { target: { value: 'Drzwi pokojowe' } });
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.0' } });
    fireEvent.change(screen.getByLabelText('opening-quantity'), { target: { value: '1' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    await waitFor(() => {
      expect(openingsApi.createOpening).toHaveBeenCalledWith(projectId, roomId, surfaceId, {
        opening_type: 'DOOR',
        name: 'Drzwi pokojowe',
        width: 0.9,
        height: 2.0,
        quantity: 1,
        description: null,
        reveal_enabled: false,
      });
    });

    expect(await screen.findByText('Otwór został dodany')).toBeInTheDocument();
    expect(onOpeningChanged).toHaveBeenCalledTimes(1);
    expect(openingsApi.fetchOpenings).toHaveBeenCalledTimes(2);
  });

  it('edits an opening and notifies parent via onOpeningChanged', async () => {
    const onOpeningChanged = vi.fn();
    vi.mocked(openingsApi.updateOpening).mockResolvedValue({
      ...openingDoor,
      width: 1.0,
      total_area: '2.000',
    });
    renderOpenings(onOpeningChanged);

    await waitFor(() => expect(screen.getByLabelText(`edit-opening-${openingDoor.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`edit-opening-${openingDoor.id}`));

    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '1.0' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    await waitFor(() => {
      expect(openingsApi.updateOpening).toHaveBeenCalledWith(
        projectId,
        roomId,
        surfaceId,
        openingDoor.id,
        expect.objectContaining({ width: 1.0 }),
      );
    });

    expect(await screen.findByText('Otwór został zaktualizowany')).toBeInTheDocument();
    expect(onOpeningChanged).toHaveBeenCalledTimes(1);
  });

  it('displays readable 422 over-deduction error without losing form input', async () => {
    vi.mocked(openingsApi.createOpening).mockRejectedValue(
      new Error('Suma powierzchni otworów (15.000 m²) przekracza powierzchnię brutto ściany (13.500 m²)'),
    );
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`add-opening-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '3' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('przekracza powierzchnię brutto ściany');

    // Form inputs remain intact for user correction
    expect(screen.getByLabelText('opening-width')).toHaveValue(5);
    expect(screen.getByLabelText('opening-height')).toHaveValue(3);
  });

  it('localizes an over-deduction 422 in Polish on every repeated submission', async () => {
    vi.mocked(openingsApi.createOpening).mockRejectedValue(
      new ApiError(
        'Total opening deductions (20.513 m²) would exceed wall gross area (9.000 m²)',
        422,
        'openings_deductions_exceed_gross',
      ),
    );
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`add-opening-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.072' } });
    fireEvent.change(screen.getByLabelText('opening-quantity'), { target: { value: '11' } });

    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Łączna powierzchnia otworów nie może przekraczać powierzchni ściany.',
    );

    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));
    await waitFor(() => expect(openingsApi.createOpening).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Łączna powierzchnia otworów nie może przekraczać powierzchni ściany.',
    );
    expect(screen.getByLabelText('opening-width')).toHaveValue(0.9);
    expect(screen.getByLabelText('opening-height')).toHaveValue(2.072);
    expect(screen.getByLabelText('opening-quantity')).toHaveValue(11);
  });

  it('localizes an over-deduction 422 in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(openingsApi.createOpening).mockRejectedValue(
      new ApiError(
        'Total opening deductions (20.513 m²) would exceed wall gross area (9.000 m²)',
        422,
        'openings_deductions_exceed_gross',
      ),
    );
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`add-opening-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.072' } });
    fireEvent.change(screen.getByLabelText('opening-quantity'), { target: { value: '11' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Общая площадь проёмов не может превышать площадь стены.',
    );
  });

  it('localizes the Pydantic decimal-places 422 from the owner example', async () => {
    vi.mocked(openingsApi.createOpening).mockRejectedValue(
      new ApiError(
        'body.height: Decimal input should have no more than 3 decimal places',
        422,
      ),
    );
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`add-opening-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.07207' } });
    fireEvent.change(screen.getByLabelText('opening-quantity'), { target: { value: '11' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Podaj maksymalnie 3 miejsca po przecinku.',
    );
    expect(screen.getByLabelText('opening-height')).toHaveValue(2.07207);
  });

  it('uses a localized generic 422 only when the API supplied no structured detail', async () => {
    vi.mocked(openingsApi.createOpening).mockRejectedValue(
      new ApiError('Request failed (422)', 422),
    );
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`add-opening-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    expect(await screen.findByRole('alert')).toHaveTextContent('Sprawdź wprowadzone wartości.');
  });

  it('preserves an unknown structured 422 detail instead of hiding it', async () => {
    vi.mocked(openingsApi.createOpening).mockRejectedValue(
      new ApiError('body.custom: Custom validator detail', 422),
    );
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`add-opening-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2' } });
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'body.custom: Custom validator detail',
    );
  });

  it('archives an active opening and notifies parent', async () => {
    const onOpeningChanged = vi.fn();
    vi.mocked(openingsApi.archiveOpening).mockResolvedValue({ ...openingDoor, is_archived: true });
    renderOpenings(onOpeningChanged);

    await waitFor(() => expect(screen.getByLabelText(`archive-opening-${openingDoor.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`archive-opening-${openingDoor.id}`));

    await waitFor(() => {
      expect(openingsApi.archiveOpening).toHaveBeenCalledWith(projectId, roomId, surfaceId, openingDoor.id);
    });
    expect(await screen.findByText('Otwór został zarchiwizowany')).toBeInTheDocument();
    expect(onOpeningChanged).toHaveBeenCalledTimes(1);
  });

  it('restores an archived opening and notifies parent', async () => {
    const onOpeningChanged = vi.fn();
    const archived = { ...openingDoor, is_archived: true };
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [archived], total: 1 });
    vi.mocked(openingsApi.restoreOpening).mockResolvedValue(openingDoor);
    renderOpenings(onOpeningChanged);

    await waitFor(() => expect(screen.getByLabelText(`restore-opening-${openingDoor.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`restore-opening-${openingDoor.id}`));

    await waitFor(() => {
      expect(openingsApi.restoreOpening).toHaveBeenCalledWith(projectId, roomId, surfaceId, openingDoor.id);
    });
    expect(await screen.findByText('Otwór został przywrócony')).toBeInTheDocument();
    expect(onOpeningChanged).toHaveBeenCalledTimes(1);
  });

  it('renders mobile-optimized inputs (inputMode="decimal" and "numeric") and optional details', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    expect(screen.getByLabelText('opening-quantity')).toHaveAttribute('inputMode', 'numeric');
    expect(screen.getByLabelText('opening-width')).toHaveAttribute('inputMode', 'decimal');
    expect(screen.getByLabelText('opening-height')).toHaveAttribute('inputMode', 'decimal');
    expect(screen.getByText('Opcjonalne szczegóły')).toBeInTheDocument();
  });
});

describe('OpeningList dimension defaults (Stage 5D.1A.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
  });

  it('saves Door dimensions as default and prefills a subsequent new Door form', async () => {
    vi.mocked(openingsApi.createOpening).mockResolvedValue(openingDoor);
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'DOOR' } });
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.0' } });
    fireEvent.click(screen.getByLabelText('set-opening-default'));
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    await waitFor(() => expect(openingsApi.createOpening).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    expect(screen.getByLabelText('opening-type')).toHaveValue('DOOR');
    expect(screen.getByLabelText('opening-width')).toHaveValue(0.9);
    expect(screen.getByLabelText('opening-height')).toHaveValue(2.0);
  });

  it('keeps Window defaults independent from Door defaults', async () => {
    vi.mocked(openingsApi.createOpening).mockResolvedValue(openingDoor);
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());

    // Save a Door default 0.9 x 2.0
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'DOOR' } });
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.0' } });
    fireEvent.click(screen.getByLabelText('set-opening-default'));
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));
    await waitFor(() => expect(openingsApi.createOpening).toHaveBeenCalledTimes(1));

    // Opening a Window form must NOT inherit the Door dimensions
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'WINDOW' } });
    expect(screen.getByLabelText('opening-width')).toHaveValue(null);
    expect(screen.getByLabelText('opening-height')).toHaveValue(null);

    // Save a Window default 1.5 x 1.4
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '1.5' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '1.4' } });
    fireEvent.click(screen.getByLabelText('set-opening-default'));
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));
    await waitFor(() => expect(openingsApi.createOpening).toHaveBeenCalledTimes(2));

    // Window form prefills its own default
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'WINDOW' } });
    expect(screen.getByLabelText('opening-width')).toHaveValue(1.5);
    expect(screen.getByLabelText('opening-height')).toHaveValue(1.4);

    // Door form still prefills the Door default
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'DOOR' } });
    expect(screen.getByLabelText('opening-width')).toHaveValue(0.9);
    expect(screen.getByLabelText('opening-height')).toHaveValue(2.0);
  });

  it('never modifies existing openings when defaults change', async () => {
    vi.mocked(openingsApi.createOpening).mockResolvedValue(openingDoor);
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingDoor], total: 1 });
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`edit-opening-${openingDoor.id}`)).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.8' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.05' } });
    fireEvent.click(screen.getByLabelText('set-opening-default'));
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    await waitFor(() => expect(openingsApi.createOpening).toHaveBeenCalledTimes(1));
    expect(openingsApi.createOpening).toHaveBeenCalledWith(
      projectId,
      roomId,
      surfaceId,
      expect.objectContaining({ width: 0.8, height: 2.05 }),
    );
    expect(openingsApi.updateOpening).not.toHaveBeenCalled();
    expect(openingsApi.archiveOpening).not.toHaveBeenCalled();
    // The existing opening row is untouched
    expect(screen.getByText(/0\.90 × 2\.00 m/)).toBeInTheDocument();
  });
});

describe('OpeningList reveals (Stage 5F)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
  });

  it('shows reveal toggle for DOOR and WINDOW but not for OTHER', async () => {
    renderOpenings();
    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    // DOOR — toggle visible
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'DOOR' } });
    expect(screen.getByLabelText(`reveal-toggle-${surfaceId}`)).toBeInTheDocument();

    // WINDOW — toggle visible
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'WINDOW' } });
    expect(screen.getByLabelText(`reveal-toggle-${surfaceId}`)).toBeInTheDocument();

    // OTHER — toggle hidden
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'OTHER' } });
    expect(screen.queryByLabelText(`reveal-toggle-${surfaceId}`)).not.toBeInTheDocument();
  });

  it('toggling reveal on shows depth input and side checkboxes; toggling off hides them', async () => {
    renderOpenings();
    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    // depth and side checkboxes not present initially
    expect(screen.queryByLabelText('reveal-depth')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('reveal-left')).not.toBeInTheDocument();

    // toggle on
    fireEvent.click(screen.getByLabelText(`reveal-toggle-${surfaceId}`));
    expect(screen.getByLabelText('reveal-depth')).toBeInTheDocument();
    expect(screen.getByLabelText('reveal-left')).toBeInTheDocument();
    expect(screen.getByLabelText('reveal-right')).toBeInTheDocument();
    expect(screen.getByLabelText('reveal-top')).toBeInTheDocument();
    expect(screen.getByLabelText('reveal-bottom')).toBeInTheDocument();

    // default checked state: left/right/top=true, bottom=false
    expect(screen.getByLabelText('reveal-left')).toBeChecked();
    expect(screen.getByLabelText('reveal-right')).toBeChecked();
    expect(screen.getByLabelText('reveal-top')).toBeChecked();
    expect(screen.getByLabelText('reveal-bottom')).not.toBeChecked();

    // toggle off
    fireEvent.click(screen.getByLabelText(`reveal-toggle-${surfaceId}`));
    expect(screen.queryByLabelText('reveal-depth')).not.toBeInTheDocument();
  });

  it('creates an opening with reveal fields in payload when reveal is enabled', async () => {
    vi.mocked(openingsApi.createOpening).mockResolvedValue({
      ...openingWindow,
      reveal_enabled: true,
      reveal_depth: '0.150',
      reveal_total_length: '4.300',
      reveal_total_area: '0.645',
    });
    renderOpenings();
    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'WINDOW' } });
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '1.5' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '1.4' } });

    // enable reveal
    fireEvent.click(screen.getByLabelText(`reveal-toggle-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('reveal-depth'), { target: { value: '0.15' } });
    // bottom stays unchecked (default)

    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    await waitFor(() => {
      expect(openingsApi.createOpening).toHaveBeenCalledWith(
        projectId,
        roomId,
        surfaceId,
        expect.objectContaining({
          opening_type: 'WINDOW',
          reveal_enabled: true,
          reveal_depth: 0.15,
          reveal_left: true,
          reveal_right: true,
          reveal_top: true,
          reveal_bottom: false,
        }),
      );
    });
  });

  it('creates an opening without reveal fields when reveal is disabled', async () => {
    vi.mocked(openingsApi.createOpening).mockResolvedValue(openingDoor);
    renderOpenings();
    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '0.9' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '2.0' } });
    // reveal toggle not clicked
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));

    await waitFor(() => {
      expect(openingsApi.createOpening).toHaveBeenCalledWith(
        projectId,
        roomId,
        surfaceId,
        expect.objectContaining({ reveal_enabled: false }),
      );
      expect(openingsApi.createOpening).toHaveBeenCalledWith(
        projectId,
        roomId,
        surfaceId,
        expect.not.objectContaining({ reveal_left: expect.anything() }),
      );
    });
  });

  it('shows reveal totals on opening card when reveal_enabled and totals are provided', async () => {
    const openingWithReveal: OpeningType = {
      ...openingWindow,
      reveal_enabled: true,
      reveal_depth: '0.150',
      reveal_total_length: '4.300',
      reveal_total_area: '0.645',
    };
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWithReveal], total: 1 });
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`opening-item-${openingWindow.id}`)).toBeInTheDocument());
    const card = screen.getByLabelText(`opening-item-${openingWindow.id}`);
    expect(card).toHaveTextContent('Ościeża');
    // Stage 10G.4 follow-up — reveal length renders localized "mb", never raw "LM"/plain "m".
    expect(card).toHaveTextContent('4.30 mb');
    expect(card).toHaveTextContent('0.65 m²');
    expect(card.textContent).not.toMatch(/\bLM\b/);
  });

  it('shows the reveal length as "м.п." in RU (Stage 10G.4 follow-up)', async () => {
    localStorage.setItem('locale', 'ru');
    const openingWithReveal: OpeningType = {
      ...openingWindow,
      reveal_enabled: true,
      reveal_depth: '0.150',
      reveal_total_length: '4.300',
      reveal_total_area: '0.645',
    };
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWithReveal], total: 1 });
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`opening-item-${openingWindow.id}`)).toBeInTheDocument());
    const card = screen.getByLabelText(`opening-item-${openingWindow.id}`);
    expect(card).toHaveTextContent('4.30 пог. м');
    expect(card.textContent).not.toMatch(/\bLM\b/);
  });

  it('does not show reveal section on card when reveal is disabled', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingDoor], total: 1 });
    renderOpenings();

    await waitFor(() => expect(screen.getByLabelText(`opening-item-${openingDoor.id}`)).toBeInTheDocument());
    const card = screen.getByLabelText(`opening-item-${openingDoor.id}`);
    expect(card).not.toHaveTextContent('Ościeża');
  });
});

// Stage 10G.4 — reveal work planning toggle per opening.
describe('OpeningList — reveal work planning entry', () => {
  const openingWithReveal: OpeningType = {
    ...openingWindow,
    reveal_enabled: true,
    reveal_depth: '0.150',
    reveal_total_length: '4.300',
    reveal_total_area: '0.645',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(revealWorksApi.fetchRevealWorks).mockResolvedValue({ opening_id: openingWithReveal.id, items: [] });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
  });

  it('shows the "Prace na ościeżach" toggle only when reveal_enabled is true', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWithReveal], total: 1 });
    renderOpenings();
    await waitFor(() => screen.getByLabelText(`opening-item-${openingWithReveal.id}`));
    expect(screen.getByLabelText(`reveal-work-toggle-${openingWithReveal.id}`)).toBeInTheDocument();
  });

  it('does not show the reveal work toggle when reveal_enabled is false', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingDoor], total: 1 });
    renderOpenings();
    await waitFor(() => screen.getByLabelText(`opening-item-${openingDoor.id}`));
    expect(screen.queryByLabelText(`reveal-work-toggle-${openingDoor.id}`)).toBeNull();
  });

  it('opens the RevealWorkPlanEditor for that exact opening on click, and closes it on toggle again', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWithReveal], total: 1 });
    renderOpenings();
    await waitFor(() => screen.getByLabelText(`opening-item-${openingWithReveal.id}`));

    fireEvent.click(screen.getByLabelText(`reveal-work-toggle-${openingWithReveal.id}`));
    expect(await screen.findByLabelText(`reveal-work-editor-${openingWithReveal.id}`)).toBeInTheDocument();
    await waitFor(() => {
      expect(revealWorksApi.fetchRevealWorks).toHaveBeenCalledWith(
        projectId, roomId, surfaceId, openingWithReveal.id,
      );
    });

    fireEvent.click(screen.getByLabelText(`reveal-work-toggle-${openingWithReveal.id}`));
    expect(screen.queryByLabelText(`reveal-work-editor-${openingWithReveal.id}`)).toBeNull();
  });

  it('passes the backend-authoritative reveal geometry through to the editor unchanged', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWithReveal], total: 1 });
    renderOpenings();
    await waitFor(() => screen.getByLabelText(`opening-item-${openingWithReveal.id}`));
    fireEvent.click(screen.getByLabelText(`reveal-work-toggle-${openingWithReveal.id}`));

    const geometry = await screen.findByLabelText(`reveal-geometry-${openingWithReveal.id}`);
    expect(geometry.textContent).toContain('4.30');
    expect(geometry.textContent).toContain('0.65');
  });

  it('only one reveal work editor is open at a time across multiple reveal-enabled openings', async () => {
    const secondOpening: OpeningType = {
      ...openingWithReveal,
      id: '77777777-7777-7777-7777-777777777777',
      name: 'Drugie okno',
    };
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({
      items: [openingWithReveal, secondOpening],
      total: 2,
    });
    renderOpenings();
    await waitFor(() => screen.getByLabelText(`opening-item-${openingWithReveal.id}`));

    fireEvent.click(screen.getByLabelText(`reveal-work-toggle-${openingWithReveal.id}`));
    await screen.findByLabelText(`reveal-work-editor-${openingWithReveal.id}`);

    fireEvent.click(screen.getByLabelText(`reveal-work-toggle-${secondOpening.id}`));
    await screen.findByLabelText(`reveal-work-editor-${secondOpening.id}`);
    expect(screen.queryByLabelText(`reveal-work-editor-${openingWithReveal.id}`)).toBeNull();
  });
});

// Owner walkthrough polish: existing openings first, strong reveal action,
// and a reveal needs at least one side.
describe('OpeningList — owner walkthrough layout and reveal sides', () => {
  const openingWithReveal: OpeningType = {
    ...openingWindow,
    reveal_enabled: true,
    reveal_depth: '0.150',
    reveal_total_length: '4.300',
    reveal_total_area: '0.645',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(revealWorksApi.fetchRevealWorks).mockResolvedValue({ opening_id: openingWithReveal.id, items: [] });
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWithReveal], total: 1 });
  });

  const follows = (a: Element, b: Element) =>
    Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

  it('shows existing openings (with geometry and reveal action) before the new-opening controls', async () => {
    renderOpenings();
    const item = await screen.findByLabelText(`opening-item-${openingWithReveal.id}`);
    expect(item).toHaveTextContent('4.30');
    const add = screen.getByLabelText(`add-opening-${surfaceId}`);
    expect(follows(item, add)).toBe(true);
    expect(add.className).toContain('min-h-[44px]');

    fireEvent.click(add);
    const form = screen.getByLabelText(`opening-form-${surfaceId}`);
    expect(follows(item, form)).toBe(true);
    expect(screen.queryByLabelText(`add-opening-${surfaceId}`)).not.toBeInTheDocument();
  });

  it('renders "Prace na ościeżach" as a strong 44px action', async () => {
    renderOpenings();
    const toggle = await screen.findByLabelText(`reveal-work-toggle-${openingWithReveal.id}`);
    expect(toggle).toHaveTextContent('Prace na ościeżach');
    expect(toggle.className).toContain('bg-orange-700');
    expect(toggle.className).toContain('text-white');
    expect(toggle.className).toContain('min-h-[44px]');
  });

  it('blocks saving a reveal with no side selected (localized)', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [], total: 0 });
    renderOpenings();
    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('opening-type'), { target: { value: 'WINDOW' } });
    fireEvent.change(screen.getByLabelText('opening-width'), { target: { value: '1.5' } });
    fireEvent.change(screen.getByLabelText('opening-height'), { target: { value: '1.4' } });
    fireEvent.click(screen.getByLabelText(`reveal-toggle-${surfaceId}`));
    fireEvent.change(screen.getByLabelText('reveal-depth'), { target: { value: '0.15' } });
    fireEvent.click(screen.getByLabelText('reveal-left'));
    fireEvent.click(screen.getByLabelText('reveal-right'));
    fireEvent.click(screen.getByLabelText('reveal-top'));
    fireEvent.submit(screen.getByLabelText(`opening-form-${surfaceId}`));
    expect(await screen.findByText('Zaznacz co najmniej jedną stronę ościeżnicy.')).toBeInTheDocument();
    expect(openingsApi.createOpening).not.toHaveBeenCalled();
  });

  it('gives Edytuj / Archiwizuj / Przywróć 44px targets and lets actions wrap below the info', async () => {
    const archived: OpeningType = { ...openingDoor, id: 'op-archived', is_archived: true };
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWithReveal, archived], total: 2 });
    renderOpenings();
    await screen.findByLabelText(`opening-item-${openingWithReveal.id}`);
    for (const label of [
      `edit-opening-${openingWithReveal.id}`,
      `archive-opening-${openingWithReveal.id}`,
      `edit-opening-${archived.id}`,
      `restore-opening-${archived.id}`,
    ]) {
      const button = screen.getByLabelText(label);
      expect(button.className).toContain('min-h-[44px]');
      expect(button.className).toContain('min-w-[44px]');
    }
    expect(screen.getByLabelText(`restore-opening-${archived.id}`)).toHaveTextContent('Przywróć');
    const actions = screen.getByLabelText(`edit-opening-${openingWithReveal.id}`).parentElement!;
    const row = actions.parentElement!;
    expect(row.className).toContain('flex-wrap');
    expect((actions.previousElementSibling as HTMLElement).className).toContain('basis-40');
  });
});
