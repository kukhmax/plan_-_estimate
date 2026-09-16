import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as workPlansApi from './api/workPlans';
import { ApiError } from './api/http';
import { SurfaceWorkPlanEditor } from './components/SurfaceWorkPlanEditor';
import { I18nProvider } from './hooks/useI18n';
import { SurfaceWorkPlanRead } from './types/workPlan';

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
const surfaceId = '33333333-3333-3333-3333-333333333333';

const plannedWorks: SurfaceWorkPlanRead['planned_works'] = [
  {
    id: 'occurrence-1',
    work_plan_id: 'plan-1',
    price_item_id: 'price-shared',
    position: 0,
    price_item: {
      id: 'price-shared',
      code: 'CUSTOM_1',
      name_key: null,
      display_name: 'Pierwsza praca',
      category: 'PREPARATION',
      unit: 'M2',
      price_scope: 'LABOR',
      price: '45.50',
      currency: 'PLN',
      is_archived: false,
      quality_level: null,
    },
  },
  {
    id: 'occurrence-2',
    work_plan_id: 'plan-1',
    price_item_id: 'price-localized',
    position: 1,
    price_item: {
      id: 'price-localized',
      code: 'PAINT_2K',
      name_key: 'pricebook.seed.paint_2k',
      display_name: null,
      category: 'PAINTING',
      unit: 'M2',
      price_scope: 'LABOR_AND_MATERIAL',
      price: '60.00',
      currency: 'PLN',
      is_archived: false,
      quality_level: 'S3',
    },
  },
  {
    id: 'occurrence-3',
    work_plan_id: 'plan-1',
    price_item_id: 'price-shared',
    position: 2,
    price_item: {
      id: 'price-shared',
      code: 'CUSTOM_1',
      name_key: null,
      display_name: 'Pierwsza praca',
      category: 'PREPARATION',
      unit: 'M2',
      price_scope: 'LABOR',
      price: null,
      currency: 'PLN',
      is_archived: true,
      quality_level: null,
    },
  },
  {
    id: 'occurrence-4',
    work_plan_id: 'plan-1',
    price_item_id: 'price-unavailable',
    position: 3,
    price_item: null,
  },
];

function makePlan(overrides: Partial<SurfaceWorkPlanRead> = {}): SurfaceWorkPlanRead {
  return {
    id: 'plan-1',
    surface_id: surfaceId,
    substrate: 'CONCRETE',
    quality_target: 'S3',
    planned_works: plannedWorks,
    ...overrides,
  };
}

function renderEditor(id = surfaceId) {
  return render(
    <I18nProvider>
      <SurfaceWorkPlanEditor
        projectId={projectId}
        roomId={roomId}
        surfaceId={id}
        surfaceName="Ściana północna"
        onClose={vi.fn()}
      />
    </I18nProvider>,
  );
}

describe('SurfaceWorkPlanEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(makePlan());
  });

  it('shows loading and hydrates the existing header and ordered read-only preview', async () => {
    let resolvePlan!: (plan: SurfaceWorkPlanRead) => void;
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockReturnValue(
      new Promise((resolve) => {
        resolvePlan = resolve;
      }),
    );

    renderEditor();
    expect(screen.getByText('Ładowanie planu prac...')).toBeInTheDocument();

    await act(async () => resolvePlan(makePlan()));

    expect(await screen.findByLabelText(`work-plan-substrate-${surfaceId}`)).toHaveValue('CONCRETE');
    expect(screen.getByLabelText(`work-plan-quality-${surfaceId}`)).toHaveValue('S3');

    const rows = within(screen.getByLabelText(`planned-works-${surfaceId}`)).getAllByRole('listitem');
    expect(rows).toHaveLength(4);
    expect(rows[0]).toHaveTextContent('Pierwsza praca');
    expect(rows[1]).toHaveTextContent('Malowanie ścian — 2 warstwy (standard)');
    expect(rows[2]).toHaveTextContent('Pierwsza praca');
    expect(rows[2]).toHaveTextContent('Do ustalenia');
    expect(rows[2]).toHaveTextContent('Zarchiwizowana');
    expect(rows[3]).toHaveTextContent('Pozycja cennika jest niedostępna');
    expect(screen.getByLabelText(`save-work-plan-${surfaceId}`)).toBeDisabled();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
  });

  it('treats only the exact no-plan 404 as an editable empty state without creating a plan', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValue(
      new ApiError('Surface work plan not found', 404),
    );

    renderEditor();

    expect(await screen.findByText('Brak zapisanego planu prac dla tej powierzchni.')).toBeInTheDocument();
    expect(screen.getByLabelText(`work-plan-substrate-${surfaceId}`)).toHaveValue('');
    expect(screen.getByLabelText(`work-plan-quality-${surfaceId}`)).toBeDisabled();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
  });

  it('shows other load failures and retries the same canonical surface', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan)
      .mockRejectedValueOnce(new ApiError('Surface not found', 404))
      .mockResolvedValueOnce(makePlan());

    renderEditor();

    expect(await screen.findByText('Nie udało się załadować planu prac.')).toBeInTheDocument();
    expect(screen.getByText('Surface not found')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(`retry-work-plan-${surfaceId}`));

    expect(await screen.findByLabelText(`work-plan-form-${surfaceId}`)).toBeInTheDocument();
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(2);
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenLastCalledWith(
      projectId,
      roomId,
      surfaceId,
    );
  });

  it('offers the compatible quality family and clears quality on incompatible substrate changes', async () => {
    renderEditor();

    const substrate = await screen.findByLabelText(`work-plan-substrate-${surfaceId}`);
    const quality = screen.getByLabelText(`work-plan-quality-${surfaceId}`);
    expect(within(quality).getByRole('option', { name: 'Klasa S1' })).toBeInTheDocument();
    expect(within(quality).queryByRole('option', { name: 'Klasa Q1' })).not.toBeInTheDocument();

    fireEvent.change(substrate, { target: { value: 'OTHER' } });
    expect(quality).toHaveValue('');
    expect(within(quality).getByRole('option', { name: 'Klasa S1' })).toBeInTheDocument();
    expect(within(quality).getByRole('option', { name: 'Klasa Q1' })).toBeInTheDocument();

    fireEvent.change(substrate, { target: { value: 'CONCRETE' } });
    fireEvent.change(quality, { target: { value: 'S3' } });
    fireEvent.change(substrate, { target: { value: 'GYPSUM_BOARD' } });
    expect(quality).toHaveValue('');
    expect(within(quality).queryByRole('option', { name: 'Klasa S1' })).not.toBeInTheDocument();
    expect(within(quality).getByRole('option', { name: 'Klasa Q1' })).toBeInTheDocument();

    fireEvent.change(quality, { target: { value: 'Q3' } });
    fireEvent.change(substrate, { target: { value: 'PAINTED' } });
    expect(quality).toHaveValue('');
    expect(within(quality).getByRole('option', { name: 'Klasa S1' })).toBeInTheDocument();
    expect(within(quality).getByRole('option', { name: 'Klasa Q1' })).toBeInTheDocument();
  });

  it('saves the header while preserving work occurrence order and duplicate IDs exactly', async () => {
    const savedPlan = makePlan({ substrate: 'GYPSUM_PLASTER' });
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(savedPlan);
    renderEditor();

    fireEvent.change(await screen.findByLabelText(`work-plan-substrate-${surfaceId}`), {
      target: { value: 'GYPSUM_PLASTER' },
    });
    const save = screen.getByLabelText(`save-work-plan-${surfaceId}`);
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledWith(projectId, roomId, surfaceId, {
        substrate: 'GYPSUM_PLASTER',
        quality_target: 'S3',
        price_item_ids: ['price-shared', 'price-localized', 'price-shared', 'price-unavailable'],
      });
    });
    expect(await screen.findByText('Plan prac został zapisany.')).toBeInTheDocument();
    expect(save).toBeDisabled();
  });

  it('retains the full draft and preview after a failed save', async () => {
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValue(
      new ApiError('Archived price item cannot be selected for a work plan', 422),
    );
    renderEditor();

    const substrate = await screen.findByLabelText(`work-plan-substrate-${surfaceId}`);
    const quality = screen.getByLabelText(`work-plan-quality-${surfaceId}`);
    fireEvent.change(substrate, { target: { value: 'GYPSUM_BOARD' } });
    fireEvent.change(quality, { target: { value: 'Q3' } });
    fireEvent.click(screen.getByLabelText(`save-work-plan-${surfaceId}`));

    expect(await screen.findByText('Nie udało się zapisać planu prac.')).toBeInTheDocument();
    expect(screen.getByText('Archived price item cannot be selected for a work plan')).toBeInTheDocument();
    expect(substrate).toHaveValue('GYPSUM_BOARD');
    expect(quality).toHaveValue('Q3');
    expect(screen.getAllByText('Pierwsza praca')).toHaveLength(2);
    expect(screen.getByLabelText(`save-work-plan-${surfaceId}`)).toBeEnabled();
  });

  it('ignores a late response after the editor switches to another surface', async () => {
    const nextSurfaceId = '44444444-4444-4444-4444-444444444444';
    let resolveFirst!: (plan: SurfaceWorkPlanRead) => void;
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan)
      .mockReturnValueOnce(new Promise((resolve) => {
        resolveFirst = resolve;
      }))
      .mockResolvedValueOnce(makePlan({
        surface_id: nextSurfaceId,
        substrate: 'GYPSUM_BOARD',
        quality_target: 'Q2',
      }));

    const view = renderEditor();
    view.rerender(
      <I18nProvider>
        <SurfaceWorkPlanEditor
          projectId={projectId}
          roomId={roomId}
          surfaceId={nextSurfaceId}
          surfaceName="Ściana wschodnia"
          onClose={vi.fn()}
        />
      </I18nProvider>,
    );

    const substrate = await screen.findByLabelText(`work-plan-substrate-${nextSurfaceId}`);
    expect(substrate).toHaveValue('GYPSUM_BOARD');
    expect(screen.getByLabelText(`work-plan-quality-${nextSurfaceId}`)).toHaveValue('Q2');

    await act(async () => resolveFirst(makePlan({ substrate: 'CONCRETE', quality_target: 'S1' })));
    expect(substrate).toHaveValue('GYPSUM_BOARD');
    expect(screen.getByLabelText(`work-plan-quality-${nextSurfaceId}`)).toHaveValue('Q2');
  });
});
