/**
 * Stage 13F.4 — Cennik → Procesy management actions: create, edit metadata,
 * duplicate, archive (confirmed) and restore. Steps stay read-only (13F.5).
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/workflowTemplates';
import { ApiError } from '../api/http';
import { I18nProvider, useI18n } from '../hooks/useI18n';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { WorkflowTemplateRead, WorkflowTemplateStepRead } from '../types/workflowTemplate';
import { WorkflowTemplateManager } from './WorkflowTemplateManager';

vi.mock('../api/workflowTemplates', async (orig) => ({
  ...(await orig<typeof import('../api/workflowTemplates')>()), // real classifier
  fetchWorkflowTemplates: vi.fn(),
  fetchWorkflowTemplate: vi.fn(),
  createWorkflowTemplate: vi.fn(),
  updateWorkflowTemplate: vi.fn(),
  archiveWorkflowTemplate: vi.fn(),
  restoreWorkflowTemplate: vi.fn(),
}));

const S2_PL = pl.workflow_templates.description.s2;
const S2_RU = ru.workflow_templates.description.s2;
const CLEAN_PL = pl.workflow_templates.step_note.clean;

function item(id: string, name: string, extra: Partial<SurfacePriceItemSummaryRead> = {}): SurfacePriceItemSummaryRead {
  return {
    id, code: id.toUpperCase(), name_key: null, display_name: name, category: 'SKIM_COAT', unit: 'M2',
    price_scope: 'LABOR', price: '10.00', currency: 'PLN', is_archived: false, quality_level: null, ...extra,
  };
}
const PRIME = item('p1', 'Gruntowanie');
const SKIM = item('p2', 'Gładź');
function step(id: string, position: number, priceItem: SurfacePriceItemSummaryRead, extra: Partial<WorkflowTemplateStepRead> = {}): WorkflowTemplateStepRead {
  return { id, position, price_item_id: priceItem.id, is_optional: false, note: null, wait_after_hours: null, price_item: priceItem, ...extra };
}

const builtin: WorkflowTemplateRead = {
  id: 'tpl-b', code: 'TECH_BETON_S2-01', name_key: 'workflow_templates.seed.tech_beton_s2', display_name: null,
  description: S2_PL, description_key: 'workflow_templates.description.s2',
  applies_to_substrates: ['CONCRETE'], applies_to_quality: ['S2'], applies_to_surface_types: ['WALL', 'CEILING'],
  position: 0, is_archived: false, is_default: true, created_at: '', updated_at: '',
  steps: [
    step('s1', 0, PRIME, { note: CLEAN_PL, note_key: 'workflow_templates.step_note.clean', wait_after_hours: 24 }),
    step('s2', 1, SKIM, { is_optional: true, note: 'Moja notatka' }),
    step('s3', 2, PRIME), // repeated PriceItem
  ],
};
const custom: WorkflowTemplateRead = {
  ...builtin, id: 'tpl-c', code: 'CUSTOM_AAA111', name_key: null, display_name: 'Mój proces', description: 'Opis',
  description_key: null, is_default: false, applies_to_substrates: [], applies_to_quality: [], applies_to_surface_types: [],
  steps: [],
};
const archivedTpl: WorkflowTemplateRead = { ...custom, id: 'tpl-a', display_name: 'Stary', is_archived: true };

let active: WorkflowTemplateRead[];
let archived: WorkflowTemplateRead[];

function LocaleSwitch() {
  const { setLocale } = useI18n();
  return <button type="button" aria-label="switch-ru" onClick={() => setLocale('ru')}>ru</button>;
}
function renderManager() {
  return render(<I18nProvider><LocaleSwitch /><WorkflowTemplateManager /></I18nProvider>);
}
const openCard = async (id: string) => fireEvent.click(await screen.findByLabelText(`process-card-${id}`));
const setField = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  active = [builtin, custom];
  archived = [archivedTpl];
  vi.mocked(api.fetchWorkflowTemplates).mockImplementation(async ({ archived: which }) =>
    which === 'archived' ? { items: archived, total: archived.length } : { items: active, total: active.length });
});

// ---- CREATE -----------------------------------------------------------------

describe('create (13F.4)', () => {
  it('creates an empty custom template (server code), refreshes it and explains that steps come later', async () => {
    const created: WorkflowTemplateRead = { ...custom, id: 'tpl-new', code: 'CUSTOM_NEW', display_name: 'Nowy', description: null,
      applies_to_surface_types: ['WALL'], applies_to_substrates: ['CONCRETE'], applies_to_quality: ['S2'] };
    vi.mocked(api.createWorkflowTemplate).mockResolvedValue(created);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(created);
    renderManager();
    fireEvent.click(await screen.findByLabelText('process-create'));
    const form = screen.getByLabelText('process-form-create');
    expect(form).toHaveTextContent('Kroki technologiczne dodasz potem przyciskiem „Edytuj kroki”');
    expect(within(form).queryByLabelText(/step/)).toBeNull(); // no step editing
    setField('process-field-name', '  Nowy  ');
    fireEvent.click(screen.getByLabelText('process-field-surface-WALL'));
    fireEvent.click(screen.getByLabelText('process-field-substrate-CONCRETE'));
    fireEvent.click(screen.getByLabelText('process-field-quality-S2'));
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(api.createWorkflowTemplate).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(api.createWorkflowTemplate).mock.calls[0][0];
    expect(payload).toEqual({
      display_name: 'Nowy', description: null, applies_to_surface_types: ['WALL'],
      applies_to_substrates: ['CONCRETE'], applies_to_quality: ['S2'], steps: [],
    });
    expect(payload).not.toHaveProperty('code');
    expect(api.fetchWorkflowTemplate).toHaveBeenCalledWith('tpl-new');
    const detail = await screen.findByLabelText('process-detail-tpl-new');
    expect(within(detail).getByLabelText('processes-notice')).toHaveTextContent('Proces utworzony.');
    expect(within(detail).getByLabelText('process-steps-empty')).toHaveTextContent('Proces bez kroków nie może zostać zastosowany');
    expect(detail).toHaveTextContent('CUSTOM_NEW');
  });

  it('blocks an empty name without calling the server', async () => {
    renderManager();
    fireEvent.click(await screen.findByLabelText('process-create'));
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    expect(await screen.findByLabelText('process-form-error')).toHaveTextContent('Podaj nazwę procesu.');
    expect(api.createWorkflowTemplate).not.toHaveBeenCalled();
  });

  it('shows localized validation, quality-scale and network errors near the form', async () => {
    vi.mocked(api.createWorkflowTemplate)
      .mockRejectedValueOnce(new ApiError('Quality target Q2 does not fit any substrate in the template filter: x', 422))
      .mockRejectedValueOnce(new ApiError('something unexpected', 422))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'));
    renderManager();
    fireEvent.click(await screen.findByLabelText('process-create'));
    setField('process-field-name', 'X');
    const submit = () => fireEvent.click(screen.getByLabelText('process-form-submit'));
    submit();
    expect(await screen.findByText(/Wybrane klasy jakości nie pasują/)).toBeInTheDocument();
    submit();
    await waitFor(() => expect(screen.getByLabelText('process-form-error')).toHaveTextContent('Nie udało się zapisać procesu.'));
    expect(screen.getByLabelText('process-form-error')).toHaveTextContent('something unexpected');
    submit();
    await waitFor(() => expect(screen.getByLabelText('process-form-error')).toHaveTextContent('Brak połączenia'));
    expect(screen.getByLabelText('process-form-create')).toBeInTheDocument(); // still on the form, input kept
    expect(screen.getByLabelText('process-field-name')).toHaveValue('X');
  });

  it('prevents double submission', async () => {
    let resolve: (tpl: WorkflowTemplateRead) => void = () => {};
    vi.mocked(api.createWorkflowTemplate).mockReturnValue(new Promise((r) => { resolve = r; }));
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(custom);
    renderManager();
    fireEvent.click(await screen.findByLabelText('process-create'));
    setField('process-field-name', 'X');
    const submit = screen.getByLabelText('process-form-submit');
    fireEvent.click(submit);
    fireEvent.click(submit);
    expect(submit).toBeDisabled();
    await act(async () => resolve(custom));
    expect(api.createWorkflowTemplate).toHaveBeenCalledTimes(1);
  });
});

// ---- EDIT -------------------------------------------------------------------

describe('edit metadata (13F.4)', () => {
  it('custom: PATCHes only changed fields and shows the refreshed server state', async () => {
    vi.mocked(api.updateWorkflowTemplate).mockResolvedValue(custom);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue({ ...custom, display_name: 'Nazwa z serwera', description: 'Nowy opis' });
    renderManager();
    await openCard('tpl-c');
    fireEvent.click(screen.getByLabelText('process-edit'));
    expect(screen.getByLabelText('process-field-name')).toHaveValue('Mój proces');
    setField('process-field-name', 'Nowa nazwa');
    setField('process-field-description', 'Nowy opis');
    fireEvent.click(screen.getByLabelText('process-field-surface-CEILING'));
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(api.updateWorkflowTemplate).toHaveBeenCalledWith('tpl-c', {
      display_name: 'Nowa nazwa', description: 'Nowy opis', applies_to_surface_types: ['CEILING'],
    }));
    const detail = await screen.findByLabelText('process-detail-tpl-c');
    expect(detail).toHaveTextContent('Nazwa z serwera'); // canonical server response, not local state
    expect(detail).toHaveTextContent('Zmiany zapisane.');
  });

  it('custom: clearing the name is blocked', async () => {
    renderManager();
    await openCard('tpl-c');
    fireEvent.click(screen.getByLabelText('process-edit'));
    setField('process-field-name', '   ');
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    expect(await screen.findByLabelText('process-form-error')).toHaveTextContent('Podaj nazwę procesu.');
    expect(api.updateWorkflowTemplate).not.toHaveBeenCalled();
  });

  it('built-in: set a custom name, then clear it -> canonical localized name returns', async () => {
    vi.mocked(api.updateWorkflowTemplate).mockResolvedValue(builtin);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValueOnce({ ...builtin, display_name: 'Mój beton' });
    renderManager();
    await openCard('tpl-b');
    fireEvent.click(screen.getByLabelText('process-edit'));
    const nameField = screen.getByLabelText('process-field-name');
    expect(nameField).toHaveValue('');
    expect(nameField).toHaveAttribute('placeholder', 'Beton — S2 — standard malarski');
    setField('process-field-name', 'Mój beton');
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(api.updateWorkflowTemplate).toHaveBeenLastCalledWith('tpl-b', { display_name: 'Mój beton' }));
    expect(await screen.findByLabelText('process-detail-tpl-b')).toHaveTextContent('Mój beton');

    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValueOnce(builtin); // server cleared it
    fireEvent.click(screen.getByLabelText('process-edit'));
    setField('process-field-name', '');
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(api.updateWorkflowTemplate).toHaveBeenLastCalledWith('tpl-b', { display_name: null }));
    const detail = await screen.findByLabelText('process-detail-tpl-b');
    expect(detail).toHaveTextContent('Beton — S2 — standard malarski');
    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(screen.getByLabelText('process-detail-tpl-b')).toHaveTextContent('Бетон — S2'));
  });

  it('built-in: owner description is verbatim in PL and RU; restoring canonical text lets localization resume', async () => {
    vi.mocked(api.updateWorkflowTemplate).mockResolvedValue(builtin);
    vi.mocked(api.fetchWorkflowTemplate)
      .mockResolvedValueOnce({ ...builtin, description: 'Moja wersja', description_key: null })
      .mockResolvedValueOnce(builtin);
    renderManager();
    await openCard('tpl-b');
    fireEvent.click(screen.getByLabelText('process-edit'));
    expect(screen.getByLabelText('process-form-edit')).toHaveTextContent('To opis domyślny');
    setField('process-field-description', 'Moja wersja');
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(api.updateWorkflowTemplate).toHaveBeenLastCalledWith('tpl-b', { description: 'Moja wersja' }));
    expect(await screen.findByLabelText('process-description')).toHaveTextContent('Moja wersja');
    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(screen.getByLabelText('process-detail-back')).toHaveTextContent('Процессы'));
    expect(screen.getByLabelText('process-description')).toHaveTextContent('Moja wersja');

    fireEvent.click(screen.getByLabelText('process-edit'));
    setField('process-field-description', S2_PL);
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(api.updateWorkflowTemplate).toHaveBeenLastCalledWith('tpl-b', { description: S2_PL }));
    await waitFor(() => expect(screen.getByLabelText('process-description')).toHaveTextContent(S2_RU));
  });

  it('unchanged save sends no PATCH but still refreshes from the server', async () => {
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(builtin);
    renderManager();
    await openCard('tpl-b');
    fireEvent.click(screen.getByLabelText('process-edit'));
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(api.fetchWorkflowTemplate).toHaveBeenCalledWith('tpl-b'));
    expect(api.updateWorkflowTemplate).not.toHaveBeenCalled();
  });
});

// ---- DUPLICATE --------------------------------------------------------------

describe('duplicate (13F.4)', () => {
  it('built-in -> new custom template with the same ordered steps; source untouched', async () => {
    const copy: WorkflowTemplateRead = { ...builtin, id: 'tpl-copy', code: 'CUSTOM_COPY1', name_key: null,
      display_name: 'Beton — S2 — standard malarski — kopia', description_key: null, is_default: false,
      steps: builtin.steps.map((s, i) => ({ ...s, id: `copy-${i}`, note_key: null })) };
    vi.mocked(api.createWorkflowTemplate).mockResolvedValue(copy);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(copy);
    const before = JSON.stringify(builtin);
    renderManager();
    fireEvent.click(screen.getByLabelText('switch-ru')); // UI language must not change what is copied
    await openCard('tpl-b');
    fireEvent.click(screen.getByLabelText('process-duplicate'));
    const form = screen.getByLabelText('process-form-duplicate');
    expect(form).toHaveTextContent('Оригинал не изменится');
    expect(screen.getByLabelText('process-field-name')).toHaveValue('Бетон — S2 — стандарт под покраску — копия');
    setField('process-field-name', 'Beton — S2 — standard malarski — kopia');
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(api.createWorkflowTemplate).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.createWorkflowTemplate).mock.calls[0][0]).toEqual({
      display_name: 'Beton — S2 — standard malarski — kopia',
      description: S2_PL, // stored text, verbatim
      applies_to_surface_types: ['WALL', 'CEILING'], applies_to_substrates: ['CONCRETE'], applies_to_quality: ['S2'],
      steps: [
        { price_item_id: 'p1', is_optional: false, note: CLEAN_PL, wait_after_hours: 24 },
        { price_item_id: 'p2', is_optional: true, note: 'Moja notatka', wait_after_hours: null },
        { price_item_id: 'p1', is_optional: false, note: null, wait_after_hours: null },
      ],
    });
    const detail = await screen.findByLabelText('process-detail-tpl-copy');
    expect(detail).toHaveTextContent('CUSTOM_COPY1');
    expect(detail).not.toHaveTextContent('По умолчанию');
    expect(within(within(detail).getByLabelText('process-steps')).getAllByRole('listitem')).toHaveLength(3);
    expect(JSON.stringify(builtin)).toBe(before);
    expect(api.updateWorkflowTemplate).not.toHaveBeenCalled();
    expect(api.archiveWorkflowTemplate).not.toHaveBeenCalled();
  });

  it('custom template duplicates too (empty template -> empty copy)', async () => {
    vi.mocked(api.createWorkflowTemplate).mockResolvedValue({ ...custom, id: 'tpl-c2', code: 'CUSTOM_C2' });
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue({ ...custom, id: 'tpl-c2', code: 'CUSTOM_C2', display_name: 'Mój proces — kopia' });
    renderManager();
    await openCard('tpl-c');
    fireEvent.click(screen.getByLabelText('process-duplicate'));
    expect(screen.getByLabelText('process-field-name')).toHaveValue('Mój proces — kopia');
    fireEvent.click(screen.getByLabelText('process-form-submit'));
    await waitFor(() => expect(vi.mocked(api.createWorkflowTemplate).mock.calls[0][0]).toMatchObject({
      display_name: 'Mój proces — kopia', description: 'Opis', steps: [] }));
    expect(await screen.findByLabelText('process-detail-tpl-c2')).toHaveTextContent('Kopia utworzona jako nowy proces.');
  });

  it('a source with an archived price item cannot be duplicated (explained, nothing sent)', async () => {
    active = [{ ...builtin, steps: [...builtin.steps, step('s4', 3, item('p9', 'Stara', { is_archived: true }))] }];
    renderManager();
    await openCard('tpl-b');
    fireEvent.click(screen.getByLabelText('process-duplicate'));
    expect(screen.getByRole('alert')).toHaveTextContent('Nie można zduplikować');
    expect(screen.getByLabelText('process-form-submit')).toBeDisabled();
    expect(api.createWorkflowTemplate).not.toHaveBeenCalled();
  });
});

// ---- ARCHIVE / RESTORE --------------------------------------------------------

describe('archive / restore (13F.4)', () => {
  it('archive needs confirmation; confirmed archive leaves the active list', async () => {
    vi.mocked(api.archiveWorkflowTemplate).mockImplementation(async () => {
      active = [builtin];
      archived = [archivedTpl, { ...custom, is_archived: true }];
      return { ...custom, is_archived: true };
    });
    renderManager();
    await openCard('tpl-c');
    fireEvent.click(screen.getByLabelText('process-archive'));
    const confirm = screen.getByLabelText('process-archive-confirm');
    expect(confirm).toHaveTextContent('Istniejące plany prac, kosztorysy i historia zastosowań NIE zostaną zmienione');
    fireEvent.click(within(confirm).getByText('Anuluj'));
    expect(api.archiveWorkflowTemplate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('process-archive'));
    fireEvent.click(screen.getByLabelText('process-archive-confirm-yes'));
    await waitFor(() => expect(api.archiveWorkflowTemplate).toHaveBeenCalledWith('tpl-c'));
    expect(await screen.findByLabelText('processes-notice')).toHaveTextContent('Proces zarchiwizowany.');
    await waitFor(() => expect(screen.queryByLabelText('process-card-tpl-c')).not.toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('processes-tab-archived'));
    expect(await screen.findByLabelText('process-card-tpl-c')).toHaveTextContent('Zarchiwizowany');
  });

  it('restore returns the template to the active list', async () => {
    vi.mocked(api.restoreWorkflowTemplate).mockImplementation(async () => {
      archived = [];
      active = [...active, { ...archivedTpl, is_archived: false }];
      return { ...archivedTpl, is_archived: false };
    });
    renderManager();
    await screen.findByLabelText('process-card-tpl-b');
    fireEvent.click(screen.getByLabelText('processes-tab-archived'));
    await openCard('tpl-a');
    expect(screen.queryByLabelText('process-archive')).toBeNull();
    fireEvent.click(screen.getByLabelText('process-restore'));
    await waitFor(() => expect(api.restoreWorkflowTemplate).toHaveBeenCalledWith('tpl-a'));
    const detail = await screen.findByLabelText('process-detail-tpl-a');
    expect(detail).toHaveTextContent('Proces przywrócony.');
    expect(detail).not.toHaveTextContent('Zarchiwizowany');
    fireEvent.click(screen.getByLabelText('process-detail-back'));
    expect(screen.getByLabelText('processes-tab-active')).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByLabelText('process-card-tpl-a')).toBeInTheDocument();
  });

  it('archive failure is shown near the action; there is no delete action anywhere', async () => {
    vi.mocked(api.archiveWorkflowTemplate).mockRejectedValue(new TypeError('Failed to fetch'));
    renderManager();
    await openCard('tpl-c');
    const detail = screen.getByLabelText('process-detail-tpl-c');
    expect(within(detail).queryByText(/usuń/i)).toBeNull();
    expect(detail.querySelector('[aria-label*="delete"]')).toBeNull();
    fireEvent.click(screen.getByLabelText('process-archive'));
    fireEvent.click(screen.getByLabelText('process-archive-confirm-yes'));
    expect(await screen.findByLabelText('process-action-error')).toHaveTextContent('Brak połączenia');
    expect(screen.getByLabelText('process-detail-tpl-c')).toBeInTheDocument();
  });
});

describe('Russian UI (13F.4)', () => {
  it('actions and form are fully Russian', async () => {
    localStorage.setItem('locale', 'ru');
    render(<I18nProvider><WorkflowTemplateManager /></I18nProvider>);
    expect(await screen.findByLabelText('process-create')).toHaveTextContent('+ Новый процесс');
    await openCard('tpl-c');
    expect(screen.getByLabelText('process-edit')).toHaveTextContent('Редактировать');
    expect(screen.getByLabelText('process-duplicate')).toHaveTextContent('Дублировать');
    expect(screen.getByLabelText('process-archive')).toHaveTextContent('Архивировать');
    fireEvent.click(screen.getByLabelText('process-archive'));
    expect(screen.getByLabelText('process-archive-confirm')).toHaveTextContent('Существующие планы работ, сметы и история применений НЕ изменятся');
    fireEvent.click(screen.getByText('Отмена'));
    fireEvent.click(screen.getByLabelText('process-edit'));
    expect(screen.getByLabelText('process-form-edit')).toHaveTextContent('Редактировать данные процесса');
  });
});
