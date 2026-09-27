/**
 * Stage 13H.5 — execution-detach confirmation UX (13H.4 409 contract) on
 * every frontend path that can trigger it (ordinary save, workflow REPLACE,
 * apply-to-all), the read-only editor badge, and the typed error parsers.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api/http';
import * as templatesApi from './api/workflowTemplates';
import * as workPlansApi from './api/workPlans';
import { isWorkExecutionConflict, parseExecutionDetachConfirmation } from './api/workPlans';
import { SurfaceWorkPlanEditor } from './components/SurfaceWorkPlanEditor';
import { I18nProvider } from './hooks/useI18n';
import {
  ExecutionDetachAffected,
  PlannedWorkExecutionRead,
  SurfacePlannedWorkRead,
  SurfacePriceItemSummaryRead,
  SurfaceWorkPlanRead,
  SurfaceWorkPlanUpsert,
} from './types/workPlan';
import { ApplyTemplateRequest, WorkflowTemplateRead } from './types/workflowTemplate';
import { localizeApiError } from './utils/apiErrors';
import pl from './locales/pl.json';

vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return { ...actual, fetchSurfaceWorkPlan: vi.fn(), putSurfaceWorkPlan: vi.fn(), applyWorkPlanToRoomWalls: vi.fn(), transitionWorkExecution: vi.fn() };
});
vi.mock('./api/workflowTemplates', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workflowTemplates')>();
  return { ...actual, fetchCompatibleTemplates: vi.fn(), fetchWorkflowTemplate: vi.fn(), applyTemplateToWorkPlan: vi.fn() };
});
vi.mock('./api/priceItems', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/priceItems')>();
  return { ...actual, fetchPriceItems: vi.fn(), createPriceItem: vi.fn() };
});
vi.mock('./api/coefficients', () => ({ fetchCoefficientGroups: vi.fn() }));

const S = 's-1';
const CODE = 'WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED';

function item(id: string, name: string): SurfacePriceItemSummaryRead {
  return { id, code: id.toUpperCase(), name_key: null, display_name: name, category: 'SKIM_COAT', unit: 'M2',
    price_scope: 'LABOR', price: '10.00', currency: 'PLN', is_archived: false, quality_level: null };
}
const GLADZ = item('p1', 'Gładź');
const exec = (status: PlannedWorkExecutionRead['status']): PlannedWorkExecutionRead => ({
  status, started_at: status === 'NOT_STARTED' ? null : '2026-09-27T08:00:00Z',
  completed_at: status === 'COMPLETED' ? '2026-09-27T10:00:00Z' : null, ready_after: null });

function work(key: string, position: number, status: PlannedWorkExecutionRead['status'], priceItem = GLADZ): SurfacePlannedWorkRead {
  return { id: `row-${key}`, work_plan_id: 'plan-1', price_item_id: priceItem.id, position, occurrence_key: key,
    wait_after_hours: null, price_item: priceItem, coefficient_options: [], execution: exec(status) };
}

// A NOT_STARTED, B COMPLETED, C IN_PROGRESS; B and C share the PriceItem (duplicates).
const PLAN: SurfaceWorkPlanRead = {
  id: 'plan-1', surface_id: S, substrate: 'CONCRETE', quality_target: 'S2', template_applications: [],
  planned_works: [work('key-A', 0, 'NOT_STARTED', item('p0', 'Gruntowanie')), work('key-B', 1, 'COMPLETED'), work('key-C', 2, 'IN_PROGRESS')],
};

function affected(key: string, status: ExecutionDetachAffected['status'], position: number, surfaceId = S,
  name: string | null = 'Gładź', nameKey: string | null = null): ExecutionDetachAffected {
  return { surface_id: surfaceId, occurrence_key: key, position, status, price_item_id: 'p1', price_item_code: 'P1',
    price_item_name_key: nameKey, price_item_display_name: name };
}

function detach409(list: ExecutionDetachAffected[]): ApiError {
  return new ApiError('this change would detach…', 409, CODE, { code: CODE, message: 'x', affected: list });
}

function renderEditor(extra: Partial<Parameters<typeof SurfaceWorkPlanEditor>[0]> = {}) {
  return render(
    <I18nProvider>
      <SurfaceWorkPlanEditor projectId="p" roomId="r" surfaceId={S} surfaceName="Ściana A" surfaceType="WALL"
        onClose={vi.fn()} {...extra} />
    </I18nProvider>,
  );
}

const puts = () => vi.mocked(workPlansApi.putSurfaceWorkPlan).mock.calls.map((c) => c[3] as SurfaceWorkPlanUpsert);
const dialog = () => screen.getByLabelText(`execution-detach-dialog-${S}`);

async function removeB() {
  const list = await screen.findByLabelText(`planned-works-${S}`);
  const rows = within(list).getAllByRole('listitem');
  const removeButton = rows[1].querySelector('button[aria-label^="remove-occurrence-"]') as HTMLButtonElement;
  fireEvent.click(removeButton);
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN);
});

describe('editor execution badge (read-only)', () => {
  it('shows each saved occurrence status, no mutation controls, and no status for an unsaved row', async () => {
    const { container } = renderEditor();
    const list = await screen.findByLabelText(`planned-works-${S}`);
    const rows = within(list).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Zaplanowano');
    expect(rows[1]).toHaveTextContent('Wykonano');
    expect(rows[2]).toHaveTextContent('W trakcie');
    expect(container.querySelector('[aria-label^="execution-start-"],[aria-label^="execution-complete-"],[aria-label^="execution-reopen-"],[aria-label^="execution-reset-"]')).toBeNull();

    vi.mocked((await import('./api/priceItems')).fetchPriceItems).mockResolvedValue({
      items: [{ ...GLADZ, id: 'p7', code: 'P7', display_name: 'Nowa praca', archived_at: null, description: null,
        market_reference: null, created_at: '', updated_at: '' } as never], total: 1 });
    fireEvent.click(screen.getByLabelText(`open-picker-${S}`));
    fireEvent.click(await screen.findByLabelText('picker-item-p7'));
    const added = within(list).getAllByRole('listitem')[3];
    expect(added).toHaveTextContent('Nowa praca — status po zapisaniu planu');
    expect(added).not.toHaveTextContent(/Zaplanowano|Wykonano|W trakcie/);

    // the save payload never carries execution state
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(PLAN);
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(JSON.stringify(puts()[0])).not.toMatch(/execution|started_at|completed_at|ready_after|"status"/);
  });
});

describe('ordinary save', () => {
  it('shows the server list, cancel keeps the draft, confirm retries the original payload with exact keys', async () => {
    renderEditor();
    await removeB();
    // another unsaved change that must survive the confirmed retry
    fireEvent.change(screen.getByLabelText(`work-plan-quality-${S}`), { target: { value: 'S3' } });
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValueOnce(detach409([affected('key-B', 'COMPLETED', 1)]));
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));

    const d = await screen.findByLabelText(`execution-detach-dialog-${S}`);
    expect(d).toHaveTextContent('Ten zapis usunie z aktualnego planu prace, które zostały już rozpoczęte lub oznaczone jako wykonane.');
    expect(d).toHaveTextContent('Historia ich realizacji zostanie zachowana');
    expect(d).not.toHaveTextContent(/usunięta|skasowan/);
    expect(within(d).getByLabelText('execution-detach-item-key-B')).toHaveTextContent('2. Gładź');
    expect(within(d).getByLabelText('execution-detach-item-key-B')).toHaveTextContent('Wykonano');

    fireEvent.click(screen.getByLabelText(`execution-detach-cancel-${S}`));
    expect(screen.queryByLabelText(`execution-detach-dialog-${S}`)).toBeNull();
    expect(puts()).toHaveLength(1);  // cancel never retries
    expect(within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem')).toHaveLength(2);  // draft kept
    expect(screen.getByLabelText(`work-plan-quality-${S}`)).toHaveValue('S3');

    vi.mocked(workPlansApi.putSurfaceWorkPlan)
      .mockRejectedValueOnce(detach409([affected('key-B', 'COMPLETED', 1)]))
      .mockResolvedValueOnce({ ...PLAN, quality_target: 'S3', planned_works: [PLAN.planned_works[0], PLAN.planned_works[2]] });
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));
    fireEvent.click(await screen.findByLabelText(`execution-detach-confirm-${S}`));
    await waitFor(() => expect(puts()).toHaveLength(3));
    const [, first, retry] = puts();
    expect(first.confirm_execution_detach_keys).toBeUndefined();
    expect(retry).toEqual({ ...first, confirm_execution_detach_keys: ['key-B'] });  // original draft, exact keys
    expect(retry.quality_target).toBe('S3');
    expect(retry.planned_works?.map((w) => w.occurrence_key)).toEqual(['key-A', 'key-C']);
    await waitFor(() => expect(screen.queryByLabelText(`execution-detach-dialog-${S}`)).toBeNull());
    expect(await screen.findByText(pl.work_plan.saved)).toBeInTheDocument();
  });

  it('a second detach 409 shows the NEW list and requires a fresh confirmation', async () => {
    renderEditor();
    await removeB();
    const row = within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem')[1];
    fireEvent.click(row.querySelector('button[aria-label^="remove-occurrence-"]') as HTMLButtonElement);  // remove C too
    vi.mocked(workPlansApi.putSurfaceWorkPlan)
      .mockRejectedValueOnce(detach409([affected('key-B', 'COMPLETED', 1)]))
      .mockRejectedValueOnce(detach409([affected('key-B', 'COMPLETED', 1), affected('key-C', 'IN_PROGRESS', 2)]))
      .mockResolvedValueOnce({ ...PLAN, planned_works: [PLAN.planned_works[0]] });
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));
    fireEvent.click(await screen.findByLabelText(`execution-detach-confirm-${S}`));
    await screen.findByLabelText(`execution-detach-repeat-${S}`);
    expect(within(dialog()).getByLabelText('execution-detach-item-key-C')).toHaveTextContent('W trakcie');
    expect(puts()).toHaveLength(2);  // not auto-confirmed
    fireEvent.click(screen.getByLabelText(`execution-detach-confirm-${S}`));
    await waitFor(() => expect(puts()).toHaveLength(3));
    expect(puts()[2].confirm_execution_detach_keys).toEqual(['key-B', 'key-C']);
  });

  it('seeded PriceItem names in the affected list are localized; owner names stay verbatim', async () => {
    renderEditor();
    await removeB();
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockRejectedValueOnce(detach409([
      affected('key-B', 'COMPLETED', 1, S, 'Moja gładź „premium” — właściciel'),
      affected('key-C', 'IN_PROGRESS', 2, S, null, 'no.such.key'),
    ]));
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));
    await screen.findByLabelText(`execution-detach-dialog-${S}`);
    expect(screen.getByLabelText('execution-detach-item-key-B')).toHaveTextContent('Moja gładź „premium” — właściciel');
    expect(screen.getByLabelText('execution-detach-item-key-C')).toHaveTextContent('P1');  // code fallback
  });
});

describe('apply to all walls', () => {
  it('one confirmation lists every target wall and retries with the exact flat key set', async () => {
    renderEditor({ isWall: true, otherActiveWallCount: 2, surfaceNames: { [S]: 'Ściana A', 'wall-b': 'Ściana B', 'wall-c': 'Ściana C' } });
    await screen.findByLabelText(`planned-works-${S}`);
    const list = [affected('kb-1', 'COMPLETED', 0, 'wall-b'), affected('kc-2', 'IN_PROGRESS', 1, 'wall-c')];
    vi.mocked(workPlansApi.applyWorkPlanToRoomWalls)
      .mockRejectedValueOnce(detach409(list))
      .mockResolvedValueOnce({ source_surface_id: S, target_count: 2, target_surface_ids: ['wall-b', 'wall-c'], targets: [] });
    fireEvent.click(screen.getByLabelText(`apply-to-all-walls-${S}`));
    fireEvent.click(screen.getByLabelText(`apply-confirm-yes-${S}`));

    const d = await screen.findByLabelText(`execution-detach-dialog-${S}`);
    expect(within(d).getByLabelText('execution-detach-item-kb-1')).toHaveTextContent('Ściana B');
    expect(within(d).getByLabelText('execution-detach-item-kc-2')).toHaveTextContent('Ściana C');
    expect(within(d).getByLabelText('execution-detach-item-kc-2')).toHaveTextContent('W trakcie');
    // the source wall's own works are not presented as copied/affected
    expect(within(d).queryByText('Ściana A')).toBeNull();

    fireEvent.click(screen.getByLabelText(`execution-detach-confirm-${S}`));
    await waitFor(() => expect(workPlansApi.applyWorkPlanToRoomWalls).toHaveBeenCalledTimes(2));
    expect(vi.mocked(workPlansApi.applyWorkPlanToRoomWalls).mock.calls[0]).toEqual(['p', 'r', S]);
    expect(vi.mocked(workPlansApi.applyWorkPlanToRoomWalls).mock.calls[1]).toEqual(['p', 'r', S, ['kb-1', 'kc-2']]);
    expect(await screen.findByText('Plan prac skopiowano na 2 ścian(y).')).toBeInTheDocument();
  });

  it('cancel does not retry and an unknown surface falls back to a neutral label', async () => {
    renderEditor({ isWall: true, otherActiveWallCount: 1 });
    await screen.findByLabelText(`planned-works-${S}`);
    vi.mocked(workPlansApi.applyWorkPlanToRoomWalls).mockRejectedValueOnce(detach409([affected('kx', 'COMPLETED', 0, 'wall-x')]));
    fireEvent.click(screen.getByLabelText(`apply-to-all-walls-${S}`));
    fireEvent.click(screen.getByLabelText(`apply-confirm-yes-${S}`));
    expect(await screen.findByLabelText('execution-detach-item-kx')).toHaveTextContent('Inna powierzchnia');
    fireEvent.click(screen.getByLabelText(`execution-detach-cancel-${S}`));
    expect(workPlansApi.applyWorkPlanToRoomWalls).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText(`apply-to-all-walls-${S}`)).toBeInTheDocument();
  });
});

describe('workflow template apply', () => {
  const TEMPLATE: WorkflowTemplateRead = {
    id: 'tpl-1', code: 'CUSTOM', name_key: null, display_name: 'Mój proces', description: null,
    applies_to_substrates: ['CONCRETE'], applies_to_quality: ['S2'], applies_to_surface_types: ['WALL'],
    position: 0, is_archived: false, created_at: '', updated_at: '',
    steps: [{ id: 'st-1', position: 0, price_item_id: 'p5', is_optional: false, note: null, wait_after_hours: null, price_item: item('p5', 'Szlifowanie') }],
  };
  const applyCalls = () => vi.mocked(templatesApi.applyTemplateToWorkPlan).mock.calls.map((c) => c[3] as ApplyTemplateRequest);

  async function openPreview() {
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [TEMPLATE], total: 1 });
    renderEditor();
    fireEvent.click(await screen.findByLabelText(`open-template-sheet-${S}`));
    const sheet = await screen.findByLabelText(`template-sheet-${S}`);
    fireEvent.click(await within(sheet).findByLabelText('template-option-tpl-1'));
    return sheet;
  }

  it('APPEND never asks for execution confirmation', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(PLAN);
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(applyCalls()).toHaveLength(1));
    expect(applyCalls()[0].mode).toBe('APPEND');
    expect(applyCalls()[0]).not.toHaveProperty('confirm_execution_detach_keys');
    expect(screen.queryByLabelText(`execution-detach-dialog-template-${S}`)).toBeNull();
  });

  it('REPLACE: dialog, confirmed retry with the SAME application_id and exact keys; a second conflict asks again', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan)
      .mockRejectedValueOnce(detach409([affected('key-B', 'COMPLETED', 1)]))
      .mockRejectedValueOnce(detach409([affected('key-B', 'COMPLETED', 1), affected('key-C', 'IN_PROGRESS', 2)]))
      .mockResolvedValueOnce({ ...PLAN, planned_works: [work('key-N', 0, 'NOT_STARTED', item('p0', 'Gruntowanie'))] });
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByLabelText(`template-replace-confirm-yes-${S}`));

    const d = await screen.findByLabelText(`execution-detach-dialog-template-${S}`);
    expect(within(d).getByLabelText('execution-detach-item-key-B')).toHaveTextContent('Gładź');
    fireEvent.click(screen.getByLabelText(`execution-detach-confirm-template-${S}`));
    await screen.findByLabelText(`execution-detach-repeat-template-${S}`);
    expect(applyCalls()).toHaveLength(2);
    fireEvent.click(screen.getByLabelText(`execution-detach-confirm-template-${S}`));
    await waitFor(() => expect(applyCalls()).toHaveLength(3));

    const [first, second, third] = applyCalls();
    expect(first.confirm_execution_detach_keys).toBeUndefined();
    expect(second.confirm_execution_detach_keys).toEqual(['key-B']);
    expect(third.confirm_execution_detach_keys).toEqual(['key-B', 'key-C']);
    expect(new Set([first.application_id, second.application_id, third.application_id]).size).toBe(1);
    const { confirm_execution_detach_keys: _a, ...firstRest } = first;
    const { confirm_execution_detach_keys: _b, ...thirdRest } = third;
    expect(thirdRest).toEqual(firstRest);  // same logical request
    await waitFor(() => expect(screen.queryByLabelText(`template-sheet-${S}`)).toBeNull());
  });

  it('REPLACE cancel does not retry and a later Apply is not silently confirmed', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockRejectedValue(detach409([affected('key-B', 'COMPLETED', 1)]));
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByLabelText(`template-replace-confirm-yes-${S}`));
    fireEvent.click(await screen.findByLabelText(`execution-detach-cancel-template-${S}`));
    expect(applyCalls()).toHaveLength(1);
    expect(screen.getByLabelText(`template-sheet-${S}`)).toBeInTheDocument();
  });
});

describe('typed error parsing', () => {
  it('distinguishes detach, execution conflict, other 409, 422 and unknown errors', () => {
    const detach = detach409([affected('key-B', 'COMPLETED', 1)]);
    expect(parseExecutionDetachConfirmation(detach)?.map((a) => a.occurrence_key)).toEqual(['key-B']);
    expect(isWorkExecutionConflict(detach)).toBe(false);
    // empty affected list is still a detach conflict (nothing left to confirm)
    expect(parseExecutionDetachConfirmation(detach409([]))).toEqual([]);

    const conflict = new ApiError('m', 409, 'WORK_EXECUTION_CONFLICT', { code: 'WORK_EXECUTION_CONFLICT', current_status: 'COMPLETED' });
    expect(isWorkExecutionConflict(conflict)).toBe(true);
    expect(parseExecutionDetachConfirmation(conflict)).toBeNull();

    // a message that merely mentions the code is not parsed as the contract
    const textOnly = new ApiError('WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED', 409);
    expect(parseExecutionDetachConfirmation(textOnly)).toBeNull();
    const stale = new ApiError('occurrence_key x is not a current occurrence of this work plan; reload', 409);
    expect(parseExecutionDetachConfirmation(stale)).toBeNull();
    expect(workPlansApi.isStaleWorkPlanError(stale)).toBe(true);

    const validation = new ApiError('planned_works.0.wait_after_hours: Input should be greater than or equal to 1', 422);
    expect(parseExecutionDetachConfirmation(validation)).toBeNull();
    expect(localizeApiError(validation, pl)).toBe(pl.errors.validation_greater_than_equal);

    expect(parseExecutionDetachConfirmation(new Error('network'))).toBeNull();
    expect(isWorkExecutionConflict(new Error('network'))).toBe(false);
  });

  it('the http layer keeps a structured detail and its code', async () => {
    const { apiRequest } = await import('./api/http');
    const body = { detail: { code: CODE, message: 'this change would detach 1', affected: [affected('key-B', 'COMPLETED', 1)] } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => body }));
    try {
      await apiRequest('/x');
      throw new Error('expected rejection');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe(CODE);
      expect((error as ApiError).message).toBe('this change would detach 1');
      expect(parseExecutionDetachConfirmation(error)?.[0].occurrence_key).toBe('key-B');
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
