import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as areaSegmentsApi from './api/areaSegments';
import * as surfacesApi from './api/surfaces';
import * as workPlansApi from './api/workPlans';
import { ApiError } from './api/http';
import { AreaSegmentList } from './components/AreaSegmentList';
import { I18nProvider } from './hooks/useI18n';
import { ProjectPhotosContext } from './hooks/ProjectPhotosContext';
import { EMPTY_PHOTO_COUNTS } from './hooks/usePhotoCounts';
import { AreaSegmentType } from './types/areaSegment';
import { SurfaceListResponse } from './types/surface';

vi.mock('./api/areaSegments', () => ({
  fetchAreaSegments: vi.fn(),
  createAreaSegment: vi.fn(),
  updateAreaSegment: vi.fn(),
  archiveAreaSegment: vi.fn(),
  restoreAreaSegment: vi.fn(),
  reorderAreaSegments: vi.fn(),
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

function renderAreaSegments(onMeasurementChanged = vi.fn(), onInspectPlane?: (plane: 'FLOOR' | 'CEILING') => void) {
  return render(
    <I18nProvider>
      <AreaSegmentList
        projectId={projectId}
        roomId={roomId}
        initiallyOpen
        onMeasurementChanged={onMeasurementChanged}
        onInspectPlane={onInspectPlane}
      />
    </I18nProvider>,
  );
}

function areaList(key: string) {
  return (
    <I18nProvider>
      <AreaSegmentList projectId={projectId} roomId={roomId} dimensionsKey={key} initiallyOpen />
    </I18nProvider>
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

  it('renders the section title with the theme-aware text color, not a hardcoded dark slate class (Stage 10H.1)', async () => {
    // Regression: a hardcoded `text-slate-900` on page-level (non-card) text
    // never adapts to Telegram's dark theme, where the page background is
    // itself dark — the heading became invisible dark-on-dark.
    renderAreaSegments();
    const heading = await screen.findByText('Podłoga i sufit');
    expect(heading.className).toContain('text-[var(--tg-theme-text-color)]');
    expect(heading.className).not.toContain('text-slate-900');
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
    expect(screen.getByText(/3,00 × 2,00 m/)).toBeInTheDocument();
    expect(screen.getByText('6,00 m²')).toBeInTheDocument();
    expect(screen.getByText('Sufit salon')).toBeInTheDocument();
    expect(screen.getByText('10,00 m²')).toBeInTheDocument();
  });

  it('computes "Razem" plane totals as additions minus subtractions', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({
      items: [floorAdd, floorSubtract],
      total: 2,
    });
    renderAreaSegments();

    // Floor net = 6.000 - 1.000 = 5.000
    await waitFor(() => expect(screen.getByText(/Razem: 5,00 m²/)).toBeInTheDocument());
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

    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '300' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '200' } });
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
    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '100' } });
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
    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '200' } });
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

    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '400' } });
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

    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '-200' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '0' } });
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Podaj poprawną szerokość i długość (cm)');
    expect(areaSegmentsApi.createAreaSegment).not.toHaveBeenCalled();
    // Form stays open for correction
    expect(screen.getByLabelText('segment-width')).toHaveValue('-200');
  });

  it('displays a readable 422 negative-net error without losing the form input', async () => {
    vi.mocked(areaSegmentsApi.createAreaSegment).mockRejectedValue(
      new Error('Net area (-1.000) cannot be negative for a plane'),
    );
    renderAreaSegments();

    await expandPlane('floor');
    await waitFor(() => expect(screen.getByLabelText('add-floor-subtraction')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('add-floor-subtraction'));

    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '300' } });
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('cannot be negative');
    expect(screen.getByLabelText('segment-width')).toHaveValue('500');
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

    await waitFor(() => expect(screen.getAllByText(/Razem: 12,21 m²/)).toHaveLength(2));
    expect(screen.getAllByText('Powierzchnia bazowa')).toHaveLength(2);
    expect(screen.getAllByText('12,21 m²').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Korekty')).toHaveLength(2);
    // Empty-state copy is still present for the no-segments list (behind Opcje)
    await expandPlane('floor');
    expect(screen.getByText('Brak prostokątów podłogi')).toBeInTheDocument();
  });

  it('re-reads the plane totals when the room size is corrected, and not when it is unchanged', async () => {
    const planes = (area: string) => ({
      FLOOR: { base_area: area, adjustment_area: '0.000', net_area: area },
      CEILING: { base_area: area, adjustment_area: '0.000', net_area: area },
    });
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValueOnce({ items: [], total: 0, planes: planes('9.470') });
    const view = render(areaList('3.73|2.54|2.68'));
    await waitFor(() => expect(screen.getAllByText(/Razem: 9,47 m²/)).toHaveLength(2));

    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0, planes: planes('8.650') });
    view.rerender(areaList('3.73|2.54|2.68'));
    expect(areaSegmentsApi.fetchAreaSegments).toHaveBeenCalledTimes(1);

    view.rerender(areaList('3.73|2.32|2.68'));
    await waitFor(() => expect(screen.getAllByText(/Razem: 8,65 m²/)).toHaveLength(2));
    expect(screen.queryByText(/Razem: 9,47 m²/)).not.toBeInTheDocument();
    expect(areaSegmentsApi.fetchAreaSegments).toHaveBeenCalledTimes(2);
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

    await waitFor(() => expect(screen.getByText(/Razem: 11,65 m²/)).toBeInTheDocument());
    expect(screen.getByText('-0,56 m²')).toBeInTheDocument();
    expect(screen.getByText(/Razem: 12,21 m²/)).toBeInTheDocument();
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
    expect(screen.queryByText(/Razem: 0,000 m²/)).not.toBeInTheDocument();
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
    expect(workPlan).toHaveTextContent('Plan');
    expect(screen.getByLabelText(`plan-tabs-${floorSurfaceId}`).parentElement).toHaveTextContent('Rodzaje prac i jakość'); // usability U-5: Plan | Realizacja under the caption
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
    expect(workPlan).toHaveTextContent('Plan');
    expect(screen.getByLabelText(`plan-tabs-${ceilingSurfaceId}`).parentElement).toHaveTextContent('Rodzaje prac i jakość');
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
    expect(screen.getAllByText(/Razem: 12,21 m²/)).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Stage 10G.4 — deterministic surface-type card tints (FLOOR/CEILING)
// ---------------------------------------------------------------------------

describe('AreaSegmentList — surface type card tints (Stage 10G.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(canonicalPlanes);
  });

  it('gives the FLOOR card a warm/sand tint family', async () => {
    renderAreaSegments();
    const floorCard = await screen.findByLabelText('floor-segments');
    expect(floorCard.className).toContain('bg-orange-50');
    expect(floorCard.className).toContain('border-orange-100');
  });

  it('gives the CEILING card a cool gray-blue tint family, distinct from FLOOR and WALL', async () => {
    renderAreaSegments();
    const ceilingCard = await screen.findByLabelText('ceiling-segments');
    expect(ceilingCard.className).toContain('bg-slate-100');
    expect(ceilingCard.className).toContain('border-slate-300');
    expect(ceilingCard.className).not.toContain('bg-orange-50');
    expect(ceilingCard.className).not.toContain('bg-blue-50');
  });

  it('preserves existing Opcje/Rodzaje prac i jakość actions on the tinted FLOOR/CEILING cards', async () => {
    renderAreaSegments();
    await screen.findByLabelText('floor-segments');
    expect(screen.getByLabelText('options-toggle-floor')).toBeInTheDocument();
    expect(screen.getByLabelText(`work-plan-${floorSurfaceId}`)).toBeInTheDocument();
    expect(screen.getByLabelText('options-toggle-ceiling')).toBeInTheDocument();
    expect(screen.getByLabelText(`work-plan-${ceilingSurfaceId}`)).toBeInTheDocument();
  });
});

describe('AreaSegmentList plane inspection in Opcje (13F-PRE)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(canonicalPlanes);
  });

  it('the inspection of the ceiling and of the floor is on its card, outside Opcje (Stage 18G; the floor since UX walk B4)', async () => {
    const onInspectPlane = vi.fn();
    renderAreaSegments(vi.fn(), onInspectPlane);
    const floorToggle = await screen.findByLabelText('options-toggle-floor');
    // visible without opening anything, above the Opcje toggle of its card
    const ceilingButton = screen.getByLabelText('inspect-ceiling');
    expect(ceilingButton.compareDocumentPosition(screen.getByLabelText('options-toggle-ceiling')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByLabelText('add-ceiling-rectangle')).not.toBeInTheDocument();

    fireEvent.click(floorToggle);
    expect(screen.getByLabelText('add-floor-rectangle')).toBeInTheDocument(); // Opcje open
    const floorButton = screen.getByLabelText('inspect-floor');
    expect(floorButton).toHaveTextContent('Badanie podłogi');
    expect(floorButton.compareDocumentPosition(floorToggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); // above Opcje, like the ceiling's

    expect(ceilingButton).toHaveTextContent('Badanie sufitu');
    fireEvent.click(ceilingButton);
    expect(onInspectPlane).toHaveBeenCalledTimes(1);
    expect(onInspectPlane).toHaveBeenCalledWith('CEILING');
    fireEvent.click(floorButton);
    expect(onInspectPlane).toHaveBeenLastCalledWith('FLOOR');
  });

  it('plane controls are compact (owner request, Stage 18G): 40 px high with little vertical padding, the inspection a calm green', async () => {
    renderAreaSegments(vi.fn(), vi.fn());
    fireEvent.click(await screen.findByLabelText('options-toggle-ceiling'));
    for (const label of ['add-ceiling-rectangle', 'add-ceiling-subtraction', 'inspect-ceiling', 'options-toggle-ceiling']) {
      expect(screen.getByLabelText(label).className).toContain('min-h-11');
      expect(screen.getByLabelText(label).className).toMatch(/\bpy-1\b/);
    }
    expect(screen.getByLabelText('inspect-ceiling').className).toContain('bg-emerald-50');
  });

  it('renders no inspection button when no handler is given', async () => {
    renderAreaSegments();
    await screen.findByLabelText('options-toggle-ceiling');
    expect(screen.queryByLabelText('inspect-ceiling')).not.toBeInTheDocument();
  });

  it('labels the plane inspection in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderAreaSegments(vi.fn(), vi.fn());
    await screen.findByLabelText('options-toggle-ceiling');
    expect(screen.getByLabelText('inspect-ceiling')).toHaveTextContent(/потолка/);
  });
});

describe('Realizacja entry on floor/ceiling planes (Stage 13H.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(canonicalPlanes);
  });

  it('each plane has its own Realizacja bound to the canonical Surface.id, exclusive with the editor', async () => {
    renderAreaSegments();
    const floor = await screen.findByLabelText(`execution-${floorSurfaceId}`);
    expect(screen.getByLabelText(`execution-${ceilingSurfaceId}`)).toHaveTextContent('Realizacja');
    fireEvent.click(floor);
    expect(await screen.findByLabelText(`execution-view-${floorSurfaceId}`)).toBeInTheDocument();
    expect(await screen.findByLabelText(`execution-empty-${floorSurfaceId}`)).toHaveTextContent('nie zawiera jeszcze żadnych prac');
    fireEvent.click(screen.getByLabelText(`work-plan-${floorSurfaceId}`));
    expect(await screen.findByLabelText(`work-plan-editor-${floorSurfaceId}`)).toBeInTheDocument();
    expect(screen.queryByLabelText(`execution-view-${floorSurfaceId}`)).not.toBeInTheDocument();
  });
});


describe('The same rectangle on the other plane (Stage 18G)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [floorAdd], total: 1 });
    vi.mocked(areaSegmentsApi.createAreaSegment).mockResolvedValue(floorAdd);
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(canonicalPlanes);
  });

  async function openForm(plane: 'floor' | 'ceiling', op: 'rectangle' | 'subtraction') {
    renderAreaSegments();
    await expandPlane(plane);
    fireEvent.click(await screen.findByLabelText(`add-${plane}-${op}`));
    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '250' } });
    fireEvent.change(screen.getByLabelText('segment-height'), { target: { value: '300' } });
  }

  it('creates the rectangle on both planes when the button is pressed, in metres', async () => {
    await openForm('floor', 'rectangle');
    const toggle = screen.getByLabelText('segment-also-opposite');
    expect(toggle).toHaveTextContent('Dodaj też do sufitu');
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    await waitFor(() => expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledTimes(2));
    expect(areaSegmentsApi.createAreaSegment).toHaveBeenNthCalledWith(1, projectId, roomId, { plane: 'FLOOR', operation: 'ADD', width: 2.5, height: 3, label: null });
    expect(areaSegmentsApi.createAreaSegment).toHaveBeenNthCalledWith(2, projectId, roomId, { plane: 'CEILING', operation: 'ADD', width: 2.5, height: 3, label: null });
    expect(await screen.findByText('Prostokąt dodano na podłodze i suficie')).toBeInTheDocument();
  });

  it('a subtraction on the ceiling is copied to the floor as a subtraction', async () => {
    await openForm('ceiling', 'subtraction');
    expect(screen.getByLabelText('segment-also-opposite')).toHaveTextContent('Dodaj też do podłogi');
    fireEvent.click(screen.getByLabelText('segment-also-opposite'));
    fireEvent.submit(screen.getByLabelText('ceiling-segment-form'));

    await waitFor(() => expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledTimes(2));
    expect(areaSegmentsApi.createAreaSegment).toHaveBeenNthCalledWith(2, projectId, roomId, { plane: 'FLOOR', operation: 'SUBTRACT', width: 2.5, height: 3, label: null });
  });

  it('creates only one rectangle when the button is not pressed', async () => {
    await openForm('floor', 'rectangle');
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));
    await waitFor(() => expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledTimes(1));
  });

  it('says what is missing when the second rectangle fails, and the first one stays', async () => {
    vi.mocked(areaSegmentsApi.createAreaSegment).mockResolvedValueOnce(floorAdd).mockRejectedValueOnce(new Error('Net area (-1.000) cannot be negative for a plane'));
    await openForm('floor', 'rectangle');
    fireEvent.click(screen.getByLabelText('segment-also-opposite'));
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Pierwszy prostokąt zapisano, ale drugiego nie udało się dodać:');
    expect(screen.getByRole('alert')).toHaveTextContent('Net area (-1.000)');
    expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledTimes(2);
  });

  it('has no such button while editing a rectangle', async () => {
    renderAreaSegments();
    await expandPlane('floor');
    fireEvent.click(await screen.findByLabelText(`edit-segment-${floorAdd.id}`));
    expect(screen.queryByLabelText('segment-also-opposite')).not.toBeInTheDocument();
  });

  it('copies an existing rectangle to the other plane with one tap', async () => {
    renderAreaSegments();
    await expandPlane('floor');
    const copy = await screen.findByLabelText(`copy-segment-${floorAdd.id}`);
    expect(copy).toHaveTextContent('Na sufit');
    fireEvent.click(copy);

    await waitFor(() => expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledWith(projectId, roomId, {
      plane: 'CEILING', operation: 'ADD', width: 3, height: 2, label: 'Parkiet wejście',
    }));
    expect(await screen.findByText('Prostokąt skopiowano na drugą płaszczyznę')).toBeInTheDocument();
  });

  it('speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    await openForm('floor', 'rectangle');
    expect(screen.getByLabelText('segment-also-opposite')).toHaveTextContent('Добавить и на потолок');
    expect(screen.getByLabelText(`copy-segment-${floorAdd.id}`)).toHaveTextContent('На потолок');
  });
});


describe('Floor and ceiling rows (Stage 18H)', () => {
  const photosValue = (surfaces: Record<string, number>) => ({
    projectId,
    counts: { ...EMPTY_PHOTO_COUNTS, surfaces },
    isExpanded: () => false,
    toggle: () => {},
    adjust: () => {},
    resolveLocation: () => '',
    ensureLocations: () => {},
  });
  const renderRows = () =>
    render(
      <I18nProvider>
        <ProjectPhotosContext.Provider value={photosValue({ [ceilingSurfaceId]: 1, [floorSurfaceId]: 4 })}>
          <AreaSegmentList projectId={projectId} roomId={roomId} />
        </ProjectPhotosContext.Provider>
      </I18nProvider>,
    );
  const planes = (area: string) => ({
    FLOOR: { base_area: area, adjustment_area: '0.000', net_area: area },
    CEILING: { base_area: area, adjustment_area: '0.000', net_area: area },
  });

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0, planes: planes('20.000') });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(canonicalPlanes);
  });

  it('shows the ceiling and the floor as one-line rows: name, photos, area — and nothing else', async () => {
    renderRows();

    const ceiling = await screen.findByLabelText('surface-row-plane-ceiling');
    expect(ceiling).toHaveTextContent('Sufit');
    await waitFor(() => expect(screen.getByLabelText('surface-row-photos-plane-ceiling')).toHaveTextContent('1'));
    expect(screen.getByLabelText('surface-row-area-plane-ceiling')).toHaveTextContent('20,00 m²');
    expect(screen.getByLabelText('surface-row-plane-floor')).toHaveTextContent('Podłoga');
    expect(screen.getByLabelText('surface-row-photos-plane-floor')).toHaveTextContent('4');
    expect(ceiling.className).toContain('min-h-11');
    // no card behind the rows
    expect(screen.queryByLabelText('options-toggle-ceiling')).toBeNull();
    expect(screen.queryByLabelText('inspect-ceiling')).toBeNull();
    expect(screen.queryByText('Powierzchnia bazowa')).toBeNull();
  });

  it('a tap opens the card of that plane only, and a tap on its name folds it back', async () => {
    renderRows();
    fireEvent.click(await screen.findByLabelText('surface-row-plane-ceiling'));

    expect(screen.getByLabelText('options-toggle-ceiling')).toBeInTheDocument();
    expect(screen.getByLabelText('ceiling-segments')).toBeInTheDocument();
    expect(screen.queryByLabelText('surface-row-plane-ceiling')).toBeNull();
    expect(screen.getByLabelText('surface-row-plane-floor')).toBeInTheDocument();
    expect(screen.queryByLabelText('options-toggle-floor')).toBeNull();

    fireEvent.click(screen.getByLabelText('plane-collapse-ceiling'));
    expect(screen.getByLabelText('surface-row-plane-ceiling')).toBeInTheDocument();
    expect(screen.queryByLabelText('options-toggle-ceiling')).toBeNull();
  });

  it('a plane without any area yet shows a dash', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0 });
    renderRows();
    expect(await screen.findByLabelText('surface-row-area-plane-floor')).toHaveTextContent('—');
  });

  it('follows a corrected room size: the row shows the new area', async () => {
    const view = renderRows();
    await waitFor(() => expect(screen.getByLabelText('surface-row-area-plane-floor')).toHaveTextContent('20,00 m²'));
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [], total: 0, planes: planes('8.650') });
    view.rerender(
      <I18nProvider>
        <ProjectPhotosContext.Provider value={photosValue({})}>
          <AreaSegmentList projectId={projectId} roomId={roomId} dimensionsKey="2.32" />
        </ProjectPhotosContext.Provider>
      </I18nProvider>,
    );
    await waitFor(() => expect(screen.getByLabelText('surface-row-area-plane-floor')).toHaveTextContent('8,65 m²'));
  });

  it('speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderRows();
    expect(await screen.findByLabelText('surface-row-plane-ceiling')).toHaveTextContent('Потолок');
    expect(screen.getByLabelText('surface-row-plane-floor')).toHaveTextContent('Пол');
  });
});

describe('AreaSegmentList: the rows of the rectangles (owner request, Stage 19)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('give the name and the numbers the whole width, and the buttons their own line (they were squeezed into a narrow column)', async () => {
    const long = { ...floorAdd, label: 'Parkiet w przedpokoju przy wejściu głównym' };
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [long], total: 1 });
    renderAreaSegments();
    await expandPlane('floor');
    const row = await screen.findByLabelText(`segment-item-${floorAdd.id}`);

    expect(row.className).toMatch(/flex-col/); // stacked: info first, buttons below
    expect(row.className).not.toMatch(/justify-between/);
    const name = screen.getByText('Parkiet w przedpokoju przy wejściu głównym');
    expect(name.className).toMatch(/break-words/);
    expect(name.className).not.toMatch(/truncate/); // the name is never cut to "Co …"
    expect(row).toHaveTextContent('3,00 × 2,00 m = 6,00 m²');
    const numbers = within(row).getByText(/3,00 × 2,00 m/).closest('p');
    expect(numbers?.className).toMatch(/break-words/);
    const buttons = within(row).getByLabelText(`edit-segment-${floorAdd.id}`).parentElement;
    expect(buttons?.className).toMatch(/flex-wrap/);
    expect(buttons).not.toBe(numbers?.parentElement); // not in the same line as the numbers
    for (const label of [`edit-segment-${floorAdd.id}`, `copy-segment-${floorAdd.id}`, `archive-segment-${floorAdd.id}`]) {
      expect(within(row).getByLabelText(label).className).toMatch(/min-h-11/);
    }
  });

  it('a rectangle being changed is changed IN ITS OWN PLACE, not in a form above a long list', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [floorAdd, floorSubtract], total: 2 });
    renderAreaSegments();
    await expandPlane('floor');
    fireEvent.click(await screen.findByLabelText(`edit-segment-${floorSubtract.id}`));

    const place = await screen.findByLabelText(`segment-editing-${floorSubtract.id}`);
    expect(within(place).getByLabelText('floor-segment-form')).toBeInTheDocument();
    expect(within(place).getByLabelText('segment-width')).toHaveValue('100'); // centimetres
    expect(screen.getAllByLabelText('floor-segment-form')).toHaveLength(1); // not a second one above the list
    expect(screen.queryByLabelText(`segment-item-${floorSubtract.id}`)).toBeNull(); // the row gives way to it
    expect(screen.getByLabelText(`segment-item-${floorAdd.id}`)).toBeInTheDocument(); // the others stay
  });

  it('a new rectangle is still added in the form above the list', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [floorAdd], total: 1 });
    renderAreaSegments();
    await expandPlane('floor');
    fireEvent.click(await screen.findByLabelText('add-floor-rectangle'));
    const form = await screen.findByLabelText('floor-segment-form');
    expect(form.closest('li')).toBeNull();
    expect(screen.getByLabelText(`segment-item-${floorAdd.id}`)).toBeInTheDocument();
  });

  it('saving the change closes the place and shows the new numbers', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValueOnce({ items: [floorAdd], total: 1 }).mockResolvedValue({ items: [{ ...floorAdd, width: 4, area: '8.000' }], total: 1 });
    vi.mocked(areaSegmentsApi.updateAreaSegment).mockResolvedValue({ ...floorAdd, width: 4, area: '8.000' });
    renderAreaSegments();
    await expandPlane('floor');
    fireEvent.click(await screen.findByLabelText(`edit-segment-${floorAdd.id}`));
    fireEvent.change(screen.getByLabelText('segment-width'), { target: { value: '400' } });
    fireEvent.submit(screen.getByLabelText('floor-segment-form'));

    expect(await screen.findByText(/4,00 × 2,00 m/)).toBeInTheDocument();
    expect(screen.queryByLabelText(`segment-editing-${floorAdd.id}`)).toBeNull();
  });
});


describe('AreaSegmentList duplicate and order (owner 2026-10-29)', () => {
  const second: AreaSegmentType = { ...floorAdd, id: 'dddddddd-dddd-dddd-dddd-dddddddddddd', width: 4, height: 1, area: '4.000', position: 1, label: 'Drugi' };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [floorAdd, second], total: 2 });
    vi.mocked(surfacesApi.fetchSurfaces).mockResolvedValue(canonicalPlanes);
  });

  it('duplicates a rectangle and puts the copy right behind the original', async () => {
    const onMeasurementChanged = vi.fn();
    const copy = { ...floorAdd, id: 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', position: null };
    vi.mocked(areaSegmentsApi.createAreaSegment).mockResolvedValue(copy);
    vi.mocked(areaSegmentsApi.reorderAreaSegments).mockResolvedValue({ items: [floorAdd, copy, second], total: 3 });
    renderAreaSegments(onMeasurementChanged);

    await expandPlane('floor');
    fireEvent.click(await screen.findByLabelText(`duplicate-segment-${floorAdd.id}`));

    await waitFor(() =>
      expect(areaSegmentsApi.createAreaSegment).toHaveBeenCalledWith(projectId, roomId, {
        plane: 'FLOOR',
        operation: 'ADD',
        width: 3,
        height: 2,
        label: 'Parkiet wejście',
      }),
    );
    await waitFor(() =>
      expect(areaSegmentsApi.reorderAreaSegments).toHaveBeenCalledWith(projectId, roomId, 'FLOOR', [floorAdd.id, copy.id, second.id]),
    );
    expect(onMeasurementChanged).toHaveBeenCalledTimes(1);
  });

  it('keeps the copy when only the ordering fails', async () => {
    const copy = { ...floorAdd, id: 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', position: null };
    vi.mocked(areaSegmentsApi.createAreaSegment).mockResolvedValue(copy);
    vi.mocked(areaSegmentsApi.reorderAreaSegments).mockRejectedValue(new Error('down'));
    renderAreaSegments();

    await expandPlane('floor');
    fireEvent.click(await screen.findByLabelText(`duplicate-segment-${floorAdd.id}`));

    expect(await screen.findByText(/zduplikowano/)).toBeInTheDocument();
  });

  it('shows the order button only with two or more rectangles', async () => {
    vi.mocked(areaSegmentsApi.fetchAreaSegments).mockResolvedValue({ items: [floorAdd], total: 1 });
    renderAreaSegments();
    await expandPlane('floor');
    await screen.findByLabelText(`duplicate-segment-${floorAdd.id}`);
    expect(screen.queryByLabelText('reorder-floor-start')).toBeNull();
  });

  it('moves a rectangle with the arrows, saves the order at once and leaves with Gotowe', async () => {
    vi.mocked(areaSegmentsApi.reorderAreaSegments).mockResolvedValue({ items: [second, floorAdd], total: 2 });
    renderAreaSegments();

    await expandPlane('floor');
    fireEvent.click(await screen.findByLabelText('reorder-floor-start'));
    expect(screen.getByLabelText(`segment-up-${floorAdd.id}`)).toBeDisabled();
    expect(screen.getByLabelText(`segment-down-${second.id}`)).toBeDisabled();

    fireEvent.click(screen.getByLabelText(`segment-up-${second.id}`));
    await waitFor(() =>
      expect(areaSegmentsApi.reorderAreaSegments).toHaveBeenCalledWith(projectId, roomId, 'FLOOR', [second.id, floorAdd.id]),
    );
    const rows = screen.getAllByLabelText(/^segment-order-/).map((row) => row.getAttribute('aria-label'));
    expect(rows).toEqual([`segment-order-${second.id}`, `segment-order-${floorAdd.id}`]);

    fireEvent.click(screen.getByLabelText('reorder-floor-done'));
    expect(screen.queryByLabelText('reorder-floor-done')).toBeNull();
  });

  it('reloads the real order and tells it when the server says the list has changed', async () => {
    vi.mocked(areaSegmentsApi.reorderAreaSegments).mockRejectedValue(new ApiError('x', 409, 'AREA_REORDER_NOT_CURRENT'));
    renderAreaSegments();

    await expandPlane('floor');
    fireEvent.click(await screen.findByLabelText('reorder-floor-start'));
    const loads = vi.mocked(areaSegmentsApi.fetchAreaSegments).mock.calls.length;
    fireEvent.click(screen.getByLabelText(`segment-up-${second.id}`));

    expect(await screen.findByText(/Lista się zmieniła/)).toBeInTheDocument();
    expect(vi.mocked(areaSegmentsApi.fetchAreaSegments).mock.calls.length).toBeGreaterThan(loads);
  });
});
