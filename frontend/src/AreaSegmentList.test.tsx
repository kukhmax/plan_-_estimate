import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as areaSegmentsApi from './api/areaSegments';
import * as surfacesApi from './api/surfaces';
import * as workPlansApi from './api/workPlans';
import { AreaSegmentList } from './components/AreaSegmentList';
import { I18nProvider } from './hooks/useI18n';
import { AreaSegmentType } from './types/areaSegment';
import { SurfaceListResponse } from './types/surface';

vi.mock('./api/areaSegments', () => ({
  fetchAreaSegments: vi.fn(),
  createAreaSegment: vi.fn(),
  updateAreaSegment: vi.fn(),
  archiveAreaSegment: vi.fn(),
  restoreAreaSegment: vi.fn(),
}));

vi.mock('./api/surfaces', () => ({
  fetchSurfaces: vi.fn(),
}));
vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return {
    ...actual,
    fetchSurfaceWorkPlan: vi.fn(),
    putSurfaceWorkPlan: vi.fn(),
  };
});

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const floorSurfaceId = 'f1111111-1111-1111-1111-111111111111';
const ceilingSurfaceId = 'c1111111-1111-1111-1111-111111111111';

const floorAdd: AreaSegmentType = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  room_id: roomId,
  surface_id: floorSurfaceId,
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
  surface_id: floorSurfaceId,
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
  surface_id: ceilingSurfaceId,
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

// Canonical FLOOR/CEILING Surface rows (Stage 10C.1A provisions one of each per room).
const canonicalPlanes: SurfaceListResponse = {
  items: [
    {
      id: floorSurfaceId,
      room_id: roomId,
      name: 'Floor',
      surface_type: 'FLOOR',
      description: null,
      position: 100,
      is_archived: false,
      created_at: '2026-09-16T08:00:00Z',
      updated_at: '2026-09-16T08:00:00Z',
    },
    {
      id: ceilingSurfaceId,
      room_id: roomId,
      name: 'Ceiling',
      surface_type: 'CEILING',
      description: null,
      position: 101,
      is_archived: false,
      created_at: '2026-09-16T08:00:00Z',
      updated_at: '2026-09-16T08:00:00Z',
    },
  ],
  total: 2,
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

async function expandPlane(planeKey: 'floor' | 'ceiling') {
  const toggle = await screen.findByLabelText(`options-toggle-${planeKey}`);
  fireEvent.click(toggle);
}

beforeEach(() => {
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockImplementation(async (_project, _room, id) => ({
    id: `plan-${id}`,
    surface_id: id,
    substrate: 'CONCRETE',
    quality_target: 'S2',
    planned_works: [],
  }));
});

describe('AreaSegmentList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(canonicalPlanes);
  });

  it('renders PODŁOGA and SUFIT cards; measurement actions hidden behind Opcje', async () => {
    renderAreaSegments();

    await waitFor(() => expect(screen.getByText('Podłoga')).toBeInTheDocument());
    expect(screen.getByText('Sufit')).toBeInTheDocument();

    // Actions are collapsed behind Opcje by default.
    expect(screen.queryByLabelText('add-floor-rectangle')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('add-ceiling-rectangle')).not.toBeInTheDocument();

    await expandPlane('floor');
    await expandPlane('ceiling');
    expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument();
    expect(screen.getByLabelText('add-floor-subtraction')).toBeInTheDocument();
    expect(screen.getByLabelText('add-ceiling-rectangle')).toBeInTheDocument();
    expect(screen.getByLabelText('add-ceiling-subtraction')).toBeInTheDocument();
  });

  it('shows empty states when a plane has no segments', async () => {
    renderAreaSegments();

    await expandPlane('floor');
    await expandPlane('ceiling');
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

    await expandPlane('floor');
    await expandPlane('ceiling');
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
    await expandPlane('floor');
    await waitFor(() => expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-floor-rectangle'));

    expect(screen.getByLabelText('segment-width')).toHaveAttribute('inputMode', 'decimal');
    expect(screen.getByLabelText('segment-height')).toHaveAttribute('inputMode', 'decimal');
  });

  it('creates an ADD rectangle and notifies parent via onMeasurementChanged', async () => {
    const onMeasurementChanged = vi.fn();
    vi.mocked(areaSegmentsApi.createAreaSegment).mockResolvedValue(floorAdd);
    renderAreaSegments(onMeasurementChanged);

    await expandPlane('floor');
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

    await expandPlane('floor');
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

    await expandPlane('ceiling');
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

    await expandPlane('floor');
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

    await expandPlane('floor');
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

    await expandPlane('floor');
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

    await expandPlane('floor');
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

    await expandPlane('floor');
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
    // Empty-state copy is still present for the no-segments list (behind Opcje)
    await expandPlane('floor');
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

    await expandPlane('floor');
    await waitFor(() => expect(screen.getByText('Brak prostokątów podłogi')).toBeInTheDocument());
    // No base-area row and no fabricated 0.000 total badge
    expect(screen.queryByText('Powierzchnia bazowa')).not.toBeInTheDocument();
    expect(screen.queryByText(/Razem: 0\.000 m²/)).not.toBeInTheDocument();
  });
});

describe('AreaSegmentList plane-card parity (10C.1B)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(canonicalPlanes);
  });

  it('A/B: FLOOR shows Opcje and Rodzaje prac i jakość', async () => {
    renderAreaSegments();

    const toggle = await screen.findByLabelText('options-toggle-floor');
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveTextContent('Opcje');
    const workPlan = screen.getByLabelText(`work-plan-${floorSurfaceId}`);
    expect(workPlan).toBeInTheDocument();
    expect(workPlan).toHaveTextContent('Rodzaje prac i jakość');
  });

  it('C: FLOOR WorkPlan button binds the canonical FLOOR Surface.id (not segment/room/synthetic)', async () => {
    renderAreaSegments();

    const buttons = await screen.findAllByLabelText(/^work-plan-/);
    expect(buttons.map((b) => b.getAttribute('aria-label'))).toEqual([
      `work-plan-${floorSurfaceId}`,
      `work-plan-${ceilingSurfaceId}`,
    ]);
    // No id masquerading as a Surface.id.
    expect(screen.queryByLabelText('work-plan-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`work-plan-${roomId}`)).not.toBeInTheDocument();
  });

  it('D/E/F: FLOOR actions hidden collapsed, visible expanded, collapse again', async () => {
    renderAreaSegments();

    const toggle = await screen.findByLabelText('options-toggle-floor');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('add-floor-rectangle')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('add-floor-subtraction')).not.toBeInTheDocument();

    await expandPlane('floor');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveTextContent('Ukryj opcje');
    expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument();
    expect(screen.getByLabelText('add-floor-subtraction')).toBeInTheDocument();

    await expandPlane('floor');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('add-floor-rectangle')).not.toBeInTheDocument();
  });

  it('G/H: CEILING shows Opcje and Rodzaje prac i jakość', async () => {
    renderAreaSegments();

    const toggle = await screen.findByLabelText('options-toggle-ceiling');
    expect(toggle).toBeInTheDocument();
    const workPlan = screen.getByLabelText(`work-plan-${ceilingSurfaceId}`);
    expect(workPlan).toBeInTheDocument();
    expect(workPlan).toHaveTextContent('Rodzaje prac i jakość');
  });

  it('I: CEILING WorkPlan button uses the canonical CEILING Surface.id', async () => {
    renderAreaSegments();

    const workPlan = await screen.findByLabelText(`work-plan-${ceilingSurfaceId}`);
    expect(workPlan.getAttribute('aria-label')).toBe(`work-plan-${ceilingSurfaceId}`);
  });

  it('J/K: CEILING actions hidden collapsed, visible expanded', async () => {
    renderAreaSegments();

    const toggle = await screen.findByLabelText('options-toggle-ceiling');
    expect(screen.queryByLabelText('add-ceiling-rectangle')).not.toBeInTheDocument();

    await expandPlane('ceiling');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('add-ceiling-rectangle')).toBeInTheDocument();
    expect(screen.getByLabelText('add-ceiling-subtraction')).toBeInTheDocument();
  });

  it('L: opening FLOOR does not expand CEILING', async () => {
    renderAreaSegments();

    await screen.findByLabelText('options-toggle-floor');
    await expandPlane('floor');
    expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument();
    expect(screen.queryByLabelText('add-ceiling-rectangle')).not.toBeInTheDocument();
    expect(screen.getByLabelText('options-toggle-ceiling')).toHaveAttribute('aria-expanded', 'false');
  });

  it('M: opening CEILING does not expand FLOOR', async () => {
    renderAreaSegments();

    await screen.findByLabelText('options-toggle-ceiling');
    await expandPlane('ceiling');
    expect(screen.getByLabelText('add-ceiling-rectangle')).toBeInTheDocument();
    expect(screen.queryByLabelText('add-floor-rectangle')).not.toBeInTheDocument();
    expect(screen.getByLabelText('options-toggle-floor')).toHaveAttribute('aria-expanded', 'false');
  });

  it('opens canonical FLOOR and CEILING WorkPlans independently from measurement Opcje', async () => {
    renderAreaSegments();

    const floorWorkPlan = await screen.findByLabelText(`work-plan-${floorSurfaceId}`);
    const ceilingWorkPlan = screen.getByLabelText(`work-plan-${ceilingSurfaceId}`);
    expect(screen.queryByLabelText('add-floor-rectangle')).not.toBeInTheDocument();

    fireEvent.click(floorWorkPlan);
    const floorEditor = await screen.findByLabelText(`work-plan-editor-${floorSurfaceId}`);
    expect(floorEditor).toHaveTextContent('Podłoga');
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(
      projectId,
      roomId,
      floorSurfaceId,
    );
    expect(screen.queryByLabelText('add-floor-rectangle')).not.toBeInTheDocument();

    await expandPlane('floor');
    expect(screen.getByLabelText(`work-plan-editor-${floorSurfaceId}`)).toBeInTheDocument();
    expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument();

    fireEvent.click(ceilingWorkPlan);
    const ceilingEditor = await screen.findByLabelText(`work-plan-editor-${ceilingSurfaceId}`);
    expect(ceilingEditor).toHaveTextContent('Sufit');
    expect(screen.queryByLabelText(`work-plan-editor-${floorSurfaceId}`)).not.toBeInTheDocument();
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(
      projectId,
      roomId,
      ceilingSurfaceId,
    );
    expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument();
    expect(screen.queryByLabelText('add-ceiling-rectangle')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(`close-work-plan-${ceilingSurfaceId}`));
    expect(screen.queryByLabelText(`work-plan-editor-${ceilingSurfaceId}`)).not.toBeInTheDocument();
    expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument();
  });

  it('localizes canonical FLOOR and CEILING cards and WorkPlan titles in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderAreaSegments();

    expect(await screen.findByText('Пол')).toBeInTheDocument();
    expect(screen.getByText('Потолок')).toBeInTheDocument();

    fireEvent.click(await screen.findByLabelText(`work-plan-${floorSurfaceId}`));
    const floorEditor = await screen.findByLabelText(`work-plan-editor-${floorSurfaceId}`);
    expect(floorEditor).toHaveTextContent('Пол');
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(
      projectId,
      roomId,
      floorSurfaceId,
    );

    fireEvent.click(screen.getByLabelText(`work-plan-${ceilingSurfaceId}`));
    const ceilingEditor = await screen.findByLabelText(`work-plan-editor-${ceilingSurfaceId}`);
    expect(ceilingEditor).toHaveTextContent('Потолок');
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledWith(
      projectId,
      roomId,
      ceilingSurfaceId,
    );
  });

  it('N/O: zero-segment FLOOR and CEILING still expose the canonical Surface.id / Work Plan button', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({
      items: [],
      total: 0,
      planes: {
        FLOOR: { base_area: '12.210', adjustment_area: '0.000', net_area: '12.210' },
        CEILING: { base_area: '12.210', adjustment_area: '0.000', net_area: '12.210' },
      },
    });
    renderAreaSegments();

    expect(await screen.findByLabelText(`work-plan-${floorSurfaceId}`)).toBeInTheDocument();
    expect(screen.getByLabelText(`work-plan-${ceilingSurfaceId}`)).toBeInTheDocument();
    expect(screen.getAllByText(/Razem: 12\.21 m²/)).toHaveLength(2);
  });
});
