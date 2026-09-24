import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as communicationsApi from '../api/communications';
import * as clipboardUtil from '../utils/clipboard';
import { I18nProvider } from '../hooks/useI18n';
import {
  CommunicationApplicationRead,
  CommunicationFindingSnapshot,
  CommunicationFindingSource,
  CommunicationQualitySource,
  CommunicationRiskSource,
} from '../types/communication';
import { RiskSourceFindingRead } from '../types/risk';
import { CommunicationPanel } from './CommunicationPanel';

vi.mock('../api/communications', () => ({
  fetchCommunications: vi.fn(),
  evaluateCommunications: vi.fn(),
  fetchCommunicationDetail: vi.fn(),
}));
vi.mock('../utils/clipboard', () => ({
  copyTextToClipboard: vi.fn(),
}));

function app(
  overrides: Partial<CommunicationApplicationRead> = {},
): CommunicationApplicationRead {
  return {
    id: 'comm-1',
    inspection_id: 'ins-1',
    phrase_code: 'COMM_FIND_UNEVENNESS',
    phrase_version: 1,
    category: 'EXPLAIN_CONDITION',
    priority: 10,
    phrase_key: 'communication.comm_find_unevenness.phrase',
    why_key: 'communication.comm_find_unevenness.why',
    seed_key: null,
    source_kind: 'FINDING',
    source_signature: 'sig',
    is_active: true,
    resolved_at: null,
    position: 0,
    created_at: '2026-09-12T08:00:00Z',
    updated_at: '2026-09-12T08:00:00Z',
    ...overrides,
  };
}

function riskSource(
  overrides: Partial<CommunicationRiskSource> = {},
): CommunicationRiskSource {
  return {
    kind: 'RISK',
    risk_id: 'risk-1',
    risk_code: 'CRACK_RECURRENCE',
    severity: 'MEDIUM',
    risk_is_active: true,
    source_findings: [],
    ...overrides,
  };
}

function findingSource(
  finding_key: string,
  findings: CommunicationFindingSnapshot[] = [],
): CommunicationFindingSource {
  return { kind: 'FINDING', finding_key, findings };
}

function snapshot(
  label_key: string | null,
  value: Record<string, unknown> | null,
): CommunicationFindingSnapshot {
  return {
    finding_id: `f-${label_key ?? 'x'}`,
    label_key,
    value_snapshot: value,
    is_active: true,
    position: 0,
  };
}

function qualitySource(): CommunicationQualitySource {
  return { kind: 'QUALITY', substrate: 'GYPSUM_PLASTER', quality_level: 'S3' };
}

function sourceFinding(
  findingKey: string,
  value?: Record<string, unknown>,
): RiskSourceFindingRead {
  return {
    finding_id: `f-${findingKey}`,
    finding_key_snapshot: findingKey,
    value_snapshot: value ?? null,
    position: 0,
  };
}

const UNEVEN_PHRASE =
  'Na podłożu stwierdziłem nierówności. W razie potrzeby wyrównam je przed pracami wykończeniowymi.';

function renderPanel() {
  return render(
    <I18nProvider>
      <CommunicationPanel
        projectId="proj-1"
        roomId="room-1"
        inspectionId="ins-1"
      />
    </I18nProvider>,
  );
}

describe('CommunicationPanel (Stage 8C)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [],
      total: 0,
    });
    vi.mocked(communicationsApi.evaluateCommunications).mockResolvedValue({
      items: [],
      total: 0,
    });
    vi.mocked(clipboardUtil.copyTextToClipboard).mockResolvedValue(true);
  });

  it('renders the section, defaults to Active, and never evaluates on load (ENTRY)', async () => {
    renderPanel();
    expect(await screen.findByText('Co powiedzieć klientowi')).toBeInTheDocument();
    expect(
      screen.getByText('Gotowe zwroty do rozmowy z klientem na podstawie wyników badania.'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Przygotuj komunikację')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Aktywne' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await waitFor(() =>
      expect(communicationsApi.fetchCommunications).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-1',
        { status: 'active' },
      ),
    );
    // List load is a plain query; evaluation requires an explicit tap.
    expect(communicationsApi.evaluateCommunications).not.toHaveBeenCalled();
    expect(
      screen.getByText('Brak aktywnej komunikacji dla tego badania.'),
    ).toBeInTheDocument();
  });

  it('evaluates on demand and renders the returned phrase card (EVALUATION)', async () => {
    const uneven = app({ id: 'c-unev' });
    vi.mocked(communicationsApi.evaluateCommunications).mockResolvedValue({
      items: [uneven],
      total: 1,
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText('Przygotuj komunikację'));
    await waitFor(() =>
      expect(communicationsApi.evaluateCommunications).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-1',
      ),
    );
    expect(await screen.findByText(UNEVEN_PHRASE)).toBeInTheDocument();
    // Category chip is localized.
    expect(screen.getByText('Wyjaśnienie stanu')).toBeInTheDocument();
    // The primary action now refreshes instead of first-time evaluation.
    expect(screen.getByText('Odśwież komunikację')).toBeInTheDocument();
  });

  it('surfaces a localized error and keeps the evaluate action on failure (EVALUATION)', async () => {
    vi.mocked(communicationsApi.evaluateCommunications).mockRejectedValue(
      new Error('Communication evaluation requires a COMPLETED inspection'),
    );
    renderPanel();
    fireEvent.click(await screen.findByLabelText('Przygotuj komunikację'));
    expect(
      await screen.findByText(
        'Badanie nie zostało ukończone. Ukończ je przed przygotowaniem komunikacji.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Przygotuj komunikację')).toBeInTheDocument();
  });

  it('filters active/resolved/all with explicit status and never re-evaluates (FILTERS)', async () => {
    const active = app({ id: 'c-act' });
    const resolved = app({
      id: 'c-res',
      phrase_key: 'communication.comm_find_joint_gap.phrase',
      why_key: 'communication.comm_find_joint_gap.why',
      is_active: false,
      resolved_at: '2026-09-12T10:00:00Z',
    });
    vi.mocked(communicationsApi.fetchCommunications).mockImplementation(
      async (_p, _r, _i, opts) => {
        if (opts?.status === 'resolved') return { items: [resolved], total: 1 };
        if (opts?.status === 'all') return { items: [active, resolved], total: 2 };
        return { items: [active], total: 1 };
      },
    );
    renderPanel();
    expect(await screen.findByText(UNEVEN_PHRASE)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Zakończone' }));
    expect(await screen.findByText('Zakończono 2026-09-12')).toBeInTheDocument();
    // Resolved cards show their phrase text and stay readable.
    expect(
      screen.getByText('Na łączeniach płyt widoczne są niewielkie szczeliny. Wypełnię je masą przed szpachlowaniem.'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(communicationsApi.fetchCommunications).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-1',
        { status: 'resolved' },
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Wszystkie' }));
    expect(await screen.findByText(UNEVEN_PHRASE)).toBeInTheDocument();
    expect(
      screen.getByText('Na łączeniach płyt widoczne są niewielkie szczeliny. Wypełnię je masą przed szpachlowaniem.'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(communicationsApi.fetchCommunications).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-1',
        { status: 'all' },
      ),
    );

    // Filter switching is a pure list query — it must never re-evaluate.
    expect(communicationsApi.evaluateCommunications).not.toHaveBeenCalled();
  });

  it('lazy-fetches the source exactly once per expanded card and caches it (TRACEABILITY)', async () => {
    const board = app({
      id: 'c-board',
      phrase_key: 'communication.comm_find_board_movement.phrase',
      why_key: 'communication.comm_find_board_movement.why',
    });
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [board],
      total: 1,
    });
    vi.mocked(communicationsApi.fetchCommunicationDetail).mockResolvedValue({
      ...board,
      source: riskSource({
        risk_code: 'BOARD_MOVEMENT_CRACK',
        severity: 'HIGH',
        source_findings: [
          sourceFinding('CRACK', { bool: true }),
          sourceFinding('BOARD_MOVEMENT', { bool: true }),
        ],
      }),
    });
    renderPanel();
    const whyButton = await screen.findByLabelText(
      /Stwierdziłem ruchliwość płyt g-k.*Dlaczego\?/,
    );
    // Detail is fetched lazily: never before the first expand.
    expect(communicationsApi.fetchCommunicationDetail).not.toHaveBeenCalled();

    fireEvent.click(whyButton);
    await waitFor(() =>
      expect(communicationsApi.fetchCommunicationDetail).toHaveBeenCalledWith(
        'proj-1',
        'room-1',
        'ins-1',
        'c-board',
      ),
    );
    // RISK source: why text, localized risk title, severity, findings and snapshots.
    expect(await screen.findByText('Spękania na łączeniach płyt g-k')).toBeInTheDocument();
    expect(screen.getByText('Wskazanie ruchliwości płyt z badania podłoża.')).toBeInTheDocument();
    expect(screen.getByText('Wysokie')).toBeInTheDocument();
    expect(screen.getByText('Pęknięcia — Tak')).toBeInTheDocument();
    expect(screen.getByText('Ruchliwość płyt — Tak')).toBeInTheDocument();

    // Collapse and re-expand: the cached detail is reused, no second fetch.
    fireEvent.click(
      screen.getByLabelText(/Stwierdziłem ruchliwość płyt g-k.*Ukryj wyjaśnienie/),
    );
    fireEvent.click(
      screen.getByLabelText(/Stwierdziłem ruchliwość płyt g-k.*Dlaczego\?/),
    );
    expect(screen.getByText('Spękania na łączeniach płyt g-k')).toBeInTheDocument();
    expect(communicationsApi.fetchCommunicationDetail).toHaveBeenCalledTimes(1);
  });

  it('formats numeric snapshots to exactly two decimals and renders booleans/text (FINDING / 2-DECIMAL)', async () => {
    const uneven = app({ id: 'c-unev' });
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [uneven],
      total: 1,
    });
    vi.mocked(communicationsApi.fetchCommunicationDetail).mockResolvedValue({
      ...uneven,
      source: findingSource('UNEVENNESS', [
        snapshot('checklist.question.unevenness_mm', { number: '3.000' }),
        snapshot('checklist.option.substrate_loose', { bool: true }),
        snapshot('checklist.question.notes', { text: 'spalling' }),
        snapshot('checklist.question.board_movement', { number: '13.515' }),
      ]),
    });
    renderPanel();
    fireEvent.click(await screen.findByLabelText(/Na podłożu stwierdziłem nierówności.*Dlaczego\?/));
    expect(await screen.findByText('Nierówności podłoża — 3.00 mm')).toBeInTheDocument();
    expect(screen.getByText('Luzne — Tak')).toBeInTheDocument();
    expect(screen.getByText('Uwagi — spalling')).toBeInTheDocument();
    // 13.515 rounds to 13.52 (toFixed) — not 13.51, not a 3-digit tail.
    expect(screen.getByText('Czy płyty g-k się ruszają? — 13.52 mm')).toBeInTheDocument();
    // Machine finding keys never leak into the disclosure.
    expect(screen.queryByText(/checklist\./)).not.toBeInTheDocument();
    expect(screen.queryByText(/UNEVENNESS/)).not.toBeInTheDocument();
  });

  it('shows the QUALITY source as substrate plus quality target (TRACEABILITY)', async () => {
    const quality = app({
      id: 'c-qual',
      category: 'QUALITY_EXPECTATION',
      phrase_key: 'communication.comm_quality_gypsum_plaster_s3.phrase',
      why_key: 'communication.comm_quality_gypsum_plaster_s3.why',
    });
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [quality],
      total: 1,
    });
    vi.mocked(communicationsApi.fetchCommunicationDetail).mockResolvedValue({
      ...quality,
      source: qualitySource(),
    });
    renderPanel();
    expect(
      await screen.findByText(
        'Podłoże: tynk gipsowy, poziom S3 — przygotuję powierzchnię o podwyższonej jednorodności wizualnej, pod bardziej wymagające wnętrza, duże jednolite powierzchnie lub trudniejsze oświetlenie.',
      ),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByLabelText(
        /Podłoże: tynk gipsowy, poziom S3.*Dlaczego\?/,
      ),
    );
    expect(await screen.findByText('Poziom jakości')).toBeInTheDocument();
    // Substrate and quality target both resolve; label columns are present.
    expect(screen.getByText('Tynk gipsowy')).toBeInTheDocument();
    expect(screen.getByText('S3')).toBeInTheDocument();
    expect(screen.getByText('Podłoże:')).toBeInTheDocument();
    expect(screen.getByText('Klasa jakości:')).toBeInTheDocument();
  });

  it('copies the exact phrase text and shows a visible success state (COPY)', async () => {
    const uneven = app({ id: 'c-unev' });
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [uneven],
      total: 1,
    });
    renderPanel();
    fireEvent.click(
      await screen.findByLabelText(/Na podłożu stwierdziłem nierówności.*Kopiuj/),
    );
    // The exact localized phrase is handed to the clipboard primitive.
    await waitFor(() =>
      expect(clipboardUtil.copyTextToClipboard).toHaveBeenCalledWith(UNEVEN_PHRASE),
    );
    // The visible copy button flips to a success label (the sr-only live region
    // duplicates the string, so assert on the button itself).
    const copyButton = screen.getByLabelText(/.*Kopiuj/);
    expect(copyButton).toHaveTextContent('Skopiowano');
  });

  it('shows a localized failure state when the clipboard rejects (COPY)', async () => {
    vi.mocked(clipboardUtil.copyTextToClipboard).mockResolvedValue(false);
    const uneven = app({ id: 'c-unev' });
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [uneven],
      total: 1,
    });
    renderPanel();
    fireEvent.click(
      await screen.findByLabelText(/Na podłożu stwierdziłem nierówności.*Kopiuj/),
    );
    // Appears in both the inline alert and the sr-only live region.
    await waitFor(() =>
      expect(screen.getAllByText('Nie udało się skopiować.').length).toBeGreaterThan(0),
    );
  });

  it('falls back to a neutral localized phrase and never leaks a raw key (LOCALIZATION)', async () => {
    const broken = app({
      id: 'c-broken',
      phrase_key: 'risk.nonexistent.communication',
      why_key: null,
    });
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [broken],
      total: 1,
    });
    renderPanel();
    expect(
      await screen.findByText('Treść komunikacji jest niedostępna.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/risk\.|checklist\.|COMM_/)).not.toBeInTheDocument();
  });

  it('localizes the full panel in RU when the RU locale is active (LOCALIZATION)', async () => {
    localStorage.setItem('locale', 'ru');
    try {
      const uneven = app({ id: 'c-unev' });
      vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
        items: [uneven],
        total: 1,
      });
      renderPanel();
      expect(await screen.findByLabelText('Подготовить фразы')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Активные' })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      expect(
        await screen.findByText(
          'На основании я обнаружил неровности. При необходимости выровняю их перед отделочными работами.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByText('Пояснение состояния')).toBeInTheDocument();
    } finally {
      localStorage.removeItem('locale');
    }
  });

  it('keeps emphasis subtle and scoped to decision/agreement categories (PRESENTATION)', async () => {
    const decision = app({
      id: 'c-dec',
      category: 'REQUIRE_CLIENT_DECISION',
      phrase_key: 'risk.moisture_block_finishing.communication',
      why_key: null,
    });
    const plain = app({
      id: 'c-plain',
      phrase_key: 'communication.comm_find_joint_gap.phrase',
      why_key: 'communication.comm_find_joint_gap.why',
    });
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [decision, plain],
      total: 2,
    });
    renderPanel();
    expect(await screen.findByText('Wymagana decyzja')).toBeInTheDocument();
    expect(screen.getByText('Wymagana decyzja')).toHaveClass('bg-blue-50');
    expect(screen.getByText('Wyjaśnienie stanu')).toHaveClass('bg-neutral-100');
  });

  it('uses ~44px touch targets, single-column list, and wrapping chip rows (MOBILE)', async () => {
    const uneven = app({ id: 'c-unev' });
    vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({
      items: [uneven],
      total: 1,
    });
    renderPanel();
    await screen.findByText(UNEVEN_PHRASE);
    expect(screen.getByLabelText('Przygotuj komunikację')).toHaveClass('min-h-11');
    const list = screen.getByText(UNEVEN_PHRASE).closest('ul');
    expect(list).not.toBeNull();
    expect(list).toHaveClass('flex-col');
    expect(screen.getByLabelText(/.*Dlaczego\?/)).toHaveClass('min-h-10');
    expect(screen.getByLabelText(/.*Kopiuj/)).toHaveClass('min-h-11');
    // The chip row is a wrapping flex so long translations never overflow.
    const chipRow = screen.getByText('Wyjaśnienie stanu').closest('div');
    expect(chipRow).toHaveClass('flex-wrap');
  });
});