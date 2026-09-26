/**
 * Stage 13E.4 — technological workflow picker / preview / apply UX,
 * exercised through SurfaceWorkPlanEditor.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as workPlansApi from './api/workPlans';
import * as templatesApi from './api/workflowTemplates';
import { ApiError } from './api/http';
import { SurfaceWorkPlanEditor } from './components/SurfaceWorkPlanEditor';
import { I18nProvider } from './hooks/useI18n';
import { SurfacePlannedWorkRead, SurfacePriceItemSummaryRead, SurfaceWorkPlanRead } from './types/workPlan';
import { ApplyTemplateRequest, WorkflowTemplateRead, WorkflowTemplateStepRead } from './types/workflowTemplate';

vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return { ...actual, fetchSurfaceWorkPlan: vi.fn(), putSurfaceWorkPlan: vi.fn(), applyWorkPlanToRoomWalls: vi.fn() };
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

function item(id: string, name: string, archived = false): SurfacePriceItemSummaryRead {
  return {
    id, code: id.toUpperCase(), name_key: null, display_name: name, category: 'SKIM_COAT', unit: 'M2',
    price_scope: 'LABOR', price: '10.00', currency: 'PLN', is_archived: archived, quality_level: null,
  };
}

const P1 = item('p1', 'Gruntowanie');
const P2 = item('p2', 'Szpachlowanie lokalne');

function work(id: string, key: string | null, position: number, coefficients = 0): SurfacePlannedWorkRead {
  return {
    id, work_plan_id: 'plan-1', price_item_id: 'p1', position, occurrence_key: key as string,
    wait_after_hours: null, price_item: P1,
    coefficient_options: Array.from({ length: coefficients }, (_, i) => ({
      id: `opt-${i}`, group_id: `g-${i}`, group_code: 'G', code: 'O', display_name: 'o', percentage: '10.00', is_base: false,
    })),
  };
}

function plan(works: SurfacePlannedWorkRead[] = [work('w-a', 'key-A', 0, 1), work('w-b', 'key-B', 1)],
  overrides: Partial<SurfaceWorkPlanRead> = {}): SurfaceWorkPlanRead {
  return { id: 'plan-1', surface_id: S, substrate: 'CONCRETE', quality_target: 'S2', planned_works: works, template_applications: [], ...overrides };
}

function step(id: string, position: number, optional: boolean, priceItem = P1, wait: number | null = null): WorkflowTemplateStepRead {
  return { id, position, price_item_id: priceItem.id, is_optional: optional, note: null, wait_after_hours: wait, price_item: priceItem };
}

function template(overrides: Partial<WorkflowTemplateRead> = {}): WorkflowTemplateRead {
  return {
    id: 'tpl-builtin', code: 'TECH_BETON_S2-01', name_key: 'workflow_templates.seed.tech_beton_s2', display_name: null,
    description: 'Opis', applies_to_substrates: ['CONCRETE'], applies_to_quality: ['S2'], applies_to_surface_types: ['WALL'],
    position: 0, is_archived: false, created_at: '', updated_at: '',
    steps: [step('st-1', 0, false, P1, 24), step('st-2', 1, true, P2), step('st-3', 2, false, P1)],
    ...overrides,
  };
}

const CUSTOM = template({ id: 'tpl-custom', code: 'CUSTOM_X', name_key: null, display_name: 'Mój proces', steps: [step('c-1', 0, false)] });
const fetchSpy = vi.fn();

function renderEditor() {
  return render(
    <I18nProvider>
      <SurfaceWorkPlanEditor projectId="p" roomId="r" surfaceId={S} surfaceName="Ściana" surfaceType="WALL" onClose={vi.fn()} />
    </I18nProvider>,
  );
}

async function openSheet() {
  renderEditor();
  const open = await screen.findByLabelText(`open-template-sheet-${S}`);
  fireEvent.click(open);
  return screen.findByLabelText(`template-sheet-${S}`);
}

async function openPreview(id = 'tpl-builtin') {
  const sheet = await openSheet();
  fireEvent.click(await within(sheet).findByLabelText(`template-option-${id}`));
  return sheet;
}

function applyCalls(): ApplyTemplateRequest[] {
  return vi.mocked(templatesApi.applyTemplateToWorkPlan).mock.calls.map((c) => c[3]);
}

const APPLIED = plan([work('w-a', 'key-A', 0, 1), work('w-b', 'key-B', 1), work('n-1', 'key-N1', 2), work('n-2', 'key-N2', 3)]);

describe('Workflow template apply (13E.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.stubGlobal('fetch', fetchSpy);
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan());
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [template(), CUSTOM], total: 2 });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // ---- entry / list / preview ---------------------------------------------

  it('offers the entry action and blocks it while the editor has unsaved changes', async () => {
    renderEditor();
    const open = await screen.findByLabelText(`open-template-sheet-${S}`);
    expect(open).toBeEnabled();
    expect(open).toHaveTextContent('Zastosuj proces technologiczny');
    fireEvent.click(within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem')[0].querySelector('button')!);
    fireEvent.change(screen.getByLabelText(`work-plan-quality-${S}`), { target: { value: 'S3' } });
    expect(open).toBeDisabled();
    expect(screen.getByLabelText(`template-unsaved-${S}`)).toHaveTextContent('Najpierw zapisz lub odrzuć niezapisane zmiany planu prac.');
  });

  it('requires a saved quality target and never lists templates without it', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan(undefined, { quality_target: null }));
    renderEditor();
    expect(await screen.findByLabelText(`open-template-sheet-${S}`)).toBeDisabled();
    expect(screen.getByLabelText(`template-need-quality-${S}`)).toHaveTextContent('Najpierw wybierz docelowy standard wykończenia.');
    expect(templatesApi.fetchCompatibleTemplates).not.toHaveBeenCalled();
  });

  it('lists server-filtered templates with localized built-in and stored custom names', async () => {
    const sheet = await openSheet();
    expect(templatesApi.fetchCompatibleTemplates).toHaveBeenCalledWith({ substrate: 'CONCRETE', quality_target: 'S2', surface_type: 'WALL' });
    const builtin = await within(sheet).findByLabelText('template-option-tpl-builtin');
    expect(builtin).toHaveTextContent('Beton — S2 — standard malarski');
    expect(builtin).toHaveTextContent('Kroki: 3');
    expect(builtin).toHaveTextContent('w tym opcjonalne: 1');
    expect(builtin).not.toHaveTextContent('TECH_BETON');
    expect(within(sheet).getByLabelText('template-option-tpl-custom')).toHaveTextContent('Mój proces');
  });

  it('shows the empty state', async () => {
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [], total: 0 });
    const sheet = await openSheet();
    expect(await within(sheet).findByLabelText(`template-empty-${S}`)).toHaveTextContent('Brak pasujących procesów technologicznych.');
  });

  it('previews ordered steps: required locked, optional OFF, waits only when set', async () => {
    const sheet = await openPreview();
    const rows = within(within(sheet).getByLabelText(`template-steps-${S}`)).getAllByRole('listitem');
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining('1.Gruntowanie'), expect.stringContaining('2.Szpachlowanie lokalne'), expect.stringContaining('3.Gruntowanie'),
    ]);
    expect(rows[0]).toHaveTextContent('Wymagany');
    expect(rows[0]).toHaveTextContent('Przerwa technologiczna: 24 h');
    expect(rows[0].querySelector('input')).toBeNull();
    expect(rows[1]).toHaveTextContent('Opcjonalny');
    expect(within(rows[1]).getByLabelText('template-optional-st-2')).not.toBeChecked();
    expect(rows[2]).not.toHaveTextContent('Przerwa');
  });

  it('switching templates resets optional selections', async () => {
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    expect(within(sheet).getByLabelText('template-optional-st-2')).toBeChecked();
    fireEvent.click(within(sheet).getByText('Wróć do listy'));
    fireEvent.click(await within(sheet).findByLabelText('template-option-tpl-builtin'));
    expect(within(sheet).getByLabelText('template-optional-st-2')).not.toBeChecked();
  });

  it('blocks a template whose required step item is archived and disables archived optional steps', async () => {
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [template({
      steps: [step('st-1', 0, false, item('p9', 'Stara pozycja', true)), step('st-2', 1, true, item('p8', 'Opcja stara', true))],
    })], total: 1 });
    const sheet = await openPreview();
    expect(within(sheet).getByLabelText(`template-apply-${S}`)).toBeDisabled();
    expect(within(sheet).getByLabelText('template-optional-st-2')).toBeDisabled();
    expect(sheet).toHaveTextContent('Przywróć ją w Cenniku');
  });

  // ---- APPEND ---------------------------------------------------------------

  it('APPEND (default) sends only identifiers and choices, re-hydrates, closes, and does nothing else', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(APPLIED);
    const sheet = await openPreview();
    expect(within(sheet).getByLabelText('template-mode-APPEND')).toBeChecked();
    expect(sheet).toHaveTextContent('Obecne prace pozostaną bez zmian. Kroki procesu zostaną dodane na końcu.');
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    await waitFor(() => expect(screen.queryByLabelText(`template-sheet-${S}`)).not.toBeInTheDocument());
    const [req] = applyCalls();
    expect(req.application_id).toMatch(/^[0-9a-f-]{36}$/);
    expect({ ...req, application_id: 'x' }).toEqual({
      application_id: 'x', template_id: 'tpl-builtin', mode: 'APPEND',
      selected_optional_step_ids: ['st-2'], expected_step_ids: ['st-1', 'st-2', 'st-3'],
    });
    expect(within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem')).toHaveLength(4);
    expect(screen.getByText('Proces technologiczny zastosowany.')).toBeInTheDocument();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled(); // no Estimate or other network call
    expect(screen.getByLabelText(`save-work-plan-${S}`)).toBeDisabled(); // re-hydrated, clean
  });

  it('blocks double submit', async () => {
    let resolve: (p: SurfaceWorkPlanRead) => void = () => {};
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockReturnValue(new Promise((r) => { resolve = r; }));
    const sheet = await openPreview();
    const apply = within(sheet).getByLabelText(`template-apply-${S}`);
    fireEvent.click(apply);
    fireEvent.click(apply);
    expect(apply).toBeDisabled();
    await act(async () => resolve(APPLIED));
    expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(1);
  });

  // ---- REPLACE --------------------------------------------------------------

  it('REPLACE shows the impact, needs a second confirmation, and sends the exact ordered keys', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(plan([work('n-1', 'key-N1', 0)]));
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    const impact = within(sheet).getByLabelText(`template-replace-impact-${S}`);
    expect(impact).toHaveTextContent('• 2 obecnych prac');
    expect(impact).toHaveTextContent('• 1 przypisania współczynników');
    expect(impact).toHaveTextContent('Kosztorys nie zostanie zmieniony automatycznie.');
    expect(templatesApi.applyTemplateToWorkPlan).not.toHaveBeenCalled();

    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    const confirm = within(sheet).getByLabelText(`template-replace-confirm-${S}`);
    expect(confirm).toHaveTextContent('Zastąpić obecne prace?');
    fireEvent.click(within(confirm).getByText('Anuluj'));
    expect(templatesApi.applyTemplateToWorkPlan).not.toHaveBeenCalled();

    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByLabelText(`template-replace-confirm-yes-${S}`));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(1));
    expect(applyCalls()[0]).toMatchObject({ mode: 'REPLACE', replace_confirmed: true, expected_occurrence_keys: ['key-A', 'key-B'] });
    await waitFor(() => expect(within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem')).toHaveLength(1));
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('a current row without an occurrence key blocks REPLACE', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan([work('w-a', null, 0)]));
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    expect(within(sheet).getByLabelText(`template-apply-${S}`)).toBeDisabled();
    expect(sheet).toHaveTextContent('Plan prac wymaga odświeżenia przed zastąpieniem prac.');
  });

  // ---- retry / errors -------------------------------------------------------

  it('a transport failure keeps the application_id for the exact retry', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(APPLIED);
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(await within(sheet).findByLabelText(`template-apply-error-${S}`)).toHaveTextContent('ta sama operacja nie zostanie zastosowana dwukrotnie');
    fireEvent.click(within(sheet).getByText('Spróbuj ponownie'));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(2));
    const [first, second] = applyCalls();
    expect(second).toEqual(first);
  });

  it('changing optional selection, mode or template makes a new command id', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockRejectedValue(new TypeError('Failed to fetch'));
    const sheet = await openPreview();
    const apply = () => fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    apply();
    await within(sheet).findByLabelText(`template-apply-error-${S}`);
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    apply();
    await waitFor(() => expect(applyCalls()).toHaveLength(2));
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByLabelText(`template-replace-confirm-yes-${S}`));
    await waitFor(() => expect(applyCalls()).toHaveLength(3));
    fireEvent.click(within(sheet).getByText('Wróć do listy'));
    fireEvent.click(await within(sheet).findByLabelText('template-option-tpl-custom'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    await waitFor(() => expect(applyCalls()).toHaveLength(4));
    const ids = applyCalls().map((r) => r.application_id);
    expect(new Set(ids).size).toBe(4);
  });

  it('stale template 409: refresh reloads steps, resets optionals and uses a new command', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan)
      .mockRejectedValueOnce(new ApiError('the workflow template changed since it was previewed; refresh the preview', 409))
      .mockResolvedValueOnce(APPLIED);
    vi.mocked(templatesApi.fetchWorkflowTemplate).mockResolvedValue(template({ steps: [step('new-1', 0, false), step('new-2', 1, true, P2)] }));
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(await within(sheet).findByLabelText(`template-apply-error-${S}`)).toHaveTextContent('Proces technologiczny zmienił się od czasu podglądu.');
    fireEvent.click(within(sheet).getByLabelText(`template-refresh-${S}`));
    await waitFor(() => expect(templatesApi.fetchWorkflowTemplate).toHaveBeenCalledWith('tpl-builtin'));
    expect(await within(sheet).findByLabelText('template-optional-new-2')).not.toBeChecked();
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    await waitFor(() => expect(applyCalls()).toHaveLength(2));
    const [first, second] = applyCalls();
    expect(second.expected_step_ids).toEqual(['new-1', 'new-2']);
    expect(second.selected_optional_step_ids).toEqual([]);
    expect(second.application_id).not.toBe(first.application_id);
  });

  it('stale plan 409 on REPLACE: reload plan, never falls back or resends', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockRejectedValue(
      new ApiError('the work plan changed since it was confirmed for replacement; reload it', 409),
    );
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByLabelText(`template-replace-confirm-yes-${S}`));
    expect(await within(sheet).findByLabelText(`template-apply-error-${S}`)).toHaveTextContent(
      'Plan prac zmienił się od czasu otwarcia. Odśwież plan przed zastąpieniem prac.',
    );
    expect(within(sheet).queryByLabelText(`template-replace-confirm-${S}`)).not.toBeInTheDocument();
    fireEvent.click(within(sheet).getByLabelText(`template-reload-plan-${S}`));
    await waitFor(() => expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(2));
    expect(screen.queryByLabelText(`template-sheet-${S}`)).not.toBeInTheDocument();
    expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(1);
    expect(applyCalls()[0].mode).toBe('REPLACE');
  });

  it('archived template 409 reloads the list', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockRejectedValue(
      new ApiError('the workflow template is archived; restore it before applying', 409),
    );
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(await within(sheet).findByLabelText(`template-apply-error-${S}`)).toHaveTextContent('Wybrany proces technologiczny nie jest już dostępny.');
    await waitFor(() => expect(templatesApi.fetchCompatibleTemplates).toHaveBeenCalledTimes(2));
    expect(await within(sheet).findByLabelText(`template-list-${S}`)).toBeInTheDocument();
  });

  it('unknown 409 and 422 show a generic error with the server detail', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan)
      .mockRejectedValueOnce(new ApiError('something else conflicted', 409))
      .mockRejectedValueOnce(new ApiError('no steps selected: at least one work must be applied', 422));
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    const err = await within(sheet).findByLabelText(`template-apply-error-${S}`);
    expect(err).toHaveTextContent('Nie udało się zastosować procesu technologicznego.');
    expect(err).toHaveTextContent('something else conflicted');
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    await waitFor(() => expect(within(sheet).getByLabelText(`template-apply-error-${S}`)).toHaveTextContent('at least one work'));
  });

  it('renders the flow in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    const sheet = await openPreview();
    expect(screen.getByLabelText(`open-template-sheet-${S}`)).toHaveTextContent('Применить технологический процесс');
    expect(sheet).toHaveTextContent('Обязательный');
    expect(sheet).toHaveTextContent('Технологический перерыв: 24 ч');
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    expect(sheet).toHaveTextContent('Смета не будет изменена автоматически.');
  });
});
