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
// Neutral item for the default plan: not used by any template fixture.
const PX = item('px', 'Naprawa rys i pęknięć');

function work(id: string, key: string | null, position: number, coefficients = 0, priceItem = PX): SurfacePlannedWorkRead {
  return {
    id, work_plan_id: 'plan-1', price_item_id: priceItem.id, position, occurrence_key: key as string,
    wait_after_hours: null, price_item: priceItem,
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

/** APPEND: Zastosuj opens the final review; nothing is sent until "Dodaj wybrane". */
function applyAppend(sheet: HTMLElement) {
  fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
  fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
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
    expect(templatesApi.applyTemplateToWorkPlan).not.toHaveBeenCalled(); // review first
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(screen.queryByLabelText(`template-sheet-${S}`)).not.toBeInTheDocument());
    const [req] = applyCalls();
    expect(req.application_id).toMatch(/^[0-9a-f-]{36}$/);
    expect({ ...req, application_id: 'x' }).toEqual({
      application_id: 'x', template_id: 'tpl-builtin', mode: 'APPEND', selected_optional_step_ids: [],
      selected_step_ids: ['st-1', 'st-2', 'st-3'], expected_step_ids: ['st-1', 'st-2', 'st-3'],
    });
    expect(within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem')).toHaveLength(4);
    expect(screen.getByLabelText(`template-applied-${S}`)).toHaveTextContent('Proces technologiczny zastosowany i zapisany.');
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled(); // no Estimate or other network call
    expect(screen.getByLabelText(`save-work-plan-${S}`)).toBeDisabled(); // re-hydrated, clean
  });

  it('blocks double submit', async () => {
    let resolve: (p: SurfaceWorkPlanRead) => void = () => {};
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockReturnValue(new Promise((r) => { resolve = r; }));
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    const confirm = within(sheet).getByLabelText(`template-review-confirm-${S}`);
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(confirm).toBeDisabled();
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
    // REPLACE keeps the 13E.3 contract: no APPEND review, no reviewed selection.
    expect(applyCalls()[0]).not.toHaveProperty('selected_step_ids');
    expect(within(sheet).queryByLabelText(`template-review-${S}`)).not.toBeInTheDocument();
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
    applyAppend(sheet);
    expect(await within(sheet).findByLabelText(`template-apply-error-${S}`)).toHaveTextContent('ta sama operacja nie zostanie zastosowana dwukrotnie');
    fireEvent.click(within(sheet).getByText('Spróbuj ponownie'));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(2));
    const [first, second] = applyCalls();
    expect(second).toEqual(first);
  });

  it('changing optional selection, mode or template makes a new command id', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockRejectedValue(new TypeError('Failed to fetch'));
    const sheet = await openPreview();
    applyAppend(sheet);
    await within(sheet).findByLabelText(`template-apply-error-${S}`);
    fireEvent.click(within(sheet).getByText('Wróć'));
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    applyAppend(sheet);
    await waitFor(() => expect(applyCalls()).toHaveLength(2));
    // Unchecking a candidate in the review is also a new command.
    fireEvent.click(within(sheet).getByText('Wróć'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByLabelText('template-review-toggle-st-3'));
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(applyCalls()).toHaveLength(3));
    expect(applyCalls()[2].selected_step_ids).toEqual(['st-1', 'st-2']);
    fireEvent.click(within(sheet).getByText('Wróć'));
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByLabelText(`template-replace-confirm-yes-${S}`));
    await waitFor(() => expect(applyCalls()).toHaveLength(4));
    fireEvent.click(within(sheet).getByText('Wróć do listy'));
    fireEvent.click(await within(sheet).findByLabelText('template-option-tpl-custom'));
    applyAppend(sheet);
    await waitFor(() => expect(applyCalls()).toHaveLength(5));
    const ids = applyCalls().map((r) => r.application_id);
    expect(new Set(ids).size).toBe(5);
  });

  it('stale template 409: refresh reloads steps, resets optionals and uses a new command', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan)
      .mockRejectedValueOnce(new ApiError('the workflow template changed since it was previewed; refresh the preview', 409))
      .mockResolvedValueOnce(APPLIED);
    vi.mocked(templatesApi.fetchWorkflowTemplate).mockResolvedValue(template({ steps: [step('new-1', 0, false), step('new-2', 1, true, P2)] }));
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    applyAppend(sheet);
    expect(await within(sheet).findByLabelText(`template-apply-error-${S}`)).toHaveTextContent('Proces technologiczny zmienił się od czasu podglądu.');
    fireEvent.click(within(sheet).getByLabelText(`template-refresh-${S}`));
    await waitFor(() => expect(templatesApi.fetchWorkflowTemplate).toHaveBeenCalledWith('tpl-builtin'));
    expect(await within(sheet).findByLabelText('template-optional-new-2')).not.toBeChecked();
    applyAppend(sheet);
    await waitFor(() => expect(applyCalls()).toHaveLength(2));
    const [first, second] = applyCalls();
    expect(second.expected_step_ids).toEqual(['new-1', 'new-2']);
    expect(second.selected_step_ids).toEqual(['new-1']);
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
    applyAppend(sheet);
    expect(await within(sheet).findByLabelText(`template-apply-error-${S}`)).toHaveTextContent('Wybrany proces technologiczny nie jest już dostępny.');
    await waitFor(() => expect(templatesApi.fetchCompatibleTemplates).toHaveBeenCalledTimes(2));
    expect(await within(sheet).findByLabelText(`template-list-${S}`)).toBeInTheDocument();
  });

  it('unknown 409 and 422 show a generic error with the server detail', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan)
      .mockRejectedValueOnce(new ApiError('something else conflicted', 409))
      .mockRejectedValueOnce(new ApiError('no steps selected: at least one work must be applied', 422));
    const sheet = await openPreview();
    applyAppend(sheet);
    const err = await within(sheet).findByLabelText(`template-apply-error-${S}`);
    expect(err).toHaveTextContent('Nie udało się zastosować procesu technologicznego.');
    expect(err).toHaveTextContent('something else conflicted');
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
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

  // ---- 13E.5B walkthrough: materialization summary + APPEND history semantics -

  const prior = (templateId = 'tpl-builtin') => ({
    id: 'app-1', template_id: templateId, template_code: 'TECH_BETON_S2-01',
    template_name: 'workflow_templates.seed.tech_beton_s2', mode: 'APPEND' as const, steps_applied: 2, applied_at: '',
  });

  it('summarizes exactly what will be materialized (required + selected optional only)', async () => {
    const sheet = await openPreview();
    const summary = within(sheet).getByLabelText(`template-summary-${S}`);
    // Visible before the FIRST apply (no provenance), next to the Apply action.
    expect(summary).toHaveTextContent('Zostaną dodane 2 prace');
    expect(summary).toHaveTextContent('2 wymagane + 0 wybranych opcjonalnych');
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    expect(summary).toHaveTextContent('Zostaną dodane 3 prace');
    expect(summary).toHaveTextContent('2 wymagane + 1 wybrana opcjonalna');
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    expect(summary).toHaveTextContent('Zostaną dodane 2 prace');
    expect(templatesApi.applyTemplateToWorkPlan).not.toHaveBeenCalled();
  });

  it('matches the owner walkthrough: 3 required + 1 selected optional = 4 works', async () => {
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [template({
      steps: [step('o-1', 0, true, P2), step('r-1', 1, false), step('r-2', 2, false), step('r-3', 3, false), step('o-2', 4, true, P2)],
    })], total: 1 });
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-optional-o-1'));
    const summary = within(sheet).getByLabelText(`template-summary-${S}`);
    expect(summary).toHaveTextContent('Zostaną dodane 4 prace');
    expect(summary).toHaveTextContent('3 wymagane + 1 wybrana opcjonalna');
  });

  it('omits the optional part for a template without optional steps and uses the singular form', async () => {
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [template({ steps: [step('r-1', 0, false)] })], total: 1 });
    const sheet = await openPreview();
    const summary = within(sheet).getByLabelText(`template-summary-${S}`);
    expect(summary).toHaveTextContent('Zostanie dodana 1 praca');
    expect(summary).toHaveTextContent('1 wymagana');
    expect(summary).not.toHaveTextContent('opcjonal');
  });

  it('REPLACE summary states the resulting plan size and that current works are replaced', async () => {
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    const summary = within(sheet).getByLabelText(`template-summary-${S}`);
    expect(summary).toHaveTextContent('Nowy plan prac będzie zawierał 2 prace');
    expect(summary).toHaveTextContent('Obecne prace (2) zostaną zastąpione.');
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(within(sheet).getByLabelText(`template-replace-confirm-${S}`)).toBeInTheDocument();
    expect(templatesApi.applyTemplateToWorkPlan).not.toHaveBeenCalled();
  });

  it('uses the many-form for five works and the Russian wording', async () => {
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [template({
      steps: [0, 1, 2, 3, 4].map((i) => step(`m-${i}`, i, false)),
    })], total: 1 });
    const sheet = await openPreview();
    const summary = within(sheet).getByLabelText(`template-summary-${S}`);
    expect(summary).toHaveTextContent('Zostanie dodanych 5 prac');
    expect(summary).toHaveTextContent('5 wymaganych');
  });

  it('shows the Russian summary', async () => {
    localStorage.setItem('locale', 'ru');
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    const summary = within(sheet).getByLabelText(`template-summary-${S}`);
    expect(summary).toHaveTextContent('Будут добавлены 3 работы');
    expect(summary).toHaveTextContent('2 обязательные + 1 выбранная дополнительная');
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    expect(summary).toHaveTextContent('Новый план работ будет содержать 3 работы');
    expect(summary).toHaveTextContent('Текущие работы (2) будут заменены.');
  });

  // 13E.5B-FIX.3: template_applications is history only. Occurrences carry no
  // relation to the application that created them, so history must never be
  // presented as "this process is currently in the plan".

  const expectNoRepeatClaim = (sheet: HTMLElement) => {
    expect(within(sheet).queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(sheet).not.toHaveTextContent('był już zastosowany');
    expect(sheet).not.toHaveTextContent('Zastosuj ponownie');
  };

  it('scenario 1: history remains but its works were removed -> normal APPEND summary and action', async () => {
    // Owner walkthrough: only an unrelated work left, history still lists the template.
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(
      plan([work('w-crack', 'key-crack', 0)], { template_applications: [prior()] }),
    );
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(APPLIED);
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    expect(within(sheet).getByLabelText(`template-summary-${S}`)).toHaveTextContent('Zostaną dodane 3 prace');
    const apply = within(sheet).getByLabelText(`template-apply-${S}`);
    expect(apply).toHaveTextContent('Zastosuj');
    fireEvent.click(apply);
    expectNoRepeatClaim(sheet);
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(1));
    expect(applyCalls()[0]).toMatchObject({ mode: 'APPEND', selected_step_ids: ['st-1', 'st-2', 'st-3'] });
  });

  it('scenario 1 (RU): no "already applied" claim from history', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(
      plan([work('w-crack', 'key-crack', 0)], { template_applications: [prior()] }),
    );
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(APPLIED);
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(within(sheet).queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(sheet).not.toHaveTextContent('уже применялся');
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(1));
  });

  it('scenario 2: first APPEND (no history) shows the count, then the review, and applies on confirm', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(APPLIED);
    const sheet = await openPreview();
    expect(within(sheet).getByLabelText(`template-summary-${S}`)).toHaveTextContent('Zostaną dodane 2 prace');
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expectNoRepeatClaim(sheet);
    expect(within(sheet).getByLabelText(`template-review-summary-${S}`)).toHaveTextContent('Zostaną dodane 2 prace');
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(1));
  });

  it('scenario 3: a deliberate second APPEND is a normal command with a NEW application_id', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan)
      .mockResolvedValueOnce({ ...APPLIED, template_applications: [prior()] })
      .mockResolvedValueOnce({ ...APPLIED, template_applications: [prior(), { ...prior(), id: 'app-2' }] });
    let sheet = await openPreview();
    applyAppend(sheet);
    await waitFor(() => expect(screen.queryByLabelText(`template-sheet-${S}`)).not.toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`open-template-sheet-${S}`));
    sheet = await screen.findByLabelText(`template-sheet-${S}`);
    fireEvent.click(await within(sheet).findByLabelText('template-option-tpl-builtin'));
    expect(within(sheet).getByLabelText(`template-summary-${S}`)).toHaveTextContent('Zostaną dodane 2 prace');
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expectNoRepeatClaim(sheet);
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(2));
    const [first, second] = applyCalls();
    expect(second.application_id).not.toBe(first.application_id);
    expect(second.mode).toBe('APPEND');
  });

  it('scenario 4: an uncertain-network retry of the same Apply reuses the application_id', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan(undefined, { template_applications: [prior()] }));
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(APPLIED);
    const sheet = await openPreview();
    applyAppend(sheet);
    await within(sheet).findByLabelText(`template-apply-error-${S}`);
    fireEvent.click(within(sheet).getByText('Spróbuj ponownie'));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(2));
    const [first, second] = applyCalls();
    expect(second).toEqual(first);
  });

  it('scenario 5: the editor never rewrites history -- removing works saves no template_applications', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(
      plan([work('w-crack', 'key-crack', 0), work('w-n1', 'key-N1', 1)], { template_applications: [prior()] }),
    );
    vi.mocked(workPlansApi.putSurfaceWorkPlan).mockResolvedValue(
      plan([work('w-crack', 'key-crack', 0)], { template_applications: [prior()] }),
    );
    renderEditor();
    await screen.findByLabelText(`open-template-sheet-${S}`);
    fireEvent.click(screen.getAllByLabelText(/^remove-occurrence-/)[1]);
    fireEvent.click(screen.getByLabelText(`save-work-plan-${S}`));
    await waitFor(() => expect(workPlansApi.putSurfaceWorkPlan).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(workPlansApi.putSurfaceWorkPlan).mock.calls[0][3];
    expect(payload.planned_works?.map((w) => w.occurrence_key)).toEqual(['key-crack']);
    expect(payload).not.toHaveProperty('template_applications'); // no intent -> server history untouched
  });

  it('REPLACE of a previously applied template keeps its own destructive confirmation only', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan(undefined, { template_applications: [prior()] }));
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-mode-REPLACE'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(within(sheet).getByLabelText(`template-replace-confirm-${S}`)).toBeInTheDocument();
    expect(sheet).not.toHaveTextContent('był już zastosowany');
  });

  // ---- 13E.5B-FIX.2: persisted state after a server-side apply ---------------

  it('after apply shows "applied and saved", keeps Save disabled, and an ordinary edit enables Save', async () => {
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(APPLIED);
    const sheet = await openPreview();
    applyAppend(sheet);
    await waitFor(() => expect(screen.queryByLabelText(`template-sheet-${S}`)).not.toBeInTheDocument());
    const status = screen.getByLabelText(`template-applied-${S}`);
    expect(status).toHaveTextContent('Proces technologiczny zastosowany i zapisany.');
    expect(status).toHaveTextContent('nie trzeba klikać „Zapisz”');
    const save = screen.getByLabelText(`save-work-plan-${S}`);
    expect(save).toBeDisabled();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
    // Ordinary editor change (reorder) -> dirty -> Save enabled, success notice gone.
    fireEvent.click(screen.getAllByLabelText(/^move-down-occurrence-/)[0]);
    expect(save).toBeEnabled();
    expect(screen.queryByLabelText(`template-applied-${S}`)).not.toBeInTheDocument();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
  });

  it('shows the Russian "applied and saved" notice', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(APPLIED);
    const sheet = await openPreview();
    applyAppend(sheet);
    expect(await screen.findByLabelText(`template-applied-${S}`)).toHaveTextContent('Технологический процесс применён и сохранён.');
    expect(screen.getByLabelText(`save-work-plan-${S}`)).toBeDisabled();
  });

  // ---- 13E.5B-FIX.4: final APPEND review, duplicate-aware ---------------------

  const GLADZ = item('a', 'Gładź szpachlowa — 2 warstwy (pakiet)');
  const ODK = item('b', 'Odkurzanie i czyszczenie podłoża');
  const GRUNT = item('c', 'Gruntowanie gruntem penetrującym');
  const SZLIF = item('d', 'Szlifowanie gładzi z odpylaniem');
  const S3 = template({
    id: 'tpl-s3', steps: [step('B', 0, false, ODK), step('C', 1, true, GRUNT), step('A', 2, false, GLADZ), step('D', 3, false, SZLIF)],
  });
  const existingA = { ...work('w-A', 'key-A', 0, 1, GLADZ), wait_after_hours: 12 };
  const reviewRow = (sheet: HTMLElement, id: string) => within(sheet).getByLabelText(`template-review-step-${id}`);

  it('owner walkthrough: existing Gładź is skipped by default, B/C/D appended, then re-open shows all as in plan', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan([existingA]));
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [S3], total: 1 });
    const afterFirst = plan([
      existingA, work('n-B', 'key-B2', 1, 0, ODK), work('n-C', 'key-C2', 2, 0, GRUNT), work('n-D', 'key-D2', 3, 0, SZLIF),
    ], { template_applications: [prior('tpl-s3')] });
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValueOnce(afterFirst);
    let sheet = await openPreview('tpl-s3');
    fireEvent.click(within(sheet).getByLabelText('template-optional-C'));
    const preSummary = within(sheet).getByLabelText(`template-summary-${S}`);
    expect(preSummary).toHaveTextContent('Zostaną dodane 4 prace');
    expect(preSummary).toHaveTextContent('Już w planie: 1 — sprawdzisz je w następnym kroku.');

    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(templatesApi.applyTemplateToWorkPlan).not.toHaveBeenCalled();
    expect(sheet).toHaveTextContent('Prace, które zostaną dodane');
    const rows = within(within(sheet).getByLabelText(`template-review-${S}`)).getAllByRole('listitem');
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual(
      ['B', 'C', 'A', 'D'].map((id) => `template-review-step-${id}`), // exact template order
    );
    for (const id of ['B', 'C', 'D']) {
      expect(within(sheet).getByLabelText(`template-review-toggle-${id}`)).toBeChecked();
      expect(within(sheet).queryByLabelText(`template-review-in-plan-${id}`)).not.toBeInTheDocument();
      expect(within(sheet).getByLabelText(`template-review-status-${id}`)).toHaveTextContent('Zostanie dodana');
    }
    expect(reviewRow(sheet, 'B')).toHaveTextContent('Wymagany');
    expect(reviewRow(sheet, 'C')).toHaveTextContent('Opcjonalny');
    expect(within(sheet).getByLabelText('template-review-toggle-A')).not.toBeChecked();
    expect(within(sheet).getByLabelText('template-review-in-plan-A')).toHaveTextContent('Już w planie: 1');
    expect(reviewRow(sheet, 'A')).toHaveTextContent('Wymagany');
    expect(reviewRow(sheet, 'A')).toHaveTextContent('Ta praca jest już w planie. Możesz pominąć jej ponowne dodanie.');
    expect(within(sheet).getByLabelText('template-review-status-A')).toHaveTextContent('Pominięta');
    const reviewSummary = within(sheet).getByLabelText(`template-review-summary-${S}`);
    expect(reviewSummary).toHaveTextContent('Zostaną dodane 3 prace');
    expect(reviewSummary).toHaveTextContent('2 wymagane + 1 wybrana opcjonalna');
    expect(reviewSummary).toHaveTextContent('Pominięte: 1');

    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(screen.queryByLabelText(`template-sheet-${S}`)).not.toBeInTheDocument());
    expect(applyCalls()[0]).toMatchObject({
      mode: 'APPEND', selected_step_ids: ['B', 'C', 'D'], selected_optional_step_ids: [], expected_step_ids: ['B', 'C', 'A', 'D'],
    });
    const listed = within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem');
    expect(listed).toHaveLength(4);
    expect(listed[0]).toHaveTextContent('Gładź szpachlowa — 2 warstwy (pakiet)');
    expect(listed.filter((r) => r.textContent?.includes('Gładź szpachlowa'))).toHaveLength(1);
    expect(screen.getByLabelText(`template-applied-${S}`)).toHaveTextContent('Proces technologiczny zastosowany i zapisany.');
    expect(screen.getByLabelText(`save-work-plan-${S}`)).toBeDisabled();
    expect(workPlansApi.putSurfaceWorkPlan).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    // Re-open: every candidate is now represented in the CURRENT plan.
    fireEvent.click(screen.getByLabelText(`open-template-sheet-${S}`));
    sheet = await screen.findByLabelText(`template-sheet-${S}`);
    fireEvent.click(await within(sheet).findByLabelText('template-option-tpl-s3'));
    fireEvent.click(within(sheet).getByLabelText('template-optional-C'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expectNoRepeatClaim(sheet);
    for (const id of ['B', 'C', 'A', 'D']) {
      expect(within(sheet).getByLabelText(`template-review-toggle-${id}`)).not.toBeChecked();
      expect(within(sheet).getByLabelText(`template-review-in-plan-${id}`)).toHaveTextContent('Już w planie: 1');
    }
    expect(within(sheet).getByLabelText(`template-review-summary-${S}`)).toHaveTextContent('Zostanie dodanych 0 prac');
    expect(within(sheet).getByRole('alert')).toHaveTextContent('Wybierz co najmniej jedną pracę.');
    expect(within(sheet).getByLabelText(`template-review-confirm-${S}`)).toBeDisabled();

    // A deliberate duplicate is still possible.
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValueOnce(
      plan([...afterFirst.planned_works, work('n-A', 'key-A3', 4, 0, GLADZ)]),
    );
    fireEvent.click(within(sheet).getByLabelText('template-review-toggle-A'));
    expect(within(sheet).getByLabelText(`template-review-summary-${S}`)).toHaveTextContent('Zostanie dodana 1 praca');
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(2));
    const [first, second] = applyCalls();
    expect(second.selected_step_ids).toEqual(['A']);
    expect(second.application_id).not.toBe(first.application_id);
    await waitFor(() => expect(within(screen.getByLabelText(`planned-works-${S}`)).getAllByRole('listitem')).toHaveLength(5));
  });

  it('"Wróć" leaves the review without sending; mode/optional choices are kept', async () => {
    const sheet = await openPreview();
    fireEvent.click(within(sheet).getByLabelText('template-optional-st-2'));
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    fireEvent.click(within(sheet).getByText('Wróć'));
    expect(within(sheet).queryByLabelText(`template-review-${S}`)).not.toBeInTheDocument();
    expect(within(sheet).getByLabelText('template-optional-st-2')).toBeChecked();
    expect(templatesApi.applyTemplateToWorkPlan).not.toHaveBeenCalled();
  });

  it('repeated PriceItem candidates stay distinct rows; plan P x1 -> both skipped, either or both can be chosen', async () => {
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan([work('w-p', 'key-P', 0, 0, P1)]));
    vi.mocked(templatesApi.applyTemplateToWorkPlan).mockResolvedValue(APPLIED);
    const sheet = await openPreview(); // st-1 P1 (req), st-2 P2 (opt, off), st-3 P1 (req)
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    const rows = within(within(sheet).getByLabelText(`template-review-${S}`)).getAllByRole('listitem');
    expect(rows).toHaveLength(2); // not collapsed
    for (const id of ['st-1', 'st-3']) {
      expect(within(sheet).getByLabelText(`template-review-toggle-${id}`)).not.toBeChecked();
      expect(within(sheet).getByLabelText(`template-review-in-plan-${id}`)).toHaveTextContent('Już w planie: 1');
    }
    fireEvent.click(within(sheet).getByLabelText('template-review-toggle-st-1'));
    expect(reviewRow(sheet, 'st-3')).toHaveTextContent('Także wyżej na tej liście: 1');
    fireEvent.click(within(sheet).getByLabelText('template-review-toggle-st-3'));
    expect(within(sheet).getByLabelText(`template-review-summary-${S}`)).toHaveTextContent('Zostaną dodane 2 prace');
    fireEvent.click(within(sheet).getByLabelText(`template-review-confirm-${S}`));
    await waitFor(() => expect(templatesApi.applyTemplateToWorkPlan).toHaveBeenCalledTimes(1));
    expect(applyCalls()[0].selected_step_ids).toEqual(['st-1', 'st-3']);
  });

  it('a template-defined repeat with nothing in the plan keeps both checked but flags the later one', async () => {
    const sheet = await openPreview(); // default plan: PX only
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(within(sheet).getByLabelText('template-review-toggle-st-1')).toBeChecked();
    expect(within(sheet).getByLabelText('template-review-toggle-st-3')).toBeChecked();
    expect(within(sheet).queryByLabelText('template-review-in-plan-st-3')).not.toBeInTheDocument();
    expect(reviewRow(sheet, 'st-3')).toHaveTextContent('Także wyżej na tej liście: 1');
    expect(reviewRow(sheet, 'st-1')).not.toHaveTextContent('Także wyżej');
  });

  it('renders the final review in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(plan([existingA]));
    vi.mocked(templatesApi.fetchCompatibleTemplates).mockResolvedValue({ items: [S3], total: 1 });
    const sheet = await openPreview('tpl-s3');
    fireEvent.click(within(sheet).getByLabelText('template-optional-C'));
    expect(within(sheet).getByLabelText(`template-summary-${S}`)).toHaveTextContent('Уже в плане: 1 — проверите на следующем шаге.');
    fireEvent.click(within(sheet).getByLabelText(`template-apply-${S}`));
    expect(sheet).toHaveTextContent('Работы, которые будут добавлены');
    expect(within(sheet).getByLabelText('template-review-in-plan-A')).toHaveTextContent('Уже в плане: 1');
    expect(reviewRow(sheet, 'A')).toHaveTextContent('Эта работа уже есть в плане. Можно не добавлять её повторно.');
    expect(within(sheet).getByLabelText('template-review-status-A')).toHaveTextContent('Пропущена');
    expect(within(sheet).getByLabelText('template-review-status-B')).toHaveTextContent('Будет добавлена');
    const summary = within(sheet).getByLabelText(`template-review-summary-${S}`);
    expect(summary).toHaveTextContent('Будут добавлены 3 работы');
    expect(summary).toHaveTextContent('Пропущено: 1');
    expect(within(sheet).getByText('Назад')).toBeInTheDocument();
    expect(within(sheet).getByLabelText(`template-review-confirm-${S}`)).toHaveTextContent('Добавить выбранные');
    for (const id of ['B', 'C', 'D']) fireEvent.click(within(sheet).getByLabelText(`template-review-toggle-${id}`));
    expect(within(sheet).getByRole('alert')).toHaveTextContent('Выберите хотя бы одну работу.');
    expect(within(sheet).getByLabelText(`template-review-confirm-${S}`)).toBeDisabled();
  });
});
