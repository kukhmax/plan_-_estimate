import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as areaSegmentsApi from './api/areaSegments';
import { AreaSegmentList } from './components/AreaSegmentList';
import { I18nProvider } from './hooks/useI18n';
import { AreaSegmentType } from './types/areaSegment';

vi.mock('./api/areaSegments', () => ({
  fetchAreaSegments: vi.fn(),
  createAreaSegment: vi.fn(),
  updateAreaSegment: vi.fn(),
  archiveAreaSegment: vi.fn(),
  restoreAreaSegment: vi.fn(),
}));

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';

const floorAdd: AreaSegmentType = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  room_id: roomId,
  plane: 'FLOOR',
  operation: 'ADD',
  width: 3.0,
  height: 2.0,
  position: 0,
  label: 'Parkiet wejście',
  area: '6.000',
  is_archived: false,
  created_at: '2026-09-11T08:00:00Z',
  updated_at: '2026-09-11T08:00:00Z',
};

const floorSubtract: AreaSegmentType = {
  id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  room_id: roomId,
  plane: 'FLOOR',
  operation: 'SUBTRACT',
  width: 1.0,
  height: 1.0,
  position: 1,
  label: null,
  area: '1.000',
  is_archived: false,
  created_at: '2026-09-11T08:05:00Z',
  updated_at: '2026-09-11T08:05:00Z',
};

const ceilingAdd: AreaSegmentType = {
  id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
  room_id: roomId,
  plane: 'CEILING',
  operation: 'ADD',
  width: 5.0,
  height: 2.0,
  position: 0,
  label: 'Sufit salon',
  area: '10.000',
  is_archived: false,
  created_at: '2026-09-11T08:10:00Z',
  updated_at: '2026-09-11T08:10:00Z',
};

function renderAreaSegments(onMeasurementChanged = vi.fn()) {
  return render(
    <I18nProvider>
      <AreaSegmentList
        projectId={projectId}
        roomId={roomId}
        onMeasurementChanged={onMeasurementChanged}
      />
    </I18nProvider>,
  );
}

describe('AreaSegmentList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0 });
  });

  it('renders PODŁOGA and SUFIT sections each with add rectangle/subtraction buttons', async () => {
    renderAreaSegments();

    await waitFor(() => expect(screen.getByText('Podłoga')).toBeInTheDocument());
    expect(screen.getByText('Sufit')).toBeInTheDocument();

    expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument();
    expect(screen.getByLabelText('add-floor-subtraction')).toBeInTheDocument();
    expect(screen.getByLabelText('add-ceiling-rectangle')).toBeInTheDocument();
    expect(screen.getByLabelText('add-ceiling-subtraction')).toBeInTheDocument();
  });

  it('shows empty states when a plane has no segments', async () => {
    renderAreaSegments();

    await waitFor(() =>
      expect(
        screen.getByText('Brak prostokątów podłogi'),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText('Brak prostokątów sufitu')).toBeInTheDocument();
  });

  it('renders segment rows with operation badge, label, dimensions, and single area', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({
      items: [floorAdd, ceilingAdd],
      total: 2,
    });
    renderAreaSegments();

    await waitFor(() => expect(screen.getByText('Parkiet wejście')).toBeInTheDocument());
    expect(screen.getAllByText('Dodanie')).toHaveLength(2);
    expect(screen.getByText(/3\.00 × 2\.00 m/)).toBeInTheDocument();
    expect(screen.getByText('6.00 m²')).toBeInTheDocument();
    expect(screen.getByText('Sufit salon')).toBeInTheDocument();
    expect(screen.getByText('10.00 m²')).toBeInTheDocument();
  });

  it('computes "Razem" plane totals as additions minus subtractions', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({
      items: [floorAdd, floorSubtract],
      total: 2,
    });
    renderAreaSegments();

    // Floor net = 6.000 - 1.000 = 5.000
    await waitFor(() => expect(screen.getByText(/Razem: 5\.00 m²/)).toBeInTheDocument());
  });

  it('renders mobile-optimized decimal inputs in the segment form', async () => {
    renderAreaSegments();
    await waitFor(() => expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-floor-rectangle'));

    expect(screen.getByLabelText('segment-width')).toHaveAttribute('inputMode', 'decimal');
    expect(screen.getByLabelText('segment-height')).toHaveAttribute('inputMode', 'decimal');
  });

  it('creates an ADD rectangle and notifies parent via onMeasurementChanged', async () => {
    const onMeasurementChanged = vi.fn();
    vi.mocked(areaSegmentsApi.createAreaSegment).mockResolvedValue(floorAdd);
    renderAreaSegments(onMeasurementChanged);

    await waitFor(() => expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-floor-rectangle'));

    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('segment-label'), { target: { value: 'Parkiet wejście' } });
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    await waitFor(() => {
      expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledWith(projectId, roomId, {
        plane: 'FLOOR',
        operation: 'ADD',
        width: 3,
        height: 2,
        label: 'Parkiet wejście',
      });
    });

    expect(await screen.findByText('Prostokąt został dodany')).toBeInTheDocument();
    expect(onMeasurementChanged).toHaveBeenCalledTimes(1);
  });

  it('creates a SUBTRACTION with the operation preset by the button', async () => {
    vi.mocked(areaSegmentsApi.createAreaSegment).mockResolvedValue(floorSubtract);
    renderAreaSegments();

    await waitFor(() => expect(screen.getByLabelText('add-floor-subtraction')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-floor-subtraction'));

    expect(screen.getByText('Odjęcie')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '1' } });
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    await waitFor(() => {
      expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledWith(projectId, roomId, {
        plane: 'FLOOR',
        operation: 'SUBTRACT',
        width: 1,
        height: 1,
        label: null,
      });
    });
  });

  it('creates CEILING segments independently of FLOOR', async () => {
    vi.mocked(areaSegmentsApi.createAreaSegment).mockResolvedValue(ceilingAdd);
    renderAreaSegments();

    await waitFor(() => expect(screen.getByLabelText('add-ceiling-rectangle')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-ceiling-rectangle'));

    expect(screen.getByLabelText('ceiling-segment-form')).toBeVisible();
    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '2' } });
    fireEvent.submit(screen.getByLabelText('ceiling-segment-form'));

    await waitFor(() => {
      expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledWith(projectId, roomId, {
        plane: 'CEILING',
        operation: 'ADD',
        width: 5,
        height: 2,
        label: null,
      });
    });
    expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledTimes(1);
  });

  it('edits a segment and notifies parent via onMeasurementChanged', async () => {
    const onMeasurementChanged = vi.fn();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [floorAdd], total: 1 });
    vi.mocked(areaSegmentsApi.updateAreaSegment).mockResolvedValue({
      ...floorAdd,
      width: 4.0,
      area: '8.000',
    });
    renderAreaSegments(onMeasurementChanged);

    await waitFor(() =>
      expect(screen.getByLabelText(`edit-segment-${floorAdd.id}`)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByLabelText(`edit-segment-${floorAdd.id}`));

    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '4' } });
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    await waitFor(() => {
      expect(areaSegmentsApi.updateAreaSegment).toHaveBeenCalledWith(
        projectId,
        roomId,
        floorAdd.id,
        expect.objectContaining({ width: 4, operation: 'ADD' }),
      );
    });

    expect(await screen.findByText('Prostokąt został zaktualizowany')).toBeInTheDocument();
    expect(onMeasurementChanged).toHaveBeenCalledTimes(1);
  });

  it('rejects invalid dimensions without calling the API', async () => {
    renderAreaSegments();

    await waitFor(() => expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-floor-rectangle'));

    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '-2' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '0' } });
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Podaj poprawną szerokość i długość (m)');
    expect(areaSegmentsApi.createAreaSegment).not.toHaveBeenCalled();
    // Form stays open for correction
    expect(screen.getByLabelText('segment-width')).toHaveValue(-2);
  });

  it('displays a readable 422 negative-net error without losing the form input', async () => {
    vi.mocked(areaSegmentsApi.createAreaSegment).mockRejectedValue(
      new Error('Net area (-1.000) cannot be negative for a plane'),
    );
    renderAreaSegments();

    await waitFor(() => expect(screen.getByLabelText('add-floor-subtraction')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-floor-subtraction'));

    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '3' } });
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('cannot be negative');
    expect(screen.getByLabelText('segment-width')).toHaveValue(5);
  });

  it('archives an active segment and notifies parent', async () => {
    const onMeasurementChanged = vi.fn();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [floorAdd], total: 1 });
    vi.mocked(areaSegmentsApi.archiveAreaSegment).mockResolvedValue({ ...floorAdd, is_archived: true });
    renderAreaSegments(onMeasurementChanged);

    await waitFor(() =>
      expect(screen.getByLabelText(`archive-segment-${floorAdd.id}`)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByLabelText(`archive-segment-${floorAdd.id}`));

    await waitFor(() => {
      expect(areaSegmentsApi.archiveAreaSegment).toHaveBeenCalledWith(
        projectId,
        roomId,
        floorAdd.id,
      );
    });
    expect(await screen.findByText('Prostokąt został zarchiwizowany')).toBeInTheDocument();
    expect(onMeasurementChanged).toHaveBeenCalledTimes(1);
  });

  it('restores an archived segment and notifies parent', async () => {
    const onMeasurementChanged = vi.fn();
    const archived = { ...floorAdd, is_archived: true };
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [archived], total: 1 });
    vi.mocked(areaSegmentsApi.restoreAreaSegment).mockResolvedValue(floorAdd);
    renderAreaSegments(onMeasurementChanged);

    await waitFor(() =>
      expect(screen.getByLabelText(`restore-segment-${floorAdd.id}`)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByLabelText(`restore-segment-${floorAdd.id}`));

    await waitFor(() => {
      expect(areaSegmentsApi.restoreAreaSegment).toHaveBeenCalledWith(
        projectId,
        roomId,
        floorAdd.id,
      );
    });
    expect(await screen.findByText('Prostokąt został przywrócony')).toBeInTheDocument();
    expect(onMeasurementChanged).toHaveBeenCalledTimes(1);
  });

  it('shows backend effective total for a rectangle plane with zero segments', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({
      items: [],
      total: 0,
      planes: {
        FLOOR: { base_area: '12.210', adjustment_area: '0.000', net_area: '12.210' },
        CEILING: { base_area: '12.210', adjustment_area: '0.000', net_area: '12.210' },
      },
    });
    renderAreaSegments();

    await waitFor(() => expect(screen.getAllByText(/Razem: 12\.21 m²/)).toHaveLength(2));
    expect(screen.getAllByText('Powierzchnia bazowa')).toHaveLength(2);
    expect(screen.getAllByText('12.21 m²').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Korekty')).toHaveLength(2);
    // Empty-state copy is still present for the no-segments list
    expect(screen.getByText('Brak prostokątów podłogi')).toBeInTheDocument();
  });

  it('shows base, negative adjustment, and effective total from the backend summary', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({
      items: [],
      total: 0,
      planes: {
        FLOOR: { base_area: '12.210', adjustment_area: '-0.560', net_area: '11.650' },
        CEILING: { base_area: '12.210', adjustment_area: '0.000', net_area: '12.210' },
      },
    });
    renderAreaSegments();

    await waitFor(() => expect(screen.getByText(/Razem: 11\.65 m²/)).toBeInTheDocument());
    expect(screen.getByText('-0.56 m²')).toBeInTheDocument();
    expect(screen.getByText(/Razem: 12\.21 m²/)).toBeInTheDocument();
  });

  it('does not fabricate a base total for a custom room without segments', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({
      items: [],
      total: 0,
      planes: {
        FLOOR: { base_area: null, adjustment_area: '0.000', net_area: '0.000' },
        CEILING: { base_area: null, adjustment_area: '0.000', net_area: '0.000' },
      },
    });
    renderAreaSegments();

    await waitFor(() => expect(screen.getByText('Brak prostokątów podłogi')).toBeInTheDocument());
    // No base-area row and no fabricated 0.000 total badge
    expect(screen.queryByText('Powierzchnia bazowa')).not.toBeInTheDocument();
    expect(screen.queryByText(/Razem: 0\.000 m²/)).not.toBeInTheDocument();
  });
});