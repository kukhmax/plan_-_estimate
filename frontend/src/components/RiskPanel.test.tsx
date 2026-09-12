import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as risksApi from '../api/risks';
import { I18nProvider } from '../hooks/useI18n';
import {
  RiskDetail,
  RiskRead,
  RiskSourceFindingRead,
} from '../types/risk';
import { RiskPanel } from './RiskPanel';

vi.mock('../api/risks', () => ({
  evaluateRisks: vi.fn(),
  fetchRisks: vi.fn(),
  fetchRiskDetail: vi.fn(),
}));

function risk(overrides: Partial<RiskRead> = {}): RiskRead {
  return {
    id: 'risk-1',
    room_id: 'room-1',
    inspection_id: 'ins-1',
    risk_code: 'CRACK_RECURRENCE',
    rule_code: 'CRACK_RECURRENCE',
    rule_version: 1,
    severity: 'MEDIUM',
    title_key: 'risk.crack_recurrence.title',
    explanation_key: 'risk.crack_recurrence.explanation',
    consequence_key: 'risk.crack_recurrence.consequence',
    mitigation_key: 'risk.crack_recurrence.mitigation',
    communication_key: 'risk.crack_recurrence.communication',
    warranty_exclusion_candidate: false,
    blocks_finishing: false,
    source_signature: 'sig',
    is_active: true,
    resolved_at: null,
    position: 0,
    created_at: '2026-09-12T08:00:00Z',
    updated_at: '2026-09-12T08:00:00Z',
    ...overrides,
  };
}

function detail(
  source: RiskRead,
  source_findings: RiskSourceFindingRead[] = [],
): RiskDetail {
  return { ...source, source_findings };
}

function sourceFinding(
  findingKey: string,
  value?: Record<string, unknown>,
  position = 0,
): RiskSourceFindingRead {
  return {
    finding_id: `f-${findingKey}`,
    finding_key_snapshot: findingKey,
    value_snapshot: value ?? null,
    position,
  };
}

function renderPanel(props: { inspectionId?: string } = {}) {
  return render(
    <I18nProvider>
      <RiskPanel
        projectId="proj-1"
        roomId="room-1"
        inspectionId={props.inspectionId ?? 'ins-1'}
      />
    </I18nProvider>,
  );
}

describe('RiskPanel (Stage 7C)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(risksApi.evaluateRisks).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(risksApi.fetchRiskDetail).mockResolvedValue(detail(risk()));
  });

  it('sends the evaluation request with the inspection id and renders the returned risks (EVALUATION)', async () => {
    const moisture = risk({
      id: 'risk-moisture',
      risk_code: 'MOISTURE_BLOCK_FINISHING',
      severity: 'CRITICAL',
      blocks_finishing: true,
      title_key: 'risk.moisture_block_finishing.title',
    });
    vi.mocked(risksApi.evaluateRisks).mockResolvedValue({
      items: [detail(moisture, [sourceFinding('HIGH_MOISTURE', { bool: true })])],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText('Oceń ryzyka'));
    await waitFor(() =>
      expect(risksApi.evaluateRisks).toHaveBeenCalledWith('proj-1', 'room-1', 'ins-1'),
    );
    expect(await screen.findByText('Podwyższona wilgotność podłoża')).toBeInTheDocument();
  });

  it('surfaces a localized error and preserves the completed view on failure (EVALUATION)', async () => {
    vi.mocked(risksApi.evaluateRisks).mockRejectedValue(
      new Error('Risk evaluation requires a COMPLETED inspection'),
    );
    renderPanel();
    fireEvent.click(await screen.findByLabelText('Oceń ryzyka'));
    expect(
      await screen.findByText('Badanie nie zostało ukończone. Ukończ je przed oceną ryzyk.'),
    ).toBeInTheDocument();
    // View is not destroyed: the retryable evaluate action stays available.
    expect(screen.getByLabelText('Oceń ryzyka')).toBeInTheDocument();
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0);
  });

  it('outputs one clear label per severity with a distinct CRITICAL tone (SEVERITY)', async () => {
    const items = [
      risk({ id: 'r-lo', risk_code: 'DUSTY_SUBSTRATE_PRIME', severity: 'LOW', title_key: 'risk.dusty_substrate_prime.title' }),
      risk({ id: 'r-me', risk_code: 'OILY_SUBSTRATE_DEGREASE', severity: 'MEDIUM', title_key: 'risk.oily_substrate_degrease.title' }),
      risk({ id: 'r-hi', risk_code: 'WEAK_ADHESION_PREP', severity: 'HIGH', title_key: 'risk.weak_adhesion_prep.title' }),
      risk({ id: 'r-cr', risk_code: 'MOLD_TREATMENT_BEFORE_FINISH', severity: 'CRITICAL', title_key: 'risk.mold_treatment_before_finish.title' }),
    ];
    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items, total: 4 });
    renderPanel();
    expect(await screen.findByText('Niskie')).toBeInTheDocument();
    expect(screen.getByText('Średnie')).toBeInTheDocument();
    expect(screen.getByText('Wysokie')).toBeInTheDocument();
    expect(screen.getByText('Krytyczne')).toBeInTheDocument();
    expect(screen.getByText('Krytyczne')).toHaveClass('bg-red-600');
  });

  it('shows the blocks-finishing warning and warranty badge only when flagged (FLAGS)', async () => {
    const flagged = risk({
      id: 'r-warn',
      risk_code: 'MOISTURE_BLOCK_FINISHING',
      severity: 'CRITICAL',
      blocks_finishing: true,
      warranty_exclusion_candidate: true,
      title_key: 'risk.moisture_block_finishing.title',
    });
    const plain = risk({
      id: 'r-plain',
      risk_code: 'BLOW_HOLES_FILLING',
      severity: 'LOW',
      blocks_finishing: false,
      warranty_exclusion_candidate: false,
      title_key: 'risk.blow_holes_filling.title',
    });
    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [flagged, plain], total: 2 });
    renderPanel();
    await screen.findByText('Podwyższona wilgotność podłoża');
    expect(
      screen.getAllByText('Nie rozpoczynać / wstrzymać prace do usunięcia przyczyny'),
    ).toHaveLength(1);
    expect(screen.getAllByText('Możliwe ograniczenie odpowiedzialności')).toHaveLength(1);
    // The unflagged card shows neither.
    expect(screen.getByText('Raki / pęcherze')).toBeInTheDocument();
    expect(
      screen.queryAllByText('Nie rozpoczynać / wstrzymać prace do usunięcia przyczyny'),
    ).toHaveLength(1);
  });

  it('renders every source finding with localized label and safe value snapshot (TRACEABILITY)', async () => {
    const board = risk({
      id: 'r-board',
      risk_code: 'BOARD_MOVEMENT_CRACK',
      severity: 'HIGH',
      title_key: 'risk.board_movement_crack.title',
    });
    const uneven = risk({
      id: 'r-unev',
      risk_code: 'UNEVENNESS_PREP_INCREASED',
      severity: 'MEDIUM',
      title_key: 'risk.unevenness_prep_increased.title',
    });
    vi.mocked(risksApi.evaluateRisks).mockResolvedValue({
      items: [
        detail(board, [sourceFinding('CRACK', { bool: true }), sourceFinding('BOARD_MOVEMENT', { bool: true })]),
        detail(uneven, [sourceFinding('UNEVENNESS', { number: '3.500' })]),
      ],
      total: 2,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText('Oceń ryzyka'));

    fireEvent.click(
      await screen.findByLabelText(/Spękania na łączeniach płyt g-k.*Szczegóły/),
    );
    expect(await screen.findByText('Dlaczego?')).toBeInTheDocument();
    expect(screen.getByText('Pęknięcia — Tak')).toBeInTheDocument();
    expect(screen.getByText('Ruchliwość płyt — Tak')).toBeInTheDocument();

    // Numeric snapshot is rendered as-is with the mm unit, never recomputed.
    fireEvent.click(screen.getByLabelText(/Zwiększone nierówności.*Szczegóły/));
    expect(await screen.findByText('Nierówności — 3.500 mm')).toBeInTheDocument();
    // Sources arrived with the evaluate response; no per-card detail fetch.
    expect(risksApi.fetchRiskDetail).not.toHaveBeenCalled();
  });

  it('lazy-fetches exactly one detail per expanded card when sources are absent (TRACEABILITY)', async () => {
    const board = risk({
      id: 'risk-lazy',
      risk_code: 'BOARD_MOVEMENT_CRACK',
      severity: 'HIGH',
      title_key: 'risk.board_movement_crack.title',
    });
    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [board], total: 1 });
    vi.mocked(risksApi.fetchRiskDetail).mockResolvedValue(
      detail(board, [sourceFinding('CRACK', { bool: true }), sourceFinding('BOARD_MOVEMENT', { bool: true })]),
    );
    renderPanel();
    fireEvent.click(
      await screen.findByLabelText(/Spękania na łączeniach płyt g-k.*Szczegóły/),
    );
    await waitFor(() =>
      expect(risksApi.fetchRiskDetail).toHaveBeenCalledWith('proj-1', 'room-1', 'risk-lazy'),
    );
    expect(await screen.findByText('Pęknięcia — Tak')).toBeInTheDocument();
  });

  it('renders overlapping rules side by side without suppression (OVERLAP)', async () => {
    const cr = risk({ id: 'r-cr1', title_key: 'risk.crack_recurrence.title' });
    const bm = risk({
      id: 'r-cr2',
      risk_code: 'BOARD_MOVEMENT_CRACK',
      severity: 'HIGH',
      title_key: 'risk.board_movement_crack.title',
    });
    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [cr, bm], total: 2 });
    renderPanel();
    expect(await screen.findByText('Pęknięcia podłoża')).toBeInTheDocument();
    expect(screen.getByText('Spękania na łączeniach płyt g-k')).toBeInTheDocument();
  });

  it('filters active/resolved/all and refreshes after re-evaluation (LIFECYCLE)', async () => {
    const active = risk({ id: 'r-act', title_key: 'risk.crack_recurrence.title' });
    const resolved = risk({
      id: 'r-res',
      risk_code: 'MOLD_TREATMENT_BEFORE_FINISH',
      severity: 'HIGH',
      title_key: 'risk.mold_treatment_before_finish.title',
      is_active: false,
      resolved_at: '2026-09-12T10:00:00Z',
    });
    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [active], total: 1 });
    renderPanel();
    expect(await screen.findByText('Pęknięcia podłoża')).toBeInTheDocument();
    expect(screen.queryByText('Pleśń / grzyb')).not.toBeInTheDocument();

    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [resolved], total: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'Rozwiązane' }));
    expect(await screen.findByText('Pleśń / grzyb')).toBeInTheDocument();
    expect(screen.getByText('Rozwiązano 2026-09-12')).toBeInTheDocument();
    await waitFor(() =>
      expect(risksApi.fetchRisks).toHaveBeenCalledWith('proj-1', 'room-1', {
        inspectionId: 'ins-1',
        status: 'resolved',
      }),
    );

    // Re-evaluation refreshes the active list from the backend response.
    vi.mocked(risksApi.evaluateRisks).mockResolvedValue({
      items: [detail(active, [])],
      total: 1,
    });
    fireEvent.click(screen.getByLabelText('Oceń ryzyka'));
    await waitFor(() =>
      expect(risksApi.evaluateRisks).toHaveBeenCalledWith('proj-1', 'room-1', 'ins-1'),
    );
  });

  it('uses ~44px touch targets and a single-column card list (MOBILE)', async () => {
    const r = risk({ id: 'r-1', title_key: 'risk.crack_recurrence.title' });
    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [r], total: 1 });
    renderPanel();
    const evaluate = await screen.findByLabelText('Oceń ryzyka');
    expect(evaluate).toHaveClass('min-h-11');
    const list = screen.getByText('Pęknięcia podłoża').closest('ul');
    expect(list).not.toBeNull();
    expect(list).toHaveClass('flex-col');
  });

  it('localizes the full panel in RU when the RU locale is active (LOCALIZATION)', async () => {
    localStorage.setItem('locale', 'ru');
    try {
      renderPanel();
      expect(await screen.findByLabelText('Оценить риски')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Активные' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Все' })).toBeInTheDocument();
    } finally {
      localStorage.removeItem('locale');
    }
  });

  it('never leaks unresolved machine keys or raw backend error text (LOCALIZATION)', async () => {
    const r = risk({ id: 'r-1', title_key: 'risk.crack_recurrence.title' });
    vi.mocked(risksApi.fetchRisks).mockResolvedValue({ items: [r], total: 1 });
    renderPanel();
    expect(await screen.findByText('Pęknięcia podłoża')).toBeInTheDocument();
    expect(screen.queryByText(/risk\./)).not.toBeInTheDocument();
  });

  it('sends status=all explicitly and lists active and resolved together; filter switching never re-evaluates (Stage 7D.1 D2)', async () => {
    const activeRisk = risk({ id: 'r-act', title_key: 'risk.crack_recurrence.title' });
    const resolvedRisk = risk({
      id: 'r-res',
      risk_code: 'MOLD_TREATMENT_BEFORE_FINISH',
      severity: 'HIGH',
      title_key: 'risk.mold_treatment_before_finish.title',
      is_active: false,
      resolved_at: '2026-09-12T10:00:00Z',
    });
    vi.mocked(risksApi.fetchRisks).mockImplementation(async (_p, _r, opts) => {
      if (opts?.status === 'active') return { items: [activeRisk], total: 1 };
      if (opts?.status === 'resolved') return { items: [resolvedRisk], total: 1 };
      if (opts?.status === 'all') return { items: [activeRisk, resolvedRisk], total: 2 };
      return { items: [], total: 0 };
    });
    renderPanel();

    // Initial tab is active: exactly the one active risk.
    expect(await screen.findByText('Pęknięcia podłoża')).toBeInTheDocument();
    expect(screen.queryByText('Pleśń / grzyb')).not.toBeInTheDocument();

    // Resolved tab shows the resolved risk only.
    fireEvent.click(screen.getByRole('button', { name: 'Rozwiązane' }));
    expect(await screen.findByText('Pleśń / grzyb')).toBeInTheDocument();
    expect(screen.queryByText('Pęknięcia podłoża')).not.toBeInTheDocument();

    // All tab lists both. Critically the request carries status=all; dropping it would make
    // the backend default to active and hide the resolved risk.
    fireEvent.click(screen.getByRole('button', { name: 'Wszystkie' }));
    expect(await screen.findByText('Pęknięcia podłoża')).toBeInTheDocument();
    expect(screen.getByText('Pleśń / grzyb')).toBeInTheDocument();
    await waitFor(() =>
      expect(risksApi.fetchRisks).toHaveBeenCalledWith('proj-1', 'room-1', {
        inspectionId: 'ins-1',
        status: 'all',
      }),
    );

    // Filter switching is a pure list query; it must never trigger a re-evaluation.
    expect(risksApi.evaluateRisks).not.toHaveBeenCalled();
  });
});