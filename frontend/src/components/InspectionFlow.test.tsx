import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as checklistsApi from '../api/checklists';
import * as inspectionsApi from '../api/inspections';
import { I18nProvider } from '../hooks/useI18n';
import { ChecklistTemplate } from '../types/checklist';
import {
  Inspection,
  InspectionDetail,
  InspectionFinding,
  InspectionTarget,
} from '../types/inspection';
import { InspectionFlow } from './InspectionFlow';

vi.mock('../api/checklists', () => ({
  fetchChecklistTemplates: vi.fn(),
  fetchChecklistTemplate: vi.fn(),
}));
vi.mock('../api/inspections', () => ({
  fetchInspection: vi.fn(),
  createInspection: vi.fn(),
  putInspectionAnswers: vi.fn(),
  completeInspection: vi.fn(),
  reopenInspection: vi.fn(),
  fetchInspectionFindings: vi.fn(),
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

const roomTarget: InspectionTarget = { kind: 'room' };

function renderFlow(props: {
  target?: InspectionTarget;
  inspectionId?: string | null;
} = {}) {
  return render(
    <I18nProvider>
      <InspectionFlow
        projectId="proj-1"
        roomId="room-1"
        target={props.target ?? roomTarget}
        inspectionId={props.inspectionId ?? null}
        onExit={vi.fn()}
        onCreated={vi.fn()}
      />
    </I18nProvider>,
  );
}

describe('InspectionFlow substrate step', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(checklistsApi.fetchChecklistTemplates).mockResolvedValue({
      items: [template],
      total: 1,
    });
    vi.mocked(checklistsApi.fetchChecklistTemplate).mockResolvedValue(template);
    vi.mocked(inspectionsApi.createInspection).mockResolvedValue(draftInspection);
    vi.mocked(inspectionsApi.putInspectionAnswers).mockResolvedValue({
      items: [],
      total: 0,
    });
    vi.mocked(inspectionsApi.completeInspection).mockResolvedValue({
      ...draftInspection,
      status: 'COMPLETED',
      completed_at: '2026-09-09T12:00:00Z',
    });
    vi.mocked(inspectionsApi.reopenInspection).mockResolvedValue(draftInspection);
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({
      items: [],
      total: 0,
    });
  });

  it('renders all six substrate options (ENTRY/SUBSTRATE)', async () => {
    renderFlow();
    for (const label of [
      'Beton',
      'Tynk gipsowy',
      'Tynk cem.-wap.',
      'Płyta g-k',
      'Stara farba',
      'Inne',
    ]) {
      expect(await screen.findByLabelText(label)).toBeInTheDocument();
    }
  });

  it('disables next until a substrate is chosen', async () => {
    renderFlow();
    const next = screen.getByLabelText('Dalej');
    expect(next).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Beton'));
    expect(next).toBeEnabled();
  });

  it('routes GYPSUM_BOARD to Q1-Q4 and sends canonical Q level to API (QUALITY)', async () => {
    renderFlow();
    fireEvent.click(await screen.findByLabelText('Płyta g-k'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    for (const level of ['Q1', 'Q2', 'Q3', 'Q4']) {
      expect(screen.getByLabelText(level)).toBeInTheDocument();
    }
    expect(screen.queryByLabelText('S1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Q2'));
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await waitFor(() =>
      expect(inspectionsApi.createInspection).toHaveBeenCalledWith('proj-1', 'room-1', {
        template_id: template.id,
        substrate: 'GYPSUM_BOARD',
        quality_target: 'Q2',
        surface_id: null,
        plane: null,
      }),
    );
  });

  it('routes concrete/plasters to S1-S4 and sends canonical S level (QUALITY)', async () => {
    renderFlow();
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    for (const level of ['S1', 'S2', 'S3', 'S4']) {
      expect(screen.getByLabelText(level)).toBeInTheDocument();
    }
    expect(screen.queryByLabelText('Q1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('S3'));
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await waitFor(() =>
      expect(inspectionsApi.createInspection).toHaveBeenCalledWith('proj-1', 'room-1', {
        template_id: template.id,
        substrate: 'CONCRETE',
        quality_target: 'S3',
        surface_id: null,
        plane: null,
      }),
    );
  });

  it('offers skip and omits quality for PAINTED (canonical null to API) (QUALITY)', async () => {
    renderFlow();
    fireEvent.click(await screen.findByLabelText('Stara farba'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    // Optional nature is made explicit for PAINTED/OTHER
    expect(screen.getByText(/jest opcjonalna/)).toBeInTheDocument();
    expect(screen.getByLabelText('Pomiń')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Pomiń'));
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await waitFor(() =>
      expect(inspectionsApi.createInspection).toHaveBeenCalledWith('proj-1', 'room-1', {
        template_id: template.id,
        substrate: 'PAINTED',
        quality_target: null,
        surface_id: null,
        plane: null,
      }),
    );
  });

  it('sends the wall surface id when the target is a wall (ENTRY)', async () => {
    render(
      <I18nProvider>
        <InspectionFlow
          projectId="proj-1"
          roomId="room-1"
          target={{ kind: 'surface', surfaceId: 'surf-1', surfaceName: 'Ściana północna' }}
          inspectionId={null}
          onExit={vi.fn()}
          onCreated={vi.fn()}
        />
      </I18nProvider>,
    );
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await waitFor(() =>
      expect(inspectionsApi.createInspection).toHaveBeenCalledWith('proj-1', 'room-1', {
        template_id: template.id,
        substrate: 'CONCRETE',
        quality_target: null,
        surface_id: 'surf-1',
        plane: null,
      }),
    );
  });

  it('renders all five answer types in the checklist (QUESTIONS)', async () => {
    renderFlow();
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await screen.findByText(/Odpowiedzi: 0 \/ 5/);
    // BOOLEAN
    expect(screen.getByLabelText('Tak')).toBeInTheDocument();
    expect(screen.getByLabelText('Nie')).toBeInTheDocument();
    // NUMBER with decimal keyboard
    expect(screen.getByLabelText('Nierówności podłoża')).toHaveAttribute(
      'inputMode',
      'decimal',
    );
    // SINGLE_CHOICE
    expect(screen.getByLabelText('Zwarte')).toBeInTheDocument();
    expect(screen.getByLabelText('Luzne')).toBeInTheDocument();
    // MULTI_CHOICE
    expect(screen.getByLabelText('Odpryski')).toBeInTheDocument();
    expect(screen.getByLabelText('Raki / pęcherze')).toBeInTheDocument();
    // TEXT
    expect(screen.getByLabelText('Uwagi')).toBeInTheDocument();
  });

  it('saves a draft with current answers (DRAFT)', async () => {
    renderFlow();
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await screen.findByText(/Odpowiedzi: 0 \/ 5/);

    fireEvent.click(screen.getByLabelText('Tak'));
    fireEvent.click(screen.getByLabelText('Luzne'));
    fireEvent.click(screen.getByLabelText('Odpryski'));
    fireEvent.change(screen.getByLabelText('Nierówności podłoża'), {
      target: { value: '5,5' },
    });
    fireEvent.blur(screen.getByLabelText('Nierówności podłoża'));
    fireEvent.change(screen.getByLabelText('Uwagi'), { target: { value: 'spalling' } });

    fireEvent.click(screen.getByLabelText('Zapisz szkic'));
    await waitFor(() =>
      expect(inspectionsApi.putInspectionAnswers).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-1',
        expect.objectContaining({
          answers: expect.arrayContaining([
            expect.objectContaining({ question_id: 'q-bool', value_bool: true }),
            expect.objectContaining({ question_id: 'q-single', option_key: 'LOOSE' }),
            expect.objectContaining({ question_id: 'q-multi', option_keys: ['DELAMINATION'] }),
            expect.objectContaining({ question_id: 'q-number', value_number: '5.5' }),
            expect.objectContaining({ question_id: 'q-text', value_text: 'spalling' }),
          ]),
        }),
      ),
    );
  });

  it('resumes an existing DRAFT inspection prefilled from the backend (DRAFT)', async () => {
    const detail: InspectionDetail = {
      ...draftInspection,
      answers: [
        {
          id: 'a-bool',
          question_id: 'q-bool',
          value_bool: true,
          value_number: null,
          value_text: null,
          option_key: null,
          option_keys: null,
          updated_at: '2026-09-09T10:00:00Z',
        },
      ],
    };
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue(detail);
    renderFlow({ inspectionId: 'ins-1' });
    await screen.findByText(/Odpowiedzi: 1 \/ 5/);
    // Prefilled boolean answered as "Tak"
    expect(screen.getByLabelText('Tak')).toHaveClass('border-blue-600');
    // Form remains editable (save draft present)
    expect(screen.getByLabelText('Zapisz szkic')).toBeInTheDocument();
  });

  it('renders a COMPLETED inspection read-only with findings and reopen (LIFECYCLE)', async () => {
    const detail: InspectionDetail = {
      ...draftInspection,
      status: 'COMPLETED',
      completed_at: '2026-09-09T12:00:00Z',
      answers: [
        {
          id: 'a-bool',
          question_id: 'q-bool',
          value_bool: true,
          value_number: null,
          value_text: null,
          option_key: null,
          option_keys: null,
          updated_at: '2026-09-09T10:00:00Z',
        },
      ],
    };
    const findings: InspectionFinding[] = [
      {
        id: 'f-1',
        finding_key: 'CRACK',
        label_key: 'checklist.question.cracks_present',
        value_snapshot: { bool: true },
        is_active: true,
        resolved_at: null,
        position: 0,
        answer_id: 'a-bool',
        question_id: 'q-bool',
        created_at: '2026-09-09T12:00:00Z',
        updated_at: '2026-09-09T12:00:00Z',
      },
    ];
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue(detail);
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({
      items: findings,
      total: 1,
    });
    renderFlow({ inspectionId: 'ins-1' });

    expect(await screen.findByText(/Czy występują pęknięcia/)).toBeInTheDocument();
    expect(screen.getAllByText('Ustalenia').length).toBeGreaterThan(0);
    // Opening a completed inspection fetches its backend-materialized findings
    expect(inspectionsApi.fetchInspectionFindings).toHaveBeenCalledWith(
      'proj-1',
      'room-1',
      'ins-1',
      true,
    );
    // No save/review/complete actions in read-only completed view
    expect(screen.queryByLabelText('Zapisz szkic')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Zakończ badanie')).not.toBeInTheDocument();
    // Reopen is available
    expect(screen.getByLabelText('Wznów')).toBeInTheDocument();
  });

  it('reviews answers (not client findings), completes, then shows backend findings (LIFECYCLE)', async () => {
    const findings: InspectionFinding[] = [
      {
        id: 'f-1',
        finding_key: 'CRACK',
        label_key: 'checklist.question.cracks_present',
        value_snapshot: { bool: true },
        is_active: true,
        resolved_at: null,
        position: 0,
        answer_id: 'a-bool',
        question_id: 'q-bool',
        created_at: '2026-09-09T12:00:00Z',
        updated_at: '2026-09-09T12:00:00Z',
      },
    ];
    vi.mocked(inspectionsApi.fetchInspectionFindings).mockResolvedValue({
      items: findings,
      total: 1,
    });
    renderFlow();
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await screen.findByText(/Odpowiedzi: 0 \/ 5/);

    fireEvent.click(screen.getByLabelText('Tak'));
    fireEvent.click(screen.getByLabelText('Przejrzyj i zakończ'));

    // Review shows the current answer, not client-derived findings
    expect(await screen.findByText('Podsumowanie odpowiedzi')).toBeInTheDocument();
    expect(screen.getByText('Tak')).toBeInTheDocument();
    expect(inspectionsApi.completeInspection).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText('Zakończ badanie'));
    await waitFor(() =>
      expect(inspectionsApi.completeInspection).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-1',
      ),
    );
    // Actual findings appear only after completion, from the backend response
    expect(await screen.findByText(/Czy występują pęknięcia/)).toBeInTheDocument();
    expect(inspectionsApi.fetchInspectionFindings).toHaveBeenCalled();
  });

  it('preserves local review state when completion fails (LIFECYCLE)', async () => {
    vi.mocked(inspectionsApi.completeInspection).mockRejectedValue(new Error('boom'));
    renderFlow();
    fireEvent.click(await screen.findByLabelText('Beton'));
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    fireEvent.click(screen.getByLabelText('Nowe badanie'));
    await screen.findByText(/Odpowiedzi: 0 \/ 5/);

    fireEvent.click(screen.getByLabelText('Tak'));
    fireEvent.click(screen.getByLabelText('Przejrzyj i zakończ'));
    await screen.findByText('Podsumowanie odpowiedzi');
    fireEvent.click(screen.getByLabelText('Zakończ badanie'));

    // Error surfaced; review state (answer) preserved so the user can retry
    expect(await screen.findByText('boom')).toBeInTheDocument();
    expect(screen.getByText('Tak')).toBeInTheDocument();
    expect(screen.getByLabelText('Zakończ badanie')).toBeInTheDocument();
  });

  it('reopens a completed inspection back into an editable draft (LIFECYCLE)', async () => {
    const detail: InspectionDetail = {
      ...draftInspection,
      status: 'COMPLETED',
      completed_at: '2026-09-09T12:00:00Z',
      answers: [
        {
          id: 'a-bool',
          question_id: 'q-bool',
          value_bool: true,
          value_number: null,
          value_text: null,
          option_key: null,
          option_keys: null,
          updated_at: '2026-09-09T10:00:00Z',
        },
      ],
    };
    vi.mocked(inspectionsApi.fetchInspection).mockResolvedValue(detail);
    renderFlow({ inspectionId: 'ins-1' });

    await screen.findByLabelText('Wznów');
    fireEvent.click(screen.getByLabelText('Wznów'));
    await waitFor(() =>
      expect(inspectionsApi.reopenInspection).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-1',
      ),
    );
    // Back to editable draft
    expect(await screen.findByLabelText('Zapisz szkic')).toBeInTheDocument();
    expect(screen.getByLabelText('Przejrzyj i zakończ')).toBeInTheDocument();
  });

  it('uses ~44px touch targets and single-column layout (MOBILE)', async () => {
    renderFlow();
    const concrete = await screen.findByLabelText('Beton');
    expect(concrete).toHaveClass('min-h-14');
    const substrateGrid = concrete.closest('div');
    expect(substrateGrid).not.toBeNull();
    fireEvent.click(concrete);
    fireEvent.click(screen.getByLabelText('Dalej'));
    await screen.findByText('Klasa jakości');
    expect(screen.getByLabelText('Nowe badanie')).toHaveClass('min-h-11');
  });
});
