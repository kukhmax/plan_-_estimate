import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { KnowledgeBasis, KnowledgeBasisTarget } from './KnowledgeBasis';
import { RiskPanel } from './RiskPanel';
import { CommunicationPanel } from './CommunicationPanel';
import { I18nProvider } from '../hooks/useI18n';
import * as api from '../api/knowledge';
import * as risksApi from '../api/risks';
import * as communicationsApi from '../api/communications';
import type { KnowledgeEntryDetail, KnowledgeEntryItem, KnowledgeLinkIndex } from '../types/knowledge';

vi.mock('../api/knowledge', () => ({
  fetchKnowledgeLinkIndex: vi.fn(),
  fetchKnowledgeEntry: vi.fn(),
}));
vi.mock('../api/risks', () => ({ evaluateRisks: vi.fn(), fetchRisks: vi.fn(), fetchRiskDetail: vi.fn() }));
vi.mock('../api/communications', () => ({ fetchCommunications: vi.fn(), evaluateCommunications: vi.fn(), fetchCommunicationDetail: vi.fn() }));

const ITEM = (code: string, overrides: Partial<KnowledgeEntryItem> = {}): KnowledgeEntryItem => ({
  code, kind: 'STATUTE', source: 'KC', source_designation: 'KC, t.j. Dz.U. 2026 poz. 795', locator: `art. ${code}`,
  title_pl: `Tytuł ${code}`, title_ru: `Название ${code}`, status: 'DRAFT', tags: [], ...overrides,
});

const INDEX: KnowledgeLinkIndex = {
  items: [
    { target_kind: 'RISK', target: 'MOISTURE_BLOCK_FINISHING', entries: [ITEM('KC.634'), ITEM('KC.557')] },
    { target_kind: 'DOCUMENT', target: 'DOWNTIME_NOTICE', entries: [ITEM('KC.640'), ITEM('KC.639')] },
    { target_kind: 'DOCUMENT', target: 'DOWNTIME_PROTOCOL', entries: [ITEM('KC.639'), ITEM('KC.640'), ITEM('KC.644', { status: 'APPROVED' })] },
  ],
};

const DETAIL = (code: string): KnowledgeEntryDetail => ({
  entry: {
    code, source: 'KC', locator: `art. ${code}`, title_pl: `Tytuł ${code}`, title_ru: `Название ${code}`, summary_pl: `Punkty ${code}.`,
    explanation_ru: `Пояснение ${code}.`, tags: [], status: 'DRAFT', approved_by: null, approved_on: null, checked_on: null, review_notes: [],
  },
  source: { code: 'KC', kind: 'STATUTE', title_pl: 'Kodeks cywilny', designation: 'KC', url: 'https://example.org/kc', status: 'DRAFT' },
  linked_from: [],
  places: [],
});

function renderBasis(targets: KnowledgeBasisTarget[] = [{ kind: 'RISK', target: 'MOISTURE_BLOCK_FINISHING' }]) {
  return render(<I18nProvider><KnowledgeBasis targets={targets} name="basis" /></I18nProvider>);
}

describe('KnowledgeBasis (Stage 17E)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchKnowledgeLinkIndex).mockResolvedValue(INDEX);
    vi.mocked(api.fetchKnowledgeEntry).mockImplementation(async (code: string) => DETAIL(code));
  });

  it('shows a folded line with the number of entries, and nothing else until it is opened', async () => {
    renderBasis();
    const toggle = await screen.findByLabelText('basis-toggle');
    expect(toggle).toHaveTextContent('Podstawa (2)');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('basis-entry-KC.634')).toBeNull();
    expect(api.fetchKnowledgeEntry).not.toHaveBeenCalled();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('basis-entry-KC.634')).toHaveTextContent('Tytuł KC.634');
    expect(screen.getByLabelText('basis-entry-KC.634')).toHaveTextContent('art. KC.634');
    expect(screen.getByLabelText('basis-entry-KC.557')).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.queryByLabelText('basis-entry-KC.634')).toBeNull();
  });

  it('is not on the screen at all when there is no link, while the index loads, or when it fails', async () => {
    vi.mocked(api.fetchKnowledgeLinkIndex).mockResolvedValue({ items: [] });
    const first = renderBasis();
    await waitFor(() => expect(api.fetchKnowledgeLinkIndex).toHaveBeenCalled());
    expect(first.container).toBeEmptyDOMElement();
    first.unmount();

    vi.mocked(api.fetchKnowledgeLinkIndex).mockReturnValue(new Promise(() => undefined));
    const second = renderBasis();
    expect(second.container).toBeEmptyDOMElement();
    second.unmount();

    vi.mocked(api.fetchKnowledgeLinkIndex).mockRejectedValue(new Error('offline'));
    const third = renderBasis();
    await waitFor(() => expect(api.fetchKnowledgeLinkIndex).toHaveBeenCalledTimes(3));
    expect(third.container).toBeEmptyDOMElement();
  });

  it('asks for a place that has no link and shows nothing for it', async () => {
    renderBasis([{ kind: 'PHRASE', target: 'COMM_NONE' }]);
    await waitFor(() => expect(api.fetchKnowledgeLinkIndex).toHaveBeenCalled());
    expect(screen.queryByLabelText('basis-toggle')).toBeNull();
  });

  it('a screen that stands for two places lists each entry once, in the order of the places', async () => {
    renderBasis([{ kind: 'DOCUMENT', target: 'DOWNTIME_NOTICE' }, { kind: 'DOCUMENT', target: 'DOWNTIME_PROTOCOL' }]);
    const toggle = await screen.findByLabelText('basis-toggle');
    expect(toggle).toHaveTextContent('Podstawa (3)');
    fireEvent.click(toggle);
    const codes = screen.getAllByRole('listitem').map((li) => li.querySelector('button')?.getAttribute('aria-label'));
    expect(codes).toEqual(['basis-entry-KC.640', 'basis-entry-KC.639', 'basis-entry-KC.644']);
  });

  it('marks the drafts and says they are for the lawyer to check; an approved entry has no mark', async () => {
    renderBasis([{ kind: 'DOCUMENT', target: 'DOWNTIME_PROTOCOL' }]);
    fireEvent.click(await screen.findByLabelText('basis-toggle'));
    expect(screen.getByText('Wersje robocze — do sprawdzenia przez prawnika.')).toBeInTheDocument();
    expect(screen.getByLabelText('basis-entry-KC.639')).toHaveTextContent('Wersja robocza');
    expect(screen.getByLabelText('basis-entry-KC.644')).not.toHaveTextContent('Wersja robocza');
  });

  it('opens an entry inside the list: the key points, then the link to the source; a second tap closes it; one is open at a time', async () => {
    renderBasis();
    fireEvent.click(await screen.findByLabelText('basis-toggle'));
    fireEvent.click(screen.getByLabelText('basis-entry-KC.634'));
    const list = screen.getByRole('list');
    expect(await within(list).findByLabelText('knowledge-summary')).toHaveTextContent('Punkty KC.634.');
    expect(within(list).queryByLabelText('knowledge-explanation')).toBeNull(); // the Polish interface: the key points only
    const link = within(list).getByLabelText('knowledge-source-link');
    expect(link).toHaveAttribute('href', 'https://example.org/kc');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    fireEvent.click(screen.getByLabelText('basis-entry-KC.557'));
    expect(await within(list).findByLabelText('knowledge-summary')).toHaveTextContent('Punkty KC.557.');
    expect(within(list).getAllByLabelText('knowledge-summary')).toHaveLength(1);
    fireEvent.click(screen.getByLabelText('basis-entry-KC.557'));
    expect(within(list).queryByLabelText('knowledge-summary')).toBeNull();
  });

  it('inside Telegram the source link leaves the Mini App through openLink; outside it stays an ordinary link', async () => {
    const openLink = vi.fn();
    window.Telegram = { WebApp: { openLink } } as never;
    try {
      renderBasis();
      fireEvent.click(await screen.findByLabelText('basis-toggle'));
      fireEvent.click(screen.getByLabelText('basis-entry-KC.634'));
      const link = await screen.findByLabelText('knowledge-source-link');
      const notPrevented = fireEvent.click(link);
      expect(openLink).toHaveBeenCalledWith('https://example.org/kc');
      expect(notPrevented).toBe(false); // the default action of the anchor was cancelled
      delete (window as { Telegram?: unknown }).Telegram;
      expect(fireEvent.click(link)).toBe(true);
      expect(openLink).toHaveBeenCalledTimes(1);
    } finally {
      delete (window as { Telegram?: unknown }).Telegram;
    }
  });

  it('speaks Russian in the Russian interface and adds the explanation', async () => {
    localStorage.setItem('locale', 'ru');
    renderBasis();
    const toggle = await screen.findByLabelText('basis-toggle');
    expect(toggle).toHaveTextContent('Основание (2)');
    fireEvent.click(toggle);
    expect(screen.getByLabelText('basis-entry-KC.634')).toHaveTextContent('Название KC.634');
    fireEvent.click(screen.getByLabelText('basis-entry-KC.634'));
    expect(await screen.findByLabelText('knowledge-explanation')).toHaveTextContent('Пояснение KC.634.');
  });

  it('an entry that does not load says so and the list stays usable', async () => {
    vi.mocked(api.fetchKnowledgeEntry).mockRejectedValueOnce(new Error('x'));
    renderBasis();
    fireEvent.click(await screen.findByLabelText('basis-toggle'));
    fireEvent.click(screen.getByLabelText('basis-entry-KC.634'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać bazy wiedzy.');
    fireEvent.click(screen.getByLabelText('basis-entry-KC.557'));
    expect(await screen.findByLabelText('knowledge-summary')).toHaveTextContent('Punkty KC.557.');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('keeps the toggle and the entries at least 44 px tall in the markup (touch targets)', async () => {
    renderBasis();
    expect((await screen.findByLabelText('basis-toggle')).className).toContain('min-h-11');
    fireEvent.click(screen.getByLabelText('basis-toggle'));
    expect(screen.getByLabelText('basis-entry-KC.634').className).toContain('min-h-11');
  });

  describe('on the screens that point at the knowledge base', () => {
    const riskRow = (id: string, code: string, warranty: boolean) => ({
      id, room_id: 'room', inspection_id: 'ins', risk_code: code, rule_code: code, rule_version: 1,
      severity: 'CRITICAL' as const, title_key: `risk.${code.toLowerCase()}.title`, explanation_key: 'x', consequence_key: 'x', mitigation_key: 'x',
      communication_key: 'x', warranty_exclusion_candidate: warranty, blocks_finishing: true, source_signature: 's', is_active: true,
      resolved_at: null, position: 0, created_at: '2026-09-12T08:00:00Z', updated_at: '2026-09-12T08:00:00Z',
    });

    it('the risks of an inspection share ONE block of the legal basis, not one under every card (17E.1)', async () => {
      vi.mocked(api.fetchKnowledgeLinkIndex).mockResolvedValue({
        items: [
          { target_kind: 'RISK', target: 'MOISTURE_BLOCK_FINISHING', entries: [ITEM('KC.634'), ITEM('KC.557')] },
          { target_kind: 'RISK', target: 'CRACK_RECURRENCE', entries: [ITEM('KC.634')] },
        ],
      });
      vi.mocked(risksApi.fetchRisks).mockResolvedValue({
        items: [riskRow('r1', 'MOISTURE_BLOCK_FINISHING', true), riskRow('r2', 'CRACK_RECURRENCE', false)], total: 2,
      });
      render(<I18nProvider><RiskPanel projectId="p" roomId="room" inspectionId="ins" /></I18nProvider>);
      const toggle = await screen.findByLabelText('knowledge-basis-risks-toggle');
      expect(toggle).toHaveTextContent('Podstawa prawna dla tych ryzyk (2)'); // KC.634 once, KC.557 once
      expect(screen.getAllByLabelText(/^knowledge-basis.*-toggle$/)).toHaveLength(1);
      expect(screen.queryByLabelText(/knowledge-basis-risk-/)).toBeNull();
    });

    it('the phrases for the client share one block that says why they must be said', async () => {
      const index: KnowledgeLinkIndex = { items: [{ target_kind: 'PHRASE', target: 'COMM_RISK_MOISTURE_BLOCK_FINISHING', entries: [ITEM('KC.634')] }] };
      vi.mocked(api.fetchKnowledgeLinkIndex).mockResolvedValue(index);
      const phrase = (id: string) => ({
        id, inspection_id: 'ins', phrase_code: 'COMM_RISK_MOISTURE_BLOCK_FINISHING', phrase_version: 1, category: 'REQUIRE_CLIENT_DECISION' as const, priority: 1,
        phrase_key: 'communication.comm_risk_moisture_block_finishing.phrase', why_key: null, seed_key: null, source_kind: 'RISK' as const, source_signature: 's',
        is_active: true, resolved_at: null, position: 0, created_at: '2026-09-12T08:00:00Z', updated_at: '2026-09-12T08:00:00Z',
      });
      vi.mocked(communicationsApi.fetchCommunications).mockResolvedValue({ items: [phrase('c1'), phrase('c2')], total: 2 });
      render(<I18nProvider><CommunicationPanel projectId="p" roomId="room" inspectionId="ins" /></I18nProvider>);
      const toggle = await screen.findByLabelText('knowledge-basis-phrases-toggle');
      expect(toggle).toHaveTextContent('Dlaczego trzeba to powiedzieć klientowi (1)');
      expect(screen.getAllByLabelText(/^knowledge-basis.*-toggle$/)).toHaveLength(1);
    });
  });
});
