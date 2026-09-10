import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as openingsApi from './api/openings';
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
    expect(screen.getByText(/0\.900 × 2\.000 m/)).toBeInTheDocument();
    expect(screen.getByText(/1\.800 m²/)).toBeInTheDocument();
    expect(screen.getByText('Standardowe drzwi')).toBeInTheDocument();
  });

  it('renders quantity badge and total area for multi-unit openings', async () => {
    vi.mocked(openingsApi.fetchOpenings).mockResolvedValue({ items: [openingWindow], total: 1 });
    renderOpenings();

    await waitFor(() => expect(screen.getByText('Okno')).toBeInTheDocument());
    expect(screen.getByText('×2')).toBeInTheDocument();
    expect(screen.getByText(/1\.500 × 1\.400 m/)).toBeInTheDocument();
    expect(screen.getByText(/4\.200 m²/)).toBeInTheDocument();
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
    expect(preview).toHaveTextContent('1.800 m²');

    // Change quantity to 2 -> shows total preview
    fireEvent.change(screen.getByLabelText('opening-quantity'), { target: { value: '2' } });
    expect(preview).toHaveTextContent('3.600 m²');
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
    expect(screen.getByText(/0\.900 × 2\.000 m/)).toBeInTheDocument();
  });
});
