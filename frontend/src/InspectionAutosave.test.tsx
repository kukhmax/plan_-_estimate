/** UX walk A4: the answers of an inspection are saved by themselves -- a phone call or a minimised Telegram must not lose them. */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as checklistsApi from './api/checklists';
import * as inspectionsApi from './api/inspections';
import { InspectionFlow } from './components/InspectionFlow';
import { I18nProvider } from './hooks/useI18n';
import type { ChecklistTemplate } from './types/checklist';

vi.mock('./api/checklists', () => ({ fetchChecklistTemplates: vi.fn(), fetchChecklistTemplate: vi.fn() }));
vi.mock('./api/workPlans', async (orig) => ({ ...(await orig<typeof import('./api/workPlans')>()), fetchSurfaceWorkPlan: vi.fn() }));
vi.mock('./api/inspections', () => ({
  fetchInspections: vi.fn(), createInspection: vi.fn(), fetchInspection: vi.fn(), updateInspection: vi.fn(),
  fetchInspectionAnswers: vi.fn(), putInspectionAnswers: vi.fn(), completeInspection: vi.fn(),
  reopenInspection: vi.fn(), archiveInspection: vi.fn(), restoreInspection: vi.fn(), fetchInspectionFindings: vi.fn(),
}));

const question = (id: string, key: string, answer_type: 'BOOLEAN' | 'NUMBER' = 'BOOLEAN') => ({
  id, position: 0, key, text_key: `checklist.question.${key}`, hint_key: null, unit_key: null, answer_type, finding_key: null, options: [],
});
const TEMPLATE: ChecklistTemplate = {
  id: 'tpl', code: 'substrate-CONCRETE', version: 1, substrate: 'CONCRETE', title_key: 'checklist.template.x', active: true, created_at: '', updated_at: '',
  sections: [{ id: 'sec', key: 'general_conditions', position: 0, title_key: 'checklist.section.general_conditions', description_key: null,
    questions: [question('q1', 'cracks_present'), question('q2', 'unevenness_mm', 'NUMBER')] }],
};
const DETAIL = (status: 'DRAFT' | 'COMPLETED' = 'DRAFT') => ({
  id: 'ins-1', room_id: 'r', template_id: 'tpl', substrate: 'CONCRETE', quality_target: 'S3', status, surface_id: 'w1', plane: null,
  notes: null, completed_at: null, is_archived: false, created_at: '', updated_at: '', answers: [],
});

function show() {
  return render(
    <I18nProvider>
      <InspectionFlow projectId="p" roomId="r" target={{ kind: 'surface', surfaceId: 'w1', surfaceName: 'Ściana 1' }} inspectionId="ins-1" onExit={vi.fn()} onCreated={vi.fn()} />
    </I18nProvider>,
  );
}

async function opened() {
  show();
  await act(async () => { await vi.advanceTimersByTimeAsync(50); });
  await act(async () => { await vi.advanceTimersByTimeAsync(50); });
}

describe('autosave of the answers (UX walk A4)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(checklistsApi.fetchChecklistTemplate).mockResolvedValue(TEMPLATE);
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue(DETAIL() as never);
    vi.mocked(inspectionsApi.putInspectionAnswers).mockResolvedValue({ items: [], total: 0 } as never);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('saves a second after the last tap, with no button, and says so', async () => {
    await opened();
    fireEvent.click(screen.getByLabelText('Tak'));
    expect(inspectionsApi.putInspectionAnswers).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(inspectionsApi.putInspectionAnswers).toHaveBeenCalledTimes(1);
    expect(inspectionsApi.putInspectionAnswers).toHaveBeenCalledWith('p', 'r', 'ins-1', { answers: [expect.objectContaining({ question_id: 'q1', value_bool: true })] });
    expect(screen.getByLabelText('inspection-autosave')).toHaveTextContent('Odpowiedzi zapisane automatycznie.');
  });

  it('opening the inspection saves nothing; several quick taps make one save', async () => {
    await opened();
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(inspectionsApi.putInspectionAnswers).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('Tak'));
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    fireEvent.click(screen.getByLabelText('Nie'));
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(inspectionsApi.putInspectionAnswers).toHaveBeenCalledTimes(1);
    expect(vi.mocked(inspectionsApi.putInspectionAnswers).mock.calls[0][3]).toEqual({ answers: [expect.objectContaining({ question_id: 'q1', value_bool: false })] });
  });

  it('saves at once when Telegram is minimised (the page is hidden) and when the screen is left', async () => {
    await opened();
    fireEvent.click(screen.getByLabelText('Tak'));
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
    expect(inspectionsApi.putInspectionAnswers).toHaveBeenCalledTimes(1);
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
  });

  it('leaving the screen right after a tap still saves it', async () => {
    const view = await (async () => { const v = show(); await act(async () => { await vi.advanceTimersByTimeAsync(100); }); return v; })();
    fireEvent.click(screen.getByLabelText('Tak'));
    view.unmount();
    expect(inspectionsApi.putInspectionAnswers).toHaveBeenCalledTimes(1);
  });

  it('a number with too many decimals waits for the correction; a failure is told', async () => {
    await opened();
    const field = screen.getByLabelText(/Nierówności|unevenness/i, { selector: 'input' });
    fireEvent.change(field, { target: { value: '1,23456' } });
    fireEvent.blur(field);
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(inspectionsApi.putInspectionAnswers).not.toHaveBeenCalled();
    vi.mocked(inspectionsApi.putInspectionAnswers).mockRejectedValue(new Error('down'));
    fireEvent.change(field, { target: { value: '4' } });
    fireEvent.blur(field);
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(inspectionsApi.putInspectionAnswers).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('inspection-autosave')).toHaveTextContent('Nie udało się zapisać automatycznie');
  });

  it('a completed inspection is never saved by itself', async () => {
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue(DETAIL('COMPLETED') as never);
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({ items: [], total: 0 } as never);
    const view = show();
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    view.unmount();
    expect(inspectionsApi.putInspectionAnswers).not.toHaveBeenCalled();
  });
});
