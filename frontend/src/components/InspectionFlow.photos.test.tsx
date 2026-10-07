import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as checklistsApi from '../api/checklists';
import * as communicationsApi from '../api/communications';
import * as inspectionsApi from '../api/inspections';
import { ApiError } from '../api/http';
import * as risksApi from '../api/risks';
import * as workRecommendationsApi from '../api/workRecommendations';
import * as workPlansApi from '../api/workPlans';
import { ProjectPhotosContext, ProjectPhotosValue, photoKey } from '../hooks/ProjectPhotosContext';
import { I18nProvider } from '../hooks/useI18n';
import { ChecklistTemplate } from '../types/checklist';
import { Inspection, InspectionDetail, InspectionFinding, InspectionTarget } from '../types/inspection';
import { PhotoCounts } from '../types/photo';
import { InspectionFlow } from './InspectionFlow';

// Photo evidence in the inspection (Stage 14F.3): the header button, one button per checklist question, one per ACTIVE finding.
// The section itself is mocked: its own behaviour (listing, uploading, counts) is covered by PhotoSection.test.tsx.

vi.mock('../api/checklists', () => ({ fetchChecklistTemplates: vi.fn(), fetchChecklistTemplate: vi.fn() }));
vi.mock('../api/inspections', () => ({
  fetchInspection: vi.fn(),
  createInspection: vi.fn(),
  putInspectionAnswers: vi.fn(),
  completeInspection: vi.fn(),
  reopenInspection: vi.fn(),
  fetchInspectionFindings: vi.fn(),
}));
vi.mock('../api/risks', () => ({ evaluateRisks: vi.fn(), fetchRisks: vi.fn(), fetchRiskDetail: vi.fn() }));
vi.mock('../api/communications', () => ({ fetchCommunications: vi.fn(), evaluateCommunications: vi.fn(), fetchCommunicationDetail: vi.fn() }));
vi.mock('../api/workRecommendations', () => ({
  fetchWorkRecommendations: vi.fn(),
  evaluateWorkRecommendations: vi.fn(),
  dismissWorkRecommendation: vi.fn(),
  reconsiderWorkRecommendation: vi.fn(),
  acceptWorkRecommendation: vi.fn(),
}));
vi.mock('../api/priceItems', () => ({ fetchPriceItems: vi.fn() }));
vi.mock('../api/workPlans', () => ({ fetchSurfaceWorkPlan: vi.fn() }));

const sectionProps = vi.fn();
vi.mock('./PhotoSection', () => ({
  PhotoSection: (props: Record<string, unknown>) => {
    sectionProps(props);
    return <div data-testid="photo-section" />;
  },
}));

const template: ChecklistTemplate = {
  id: 'tpl-1',
  code: 'substrate-concrete',
  version: 1,
  substrate: 'CONCRETE',
  title_key: 'checklist.template.concrete.title',
  active: true,
  sections: [
    {
      id: 'sec-1',
      key: 'general_conditions',
      position: 0,
      title_key: 'checklist.section.general_conditions',
      description_key: null,
      questions: [
        {
          id: 'q-bool',
          position: 0,
          key: 'cracks_present',
          text_key: 'checklist.question.cracks_present',
          hint_key: 'checklist.hint.cracks_present',
          unit_key: null,
          answer_type: 'BOOLEAN',
          finding_key: 'CRACK',
          options: [],
        },
        {
          id: 'q-number',
          position: 1,
          key: 'unevenness_mm',
          text_key: 'checklist.question.unevenness_mm',
          hint_key: 'checklist.hint.unevenness_mm',
          unit_key: 'mm',
          answer_type: 'NUMBER',
          finding_key: 'UNEVENNESS',
          options: [],
        },
        {
          id: 'q-single',
          position: 2,
          key: 'substrate_condition',
          text_key: 'checklist.question.substrate_condition',
          hint_key: null,
          unit_key: null,
          answer_type: 'SINGLE_CHOICE',
          finding_key: null,
          options: [
            {
              id: 'o-solid',
              position: 0,
              key: 'SOLID',
              label_key: 'checklist.option.substrate_solid',
              finding_key: null,
            },
            {
              id: 'o-loose',
              position: 1,
              key: 'LOOSE',
              label_key: 'checklist.option.substrate_loose',
              finding_key: 'LOOSE_SUBSTRATE',
            },
          ],
        },
        {
          id: 'q-multi',
          position: 3,
          key: 'present_defects',
          text_key: 'checklist.question.present_defects',
          hint_key: null,
          unit_key: null,
          answer_type: 'MULTI_CHOICE',
          finding_key: null,
          options: [
            {
              id: 'o-delam',
              position: 0,
              key: 'DELAMINATION',
              label_key: 'checklist.option.defect_delamination',
              finding_key: 'DELAMINATION',
            },
            {
              id: 'o-blow',
              position: 1,
              key: 'BLOW_HOLES',
              label_key: 'checklist.option.defect_blow_holes',
              finding_key: 'BLOW_HOLES',
            },
          ],
        },
        {
          id: 'q-text',
          position: 4,
          key: 'notes',
          text_key: 'checklist.question.notes',
          hint_key: null,
          unit_key: null,
          answer_type: 'TEXT',
          finding_key: null,
          options: [],
        },
      ],
    },
  ],
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};

const draftInspection: Inspection = {
  id: 'ins-1',
  room_id: 'room-1',
  surface_id: null,
  plane: null,
  template_id: template.id,
  substrate: 'CONCRETE',
  quality_target: 'S2',
  status: 'DRAFT',
  notes: null,
  completed_at: null,
  is_archived: false,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
};


const COUNTS: PhotoCounts = {
  project: 0,
  rooms: {},
  surfaces: {},
  openings: {},
  room_totals: {},
  inspections: { 'ins-1': 7 },
  findings: { 'f-active': 1, 'f-old': 2 },
  lineages: { 'lineage-1': 3 },
  questions: { 'ins-1': { 'q-bool': 2, 'q-number': 1 } },
};

function photos(over: Partial<ProjectPhotosValue> = {}, expanded: string[] = []): ProjectPhotosValue {
  return {
    projectId: 'proj-1',
    counts: COUNTS,
    isExpanded: (key) => expanded.includes(key),
    toggle: vi.fn(),
    adjust: vi.fn(),
    resolveLocation: vi.fn(() => 'resolved'),
    ensureLocations: vi.fn(),
    ...over,
  };
}

function renderFlow(options: { inspectionId?: string | null; target?: InspectionTarget; provided?: ProjectPhotosValue | null } = {}) {
  const provided = options.provided === undefined ? photos() : options.provided;
  return render(
    <I18nProvider>
      <ProjectPhotosContext.Provider value={provided}>
        <InspectionFlow
          projectId="proj-1"
          roomId="room-1"
          target={options.target ?? { kind: 'room' }}
          inspectionId={options.inspectionId === undefined ? 'ins-1' : options.inspectionId}
          onExit={vi.fn()}
          onCreated={vi.fn()}
        />
      </ProjectPhotosContext.Provider>
    </I18nProvider>,
  );
}

const completedDetail = (over: Partial<InspectionDetail> = {}): InspectionDetail => ({
  ...draftInspection,
  status: 'COMPLETED',
  completed_at: '2026-09-09T12:00:00Z',
  answers: [],
  ...over,
});

const finding = (over: Partial<InspectionFinding>): InspectionFinding => ({
  id: 'f-active',
  finding_key: 'CRACK',
  label_key: 'checklist.question.cracks_present',
  value_snapshot: { bool: true },
  is_active: true,
  resolved_at: null,
  position: 0,
  answer_id: 'a-bool',
  question_id: 'q-bool',
  lineage_id: 'lineage-1',
  created_at: '2026-09-09T12:00:00Z',
  updated_at: '2026-09-09T12:00:00Z',
  ...over,
});

const photoButtons = () => screen.queryAllByRole('button', { name: /^Zdjęcia: \d+$/ });

beforeEach(() => {
  vi.clearAllMocks();
  sectionProps.mockClear();
  vi.mocked(checklistsApi.fetchChecklistTemplates).mockResolvedValue({ items: [template], total: 1 });
  vi.mocked(checklistsApi.fetchChecklistTemplate).mockResolvedValue(template);
  vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue({ ...draftInspection, answers: [] });
  vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(risksApi.fetchRiskDetail).mockRejectedValue(new Error('not found'));
  vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(communicationsApi.fetchCommunicationDetail).mockRejectedValue(new Error('not found'));
  vi.mocked(workRecommendationsApi.fetchWorkRecommendations).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockRejectedValue(new ApiError('Surface work plan not found', 404));
});

describe('InspectionFlow — photo evidence', () => {
  it('shows no photo controls without a project photo context (existing screens)', async () => {
    renderFlow({ provided: null });
    await screen.findAllByRole('group');
    expect(photoButtons()).toHaveLength(0);
    expect(screen.queryByTestId('photo-section')).toBeNull();
  });

  it('puts a button in the header and one on every question of a saved inspection, each with its own count', async () => {
    renderFlow();
    await screen.findAllByRole('group');
    const names = photoButtons().map((b) => b.getAttribute('aria-label'));
    // header (the whole inspection: 7), then the questions in order: bool 2, number 1, single 0, multi 0, text 0
    expect(names).toEqual(['Zdjęcia: 7', 'Zdjęcia: 2', 'Zdjęcia: 1', 'Zdjęcia: 0', 'Zdjęcia: 0', 'Zdjęcia: 0']);
  });

  it('a question button toggles its own section by an inspection + question key', async () => {
    const provided = photos();
    renderFlow({ provided });
    await screen.findAllByRole('group');
    fireEvent.click(photoButtons()[1]);
    expect(provided.toggle).toHaveBeenCalledWith(photoKey('INSPECTION', 'ins-1', 'q-bool'));
    fireEvent.click(photoButtons()[0]);
    expect(provided.toggle).toHaveBeenCalledWith(photoKey('INSPECTION', 'ins-1'));
  });

  it('an open question panel is the question\'s section: inspection target, its question, a caption naming the question', async () => {
    renderFlow({ provided: photos({}, [photoKey('INSPECTION', 'ins-1', 'q-number')]) });
    await screen.findAllByRole('group');
    const props = sectionProps.mock.calls.map((call) => call[0]).find((p) => p.questionId === 'q-number');
    expect(props).toMatchObject({ context: 'INSPECTION', targetId: 'ins-1', allowUpload: true });
    expect(props?.locationLabel).toMatch(/^Badania podłoża → .+ → .+/);
    expect(screen.getAllByTestId('photo-section')).toHaveLength(1);
  });

  it('the header panel lists the whole inspection and names the question of each photo in its caption', async () => {
    renderFlow({ provided: photos({}, [photoKey('INSPECTION', 'ins-1')]) });
    await screen.findAllByRole('group');
    const props = sectionProps.mock.calls.map((call) => call[0]).find((p) => p.questionId === undefined && p.context === 'INSPECTION');
    expect(props).toMatchObject({ targetId: 'ins-1', allowUpload: true });
    const label = props?.locationLabel as (attachment: { question_id: string | null }) => string;
    const general = label({ question_id: null });
    const forQuestion = label({ question_id: 'q-bool' });
    expect(forQuestion.startsWith(general + ' → ')).toBe(true); // the question is one segment longer
    expect(forQuestion).toContain('pęknięcia');
  });

  it('has no photo controls while the wizard still asks for the substrate (nothing saved to attach to)', async () => {
    renderFlow({ inspectionId: null });
    await screen.findAllByRole('button');
    expect(photoButtons()).toHaveLength(0);
  });

  it('has none for an archived inspection', async () => {
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue({ ...draftInspection, is_archived: true, answers: [] });
    renderFlow();
    await screen.findAllByRole('group');
    expect(photoButtons()).toHaveLength(0);
  });

  it('the review step of an unfinished inspection keeps the question buttons', async () => {
    renderFlow();
    await screen.findAllByRole('group');
    fireEvent.click(screen.getByRole('button', { name: 'Przejrzyj i zakończ' }));
    await waitFor(() => expect(photoButtons().length).toBeGreaterThan(1));
    expect(photoButtons()[0]).toHaveAttribute('aria-label', 'Zdjęcia: 7');
  });

  it('after completion every ACTIVE finding has a button counting its whole lineage; resolved ones have none', async () => {
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue(completedDetail());
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({
      items: [finding({}), finding({ id: 'f-old', is_active: false, resolved_at: '2026-09-09T11:00:00Z' })],
      total: 2,
    });
    renderFlow();
    const list = await screen.findByRole('list');
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getAllByRole('button', { name: /^Zdjęcia: \d+$/ })).toHaveLength(1);
    expect(within(list).getByRole('button', { name: 'Zdjęcia: 3' })).toBeInTheDocument(); // lineage-1: both rows' photos
  });

  it('a finding panel is a FINDING section of that row with its lineage', async () => {
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue(completedDetail());
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({ items: [finding({})], total: 1 });
    renderFlow({ provided: photos({}, [photoKey('FINDING', 'f-active')]) });
    await screen.findByRole('list');
    const props = sectionProps.mock.calls.map((call) => call[0]).find((p) => p.context === 'FINDING');
    expect(props).toMatchObject({ targetId: 'f-active', lineageId: 'lineage-1', allowUpload: true });
    expect(props?.locationLabel).toMatch(/^Badania podłoża → .+ → .+/);
  });

  it('the finding row keeps its text and wraps long labels next to the button', async () => {
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue(completedDetail());
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({ items: [finding({})], total: 1 });
    renderFlow();
    const row = (await screen.findByRole('list')).querySelector('li') as HTMLElement;
    expect(row.textContent).toContain('pęknięcia');
    expect(row.querySelector('span.break-words')).not.toBeNull();
  });
});
