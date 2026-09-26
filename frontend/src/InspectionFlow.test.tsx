/**
 * Stage 13F-PRE FIX.2 — inspection wizard target rules.
 * - FLOOR never asks for an S/Q finishing class (it is a wall/ceiling concept).
 * - "Pomiń" on the quality step is a real transition: it starts the
 *   inspection without a class and shows the checklist (never a dead click,
 *   never a 0/0 screen).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as checklistsApi from './api/checklists';
import * as inspectionsApi from './api/inspections';
import * as workPlansApi from './api/workPlans';
import { InspectionFlow } from './components/InspectionFlow';
import { I18nProvider } from './hooks/useI18n';
import { ChecklistTemplate } from './types/checklist';
import { Inspection, InspectionTarget } from './types/inspection';

vi.mock('./api/checklists', () => ({ fetchChecklistTemplates: vi.fn(), fetchChecklistTemplate: vi.fn() }));
vi.mock('./api/workPlans', async (orig) => ({
  ...(await orig<typeof import('./api/workPlans')>()),
  fetchSurfaceWorkPlan: vi.fn(),
}));
vi.mock('./api/inspections', () => ({
  fetchInspections: vi.fn(), createInspection: vi.fn(), fetchInspection: vi.fn(), updateInspection: vi.fn(),
  fetchInspectionAnswers: vi.fn(), putInspectionAnswers: vi.fn(), completeInspection: vi.fn(),
  reopenInspection: vi.fn(), archiveInspection: vi.fn(), restoreInspection: vi.fn(), fetchInspectionFindings: vi.fn(),
}));

const question = (id: string, key: string) => ({
  id, position: 0, key, text_key: `checklist.question.${key}`, hint_key: null, unit_key: null,
  answer_type: 'BOOLEAN' as const, finding_key: null, options: [],
});

const template = (substrate: 'CONCRETE' | 'GYPSUM_BOARD'): ChecklistTemplate => ({
  id: `tpl-${substrate}`, code: `substrate-${substrate}`, version: 1, substrate,
  title_key: 'checklist.template.x', active: true, created_at: '', updated_at: '',
  sections: [{
    id: 'sec', key: 'general_conditions', position: 0, title_key: 'checklist.section.general_conditions',
    description_key: null, questions: [question('q1', 'cracks_present'), question('q2', 'moisture_high')],
  }],
});

const created = (target: InspectionTarget, substrate: 'CONCRETE' | 'GYPSUM_BOARD'): Inspection => ({
  id: 'ins-new', room_id: 'r', template_id: `tpl-${substrate}`, substrate, quality_target: null, status: 'DRAFT',
  surface_id: target.kind === 'surface' ? target.surfaceId : null,
  plane: target.kind === 'plane' ? target.plane : null,
  notes: null, completed_at: null, is_archived: false, created_at: '', updated_at: '',
});

function renderFlow(target: InspectionTarget) {
  return render(
    <I18nProvider>
      <InspectionFlow projectId="p" roomId="r" target={target} inspectionId={null} onExit={vi.fn()} onCreated={vi.fn()} />
    </I18nProvider>,
  );
}

const QUALITY = ['S1', 'S2', 'S3', 'S4', 'Q1', 'Q2', 'Q3', 'Q4'];

describe('InspectionFlow target rules (13F-PRE FIX.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(checklistsApi.fetchChecklistTemplates).mockImplementation(async (substrate) => ({
      items: [template((substrate as 'CONCRETE' | 'GYPSUM_BOARD') ?? 'CONCRETE')], total: 1,
    }));
    vi.mocked(checklistsApi.fetchChecklistTemplate).mockImplementation(async (id) =>
      template(id === 'tpl-GYPSUM_BOARD' ? 'GYPSUM_BOARD' : 'CONCRETE'));
    vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValue(new Error('404'));
  });

  it('FLOOR never shows S1-S4 / Q1-Q4: substrate -> checklist with real questions', async () => {
    const target: InspectionTarget = { kind: 'plane', plane: 'FLOOR' };
    vi.mocked(inspectionsApi.createInspection).mockResolvedValue(created(target, 'CONCRETE'));
    renderFlow(target);
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await waitFor(() => expect(inspectionsApi.createInspection).toHaveBeenCalledWith('p', 'r', expect.objectContaining({
      plane: 'FLOOR', substrate: 'CONCRETE', quality_target: null,
    })));
    expect(await screen.findByText('Odpowiedzi: 0 / 2')).toBeInTheDocument();
    expect(screen.queryByText('Klasa jakości')).not.toBeInTheDocument();
    for (const level of QUALITY) expect(screen.queryByLabelText(level)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Pomiń')).not.toBeInTheDocument();
  });

  it('CEILING keeps the substrate-scoped quality step (S-scale for concrete, Q-scale for GK)', async () => {
    renderFlow({ kind: 'plane', plane: 'CEILING' });
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    expect(['S1', 'S2', 'S3', 'S4'].every((l) => screen.queryByLabelText(l))).toBe(true);
    expect(screen.queryByLabelText('Q1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Wstecz'));
    fireEvent.click(await screen.findByLabelText('Płyta g-k'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    expect(screen.getByLabelText('Q3')).toBeInTheDocument();
    expect(screen.queryByLabelText('S3')).not.toBeInTheDocument();
  });

  for (const target of [
    { kind: 'plane', plane: 'CEILING' } as InspectionTarget,
    { kind: 'surface', surfaceId: 'wall-1', surfaceName: 'Ściana 1' } as InspectionTarget,
  ]) {
    const name = target.kind === 'plane' ? 'CEILING' : 'WALL';
    it(`${name}: "Pomiń" starts the inspection without a class and shows the checklist`, async () => {
      vi.mocked(inspectionsApi.createInspection).mockResolvedValue(created(target, 'CONCRETE'));
      renderFlow(target);
      fireEvent.click(await screen.findByLabelText('Beton'));
      fireEvent.click(screen.getByLabelText('Dalej'));
      await screen.findByText('Klasa jakości');
      fireEvent.click(screen.getByLabelText('S2')); // a class picked first is discarded by Skip
      fireEvent.click(screen.getByLabelText('Pomiń'));
      await waitFor(() => expect(inspectionsApi.createInspection).toHaveBeenCalledTimes(1));
      expect(vi.mocked(inspectionsApi.createInspection).mock.calls[0][2]).toMatchObject({
        substrate: 'CONCRETE', quality_target: null,
      });
      expect(await screen.findByText('Odpowiedzi: 0 / 2')).toBeInTheDocument();
      expect(screen.queryByText('Klasa jakości')).not.toBeInTheDocument();
    });
  }

  it('choosing a class and pressing start still records it (unchanged path)', async () => {
    const target: InspectionTarget = { kind: 'plane', plane: 'CEILING' };
    vi.mocked(inspectionsApi.createInspection).mockResolvedValue({ ...created(target, 'CONCRETE'), quality_target: 'S3' });
    renderFlow(target);
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    fireEvent.click(await screen.findByLabelText('S3'));
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await waitFor(() => expect(vi.mocked(inspectionsApi.createInspection).mock.calls[0][2]).toMatchObject({ quality_target: 'S3' }));
    expect(await screen.findByText('Odpowiedzi: 0 / 2')).toBeInTheDocument();
  });
});
