/**
 * Stage 13F.5 — workflow template step editor (explicit draft + expected_step_ids).
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as priceItemsApi from '../api/priceItems';
import * as api from '../api/workflowTemplates';
import { ApiError } from '../api/http';
import { I18nProvider, useI18n } from '../hooks/useI18n';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { PriceItem } from '../types/priceItem';
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { WorkflowTemplateRead, WorkflowTemplateStepRead } from '../types/workflowTemplate';
import { WorkflowTemplateManager } from './WorkflowTemplateManager';

vi.mock('../api/priceItems', () => ({
  fetchPriceItems: vi.fn(), createPriceItem: vi.fn(), updatePriceItem: vi.fn(),
  archivePriceItem: vi.fn(), restorePriceItem: vi.fn(),
}));
vi.mock('../api/workflowTemplates', async (orig) => ({
  ...(await orig<typeof import('../api/workflowTemplates')>()), // real classifier
  fetchWorkflowTemplates: vi.fn(),
  fetchWorkflowTemplate: vi.fn(),
  replaceWorkflowTemplateSteps: vi.fn(),
  updateWorkflowTemplate: vi.fn(),
  createWorkflowTemplate: vi.fn(),
  archiveWorkflowTemplate: vi.fn(),
  restoreWorkflowTemplate: vi.fn(),
}));

const CLEAN_PL = pl.workflow_templates.step_note.clean;
const CLEAN_RU = ru.workflow_templates.step_note.clean;
const CLEAN_KEY = 'workflow_templates.step_note.clean';

function priceItem(id: string, name: string, extra: Partial<PriceItem> = {}): PriceItem {
  return {
    id, code: id.toUpperCase(), name_key: null, display_name: name, category: 'SKIM_COAT', unit: 'M2', price: '12.50',
    currency: 'PLN', price_scope: 'LABOR', quality_level: null, is_archived: false, created_at: '', updated_at: '', ...extra,
  };
}
const summary = (item: PriceItem): SurfacePriceItemSummaryRead => ({
  id: item.id, code: item.code, name_key: item.name_key, display_name: item.display_name, category: item.category,
  unit: item.unit, price_scope: item.price_scope, price: item.price, currency: item.currency,
  is_archived: item.is_archived, quality_level: item.quality_level,
});
const PRIME = priceItem('p1', 'Gruntowanie', { category: 'PREPARATION' });
const SKIM = priceItem('p2', 'Gładź szpachlowa');
const UNPRICED = priceItem('p3', 'Szpachlowanie dodatkowe', { price: null });
const OLD = priceItem('p9', 'Stara pozycja', { is_archived: true });
const REVEAL = priceItem('p8', 'Ościeże', { category: 'REVEAL', unit: 'LM' });

function step(id: string, item: PriceItem, extra: Partial<WorkflowTemplateStepRead> = {}): WorkflowTemplateStepRead {
  return { id, position: 0, price_item_id: item.id, is_optional: false, note: null, wait_after_hours: null, price_item: summary(item), ...extra };
}

const builtin: WorkflowTemplateRead = {
  id: 'tpl-b', code: 'TECH_BETON_S2-01', name_key: 'workflow_templates.seed.tech_beton_s2', display_name: null,
  description: null, applies_to_substrates: ['CONCRETE'], applies_to_quality: ['S2'], applies_to_surface_types: ['WALL'],
  position: 0, is_archived: false, is_default: true, created_at: '', updated_at: '',
  steps: [
    step('s1', PRIME, { note: CLEAN_PL, note_key: CLEAN_KEY, wait_after_hours: 24 }),
    step('s2', SKIM, { is_optional: true }),
    step('s3', PRIME), // same PriceItem again
  ],
};
const custom: WorkflowTemplateRead = {
  ...builtin, id: 'tpl-c', code: 'CUSTOM_C', name_key: null, display_name: 'Mój proces', is_default: false,
  steps: [step('c1', SKIM, { note: 'Moja notatka' }), step('c2', OLD)],
};
const empty: WorkflowTemplateRead = { ...custom, id: 'tpl-e', display_name: 'Pusty', steps: [] };

function LocaleSwitch() {
  const { setLocale } = useI18n();
  return <button type="button" aria-label="switch-ru" onClick={() => setLocale('ru')}>ru</button>;
}
async function openEditor(id: string) {
  render(<I18nProvider><LocaleSwitch /><WorkflowTemplateManager /></I18nProvider>);
  fireEvent.click(await screen.findByLabelText(`process-card-${id}`));
  fireEvent.click(screen.getByLabelText('process-edit-steps'));
  return screen.getByLabelText(`process-steps-editor-${id}`);
}
const rows = () => within(screen.getByLabelText('steps-editor-list')).getAllByRole('listitem');
const rowNames = () => rows().map((r) => r.querySelector('span.flex-1')?.textContent);
const openOptions = (i: number) => fireEvent.click(screen.getByLabelText(`steps-editor-options-${i}`));
const payload = () => {
  const calls = vi.mocked(api.replaceWorkflowTemplateSteps).mock.calls;
  return calls[calls.length - 1];
};
async function pick(item: PriceItem) {
  fireEvent.click(screen.getByLabelText('steps-editor-add'));
  fireEvent.click(await screen.findByLabelText(`steps-editor-pick-${item.id}`));
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.fetchWorkflowTemplates).mockResolvedValue({ items: [builtin, custom, empty], total: 3 });
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [PRIME, SKIM, UNPRICED, OLD, REVEAL], total: 5 });
});

describe('open / render', () => {
  it('opens from the detail as a separate action and renders steps in order with their state', async () => {
    const editor = await openEditor('tpl-b');
    expect(editor).toHaveTextContent('Kroki technologiczne');
    expect(screen.getByLabelText('steps-editor-count')).toHaveTextContent('Kroki: 3');
    expect(rowNames()).toEqual(['Gruntowanie', 'Gładź szpachlowa', 'Gruntowanie']);
    expect(rows()[0]).toHaveTextContent('Wymagany');
    expect(rows()[0]).toHaveTextContent('Przerwa technologiczna: 24 h');
    expect(rows()[0]).toHaveTextContent('m²');
    expect(rows()[1]).toHaveTextContent('Opcjonalny');
    expect(screen.getByLabelText('steps-editor-note-0')).toHaveTextContent(CLEAN_PL); // canonical note (PL)
    expect(screen.queryByLabelText('steps-editor-note-input-0')).toBeNull(); // progressive disclosure
    expect(screen.getByLabelText('steps-editor-save')).toBeDisabled(); // clean draft
  });

  it('shows archived-item and no-price warnings', async () => {
    vi.mocked(api.fetchWorkflowTemplates).mockResolvedValue({ items: [{ ...custom, steps: [...custom.steps, step('c3', UNPRICED)] }], total: 1 });
    await openEditor('tpl-c');
    expect(rows()[1]).toHaveTextContent('Pozycja zarchiwizowana');
    expect(rows()[2]).toHaveTextContent('Brak ceny w cenniku');
  });
});

describe('add / duplicates / picker', () => {
  it('adds active items, the same item twice, and a no-price item; archived and REVEAL are not offered', async () => {
    await openEditor('tpl-b');
    fireEvent.click(screen.getByLabelText('steps-editor-add'));
    const list = await screen.findByLabelText('steps-editor-picker-list');
    expect(within(list).queryByLabelText('steps-editor-pick-p9')).toBeNull();
    expect(within(list).queryByLabelText('steps-editor-pick-p8')).toBeNull();
    expect(within(list).getByLabelText('steps-editor-pick-p3')).toHaveTextContent('Brak ceny w cenniku');
    expect(within(list).getByLabelText('steps-editor-pick-p1')).toHaveTextContent('12,50');
    fireEvent.change(screen.getByLabelText('steps-editor-picker-search'), { target: { value: 'gład' } });
    expect(within(list).queryByLabelText('steps-editor-pick-p1')).toBeNull();
    fireEvent.click(within(list).getByLabelText('steps-editor-pick-p2'));
    await pick(SKIM);
    await pick(UNPRICED);
    expect(rowNames()).toEqual(['Gruntowanie', 'Gładź szpachlowa', 'Gruntowanie', 'Gładź szpachlowa', 'Gładź szpachlowa', 'Szpachlowanie dodatkowe']);
    expect(screen.getByLabelText('steps-editor-count')).toHaveTextContent('Kroki: 6');
    expect(screen.getByLabelText('steps-editor-save')).toBeEnabled();
  });

  it('an empty template can add its first step and save; an emptied template may save an empty list', async () => {
    vi.mocked(api.replaceWorkflowTemplateSteps).mockResolvedValue(empty);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue({ ...empty, steps: [step('n1', PRIME)] });
    await openEditor('tpl-e');
    expect(screen.getByLabelText('steps-editor-empty')).toBeInTheDocument();
    await pick(PRIME);
    fireEvent.click(screen.getByLabelText('steps-editor-save'));
    await waitFor(() => expect(api.replaceWorkflowTemplateSteps).toHaveBeenCalledWith('tpl-e', [
      { price_item_id: 'p1', is_optional: false, note: null, wait_after_hours: null },
    ], []));
    expect(await screen.findByLabelText('process-detail-tpl-e')).toHaveTextContent('Kroki zapisane.');
  });

  it('removing every step saves an empty list (valid in the API)', async () => {
    vi.mocked(api.replaceWorkflowTemplateSteps).mockResolvedValue(custom);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue({ ...custom, steps: [] });
    await openEditor('tpl-c');
    for (const i of [1, 0]) {
      openOptions(i);
      fireEvent.click(screen.getByLabelText(`steps-editor-remove-${i}`));
      fireEvent.click(screen.getByLabelText(`steps-editor-remove-yes-${i}`));
    }
    fireEvent.click(screen.getByLabelText('steps-editor-save'));
    await waitFor(() => expect(api.replaceWorkflowTemplateSteps).toHaveBeenCalledWith('tpl-c', [], ['c1', 'c2']));
  });
});

describe('edit / reorder / remove', () => {
  it('edits required/optional, note and wait (with day hint); clearing the wait sends null', async () => {
    vi.mocked(api.replaceWorkflowTemplateSteps).mockResolvedValue(builtin);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(builtin);
    await openEditor('tpl-b');
    openOptions(1);
    fireEvent.click(screen.getByLabelText('steps-editor-required-1'));
    fireEvent.change(screen.getByLabelText('steps-editor-note-input-1'), { target: { value: '  Po wyschnięciu  ' } });
    fireEvent.change(screen.getByLabelText('steps-editor-wait-1'), { target: { value: '48' } });
    expect(rows()[1]).toHaveTextContent('48 h = 2 dn.');
    fireEvent.change(screen.getByLabelText('steps-editor-wait-1'), { target: { value: '0' } });
    expect(rows()[1]).toHaveTextContent('Podaj pełną liczbę godzin');
    expect(screen.getByLabelText('steps-editor-save')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('steps-editor-wait-1'), { target: { value: '12' } });
    openOptions(0);
    fireEvent.change(screen.getByLabelText('steps-editor-wait-0'), { target: { value: '' } });
    fireEvent.click(screen.getByLabelText('steps-editor-save'));
    await waitFor(() => expect(api.replaceWorkflowTemplateSteps).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual(['tpl-b', [
      { price_item_id: 'p1', is_optional: false, note: CLEAN_PL, wait_after_hours: null },
      { price_item_id: 'p2', is_optional: false, note: 'Po wyschnięciu', wait_after_hours: 12 },
      { price_item_id: 'p1', is_optional: false, note: null, wait_after_hours: null },
    ], ['s1', 's2', 's3']]);
  });

  it('moves steps up/down with disabled boundaries; duplicate occurrences move independently', async () => {
    await openEditor('tpl-b');
    openOptions(0);
    expect(screen.getByLabelText('steps-editor-up-0')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('steps-editor-down-0'));
    expect(rowNames()).toEqual(['Gładź szpachlowa', 'Gruntowanie', 'Gruntowanie']);
    // the moved row keeps its own note/wait (occurrence identity), the other Gruntowanie is untouched
    expect(rows()[1]).toHaveTextContent('24 h');
    expect(rows()[2]).not.toHaveTextContent('24 h');
    openOptions(2);
    expect(screen.getByLabelText('steps-editor-down-2')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('steps-editor-up-2'));
    expect(rows()[1]).not.toHaveTextContent('24 h');
    expect(rows()[2]).toHaveTextContent('24 h');
  });

  it('removes one duplicate occurrence (with confirmation) and keeps the other', async () => {
    vi.mocked(api.replaceWorkflowTemplateSteps).mockResolvedValue(builtin);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(builtin);
    await openEditor('tpl-b');
    openOptions(2);
    fireEvent.click(screen.getByLabelText('steps-editor-remove-2'));
    expect(screen.getByLabelText('steps-editor-remove-confirm-2')).toHaveTextContent('Istniejące plany prac i kosztorysy nie zostaną zmienione');
    fireEvent.click(within(screen.getByLabelText('steps-editor-remove-confirm-2')).getByText('Anuluj'));
    expect(rows()).toHaveLength(3);
    fireEvent.click(screen.getByLabelText('steps-editor-remove-2'));
    fireEvent.click(screen.getByLabelText('steps-editor-remove-yes-2'));
    expect(rowNames()).toEqual(['Gruntowanie', 'Gładź szpachlowa']);
    expect(rows()[0]).toHaveTextContent('24 h'); // the remaining Gruntowanie is the first occurrence
    fireEvent.click(screen.getByLabelText('steps-editor-save'));
    await waitFor(() => expect(payload()[1].map((s) => s.price_item_id)).toEqual(['p1', 'p2']));
  });

  it('a newly added (unsaved) step is removed without confirmation', async () => {
    await openEditor('tpl-b');
    await pick(SKIM);
    fireEvent.click(screen.getByLabelText('steps-editor-remove-3'));
    expect(rows()).toHaveLength(3);
    expect(screen.getByLabelText('steps-editor-save')).toBeDisabled(); // back to the server state
  });
});

describe('save / concurrency / errors', () => {
  it('saves the ordered payload with the ORIGINAL expected_step_ids and shows the refreshed server detail', async () => {
    const fresh: WorkflowTemplateRead = { ...builtin, steps: [step('n1', SKIM), step('n2', PRIME)] };
    vi.mocked(api.replaceWorkflowTemplateSteps).mockResolvedValue(builtin);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(fresh);
    await openEditor('tpl-b');
    openOptions(0);
    fireEvent.click(screen.getByLabelText('steps-editor-down-0'));
    fireEvent.click(screen.getByLabelText('steps-editor-save'));
    await waitFor(() => expect(api.replaceWorkflowTemplateSteps).toHaveBeenCalledTimes(1));
    expect(payload()[2]).toEqual(['s1', 's2', 's3']);
    expect(api.fetchWorkflowTemplate).toHaveBeenCalledWith('tpl-b');
    const detail = await screen.findByLabelText('process-detail-tpl-b');
    expect(detail).toHaveTextContent('Kroki zapisane.');
    expect(within(detail).getByLabelText('process-steps').querySelectorAll('li')).toHaveLength(2);
    expect(api.updateWorkflowTemplate).not.toHaveBeenCalled(); // metadata never touched by the step editor
  });

  it('409 stale: conflict shown, draft kept, never retried; explicit reload loads the server state', async () => {
    vi.mocked(api.replaceWorkflowTemplateSteps).mockRejectedValue(
      new ApiError("the workflow template's steps changed since they were read; reload it", 409));
    const server: WorkflowTemplateRead = { ...builtin, steps: [step('x1', UNPRICED)] };
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(server);
    await openEditor('tpl-b');
    await pick(SKIM);
    fireEvent.click(screen.getByLabelText('steps-editor-save'));
    const err = await screen.findByLabelText('steps-editor-error');
    expect(err).toHaveTextContent('Lista kroków została zmieniona w innym miejscu. Odśwież dane przed ponowną edycją.');
    expect(rows()).toHaveLength(4); // draft intact
    await new Promise((r) => setTimeout(r, 20));
    expect(api.replaceWorkflowTemplateSteps).toHaveBeenCalledTimes(1); // no automatic retry
    fireEvent.click(screen.getByLabelText('steps-editor-reload'));
    await waitFor(() => expect(rowNames()).toEqual(['Szpachlowanie dodatkowe']));
    expect(screen.queryByLabelText('steps-editor-error')).toBeNull();
    // the next save uses the reloaded server ids
    vi.mocked(api.replaceWorkflowTemplateSteps).mockResolvedValue(server);
    await pick(PRIME);
    fireEvent.click(screen.getByLabelText('steps-editor-save'));
    await waitFor(() => expect(payload()[2]).toEqual(['x1']));
  });

  it('422, archived rejection, missing item and network errors are shown; the draft survives', async () => {
    vi.mocked(api.replaceWorkflowTemplateSteps)
      .mockRejectedValueOnce(new ApiError('Archived price item p9 cannot be added to a workflow template', 422))
      .mockRejectedValueOnce(new ApiError('Price item not found', 404))
      .mockRejectedValueOnce(new ApiError('odd validation', 422))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await openEditor('tpl-b');
    await pick(SKIM);
    const save = () => fireEvent.click(screen.getByLabelText('steps-editor-save'));
    const errText = () => screen.getByLabelText('steps-editor-error').textContent;
    save();
    await waitFor(() => expect(errText()).toContain('Nie można dodać zarchiwizowanej pozycji cennika'));
    save();
    await waitFor(() => expect(errText()).toContain('Jedna z pozycji cennika nie istnieje'));
    save();
    await waitFor(() => expect(errText()).toContain('Nie udało się zapisać kroków.'));
    expect(errText()).toContain('odd validation');
    save();
    await waitFor(() => expect(errText()).toContain('Brak połączenia'));
    expect(rows()).toHaveLength(4);
    expect(screen.queryByLabelText('steps-editor-reload')).toBeNull(); // reload is offered only for 409
  });

  it('prevents double submission', async () => {
    let resolve: (tpl: WorkflowTemplateRead) => void = () => {};
    vi.mocked(api.replaceWorkflowTemplateSteps).mockReturnValue(new Promise((r) => { resolve = r; }));
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue(builtin);
    await openEditor('tpl-b');
    await pick(SKIM);
    const save = screen.getByLabelText('steps-editor-save');
    fireEvent.click(save);
    fireEvent.click(save);
    expect(save).toBeDisabled();
    await act(async () => resolve(builtin));
    expect(api.replaceWorkflowTemplateSteps).toHaveBeenCalledTimes(1);
  });

  it('cancel: clean closes immediately; dirty asks before discarding', async () => {
    await openEditor('tpl-b');
    fireEvent.click(screen.getByLabelText('steps-editor-cancel'));
    expect(await screen.findByLabelText('process-detail-tpl-b')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('process-edit-steps'));
    await pick(SKIM);
    fireEvent.click(screen.getByLabelText('steps-editor-back'));
    const confirm = screen.getByLabelText('steps-editor-discard-confirm');
    fireEvent.click(within(confirm).getByText('Wróć do edycji'));
    expect(rows()).toHaveLength(4);
    fireEvent.click(screen.getByLabelText('steps-editor-cancel'));
    fireEvent.click(screen.getByLabelText('steps-editor-discard-yes'));
    const detail = await screen.findByLabelText('process-detail-tpl-b');
    expect(within(detail).getByLabelText('process-steps').querySelectorAll('li')).toHaveLength(3);
    expect(api.replaceWorkflowTemplateSteps).not.toHaveBeenCalled();
  });
});

describe('note localization (built-in vs owner text)', () => {
  it('canonical note localizes in RU; an edited note shows verbatim in PL and RU; restoring the exact text localizes again', async () => {
    await openEditor('tpl-b');
    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(screen.getByLabelText('steps-editor-note-0')).toHaveTextContent(CLEAN_RU));
    openOptions(0);
    expect(rows()[0]).toHaveTextContent('Стандартная заметка');
    fireEvent.change(screen.getByLabelText('steps-editor-note-input-0'), { target: { value: 'Moja wersja' } });
    expect(screen.getByLabelText('steps-editor-note-0')).toHaveTextContent('Moja wersja');
    fireEvent.change(screen.getByLabelText('steps-editor-note-input-0'), { target: { value: CLEAN_PL } });
    expect(screen.getByLabelText('steps-editor-note-0')).toHaveTextContent(CLEAN_RU);
  });

  it('after saving an edited built-in note the server response (no key) is shown verbatim', async () => {
    vi.mocked(api.replaceWorkflowTemplateSteps).mockResolvedValue(builtin);
    vi.mocked(api.fetchWorkflowTemplate).mockResolvedValue({ ...builtin, steps: [step('n1', PRIME, { note: 'Moja wersja', note_key: null })] });
    await openEditor('tpl-b');
    openOptions(0);
    fireEvent.change(screen.getByLabelText('steps-editor-note-input-0'), { target: { value: 'Moja wersja' } });
    fireEvent.click(screen.getByLabelText('steps-editor-save'));
    await screen.findByLabelText('process-detail-tpl-b');
    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(screen.getByLabelText('process-step-note-n1')).toHaveTextContent('Moja wersja'));
  });

  it('custom template notes are verbatim in PL and RU', async () => {
    await openEditor('tpl-c');
    expect(screen.getByLabelText('steps-editor-note-0')).toHaveTextContent('Moja notatka');
    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(screen.getByLabelText('steps-editor-save')).toHaveTextContent('Сохранить шаги'));
    expect(screen.getByLabelText('steps-editor-note-0')).toHaveTextContent('Moja notatka');
  });
});

describe('Russian UI', () => {
  it('editor controls are Russian', async () => {
    localStorage.setItem('locale', 'ru');
    render(<I18nProvider><WorkflowTemplateManager /></I18nProvider>);
    fireEvent.click(await screen.findByLabelText('process-card-tpl-b'));
    expect(screen.getByLabelText('process-edit-steps')).toHaveTextContent('Редактировать шаги');
    fireEvent.click(screen.getByLabelText('process-edit-steps'));
    expect(screen.getByLabelText('steps-editor-add')).toHaveTextContent('+ Добавить шаг');
    openOptions(1);
    expect(screen.getByLabelText('steps-editor-up-1')).toHaveTextContent('Вверх');
    expect(screen.getByLabelText('steps-editor-down-1')).toHaveTextContent('Вниз');
    expect(screen.getByLabelText('steps-editor-remove-1')).toHaveTextContent('Удалить шаг');
    expect(screen.getByLabelText('steps-editor-required-1')).toHaveTextContent('Обязательный');
    expect(screen.getByLabelText('steps-editor-save')).toHaveTextContent('Сохранить шаги');
  });
});
