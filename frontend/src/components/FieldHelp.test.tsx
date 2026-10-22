import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { FieldHelp } from './FieldHelp';
import { I18nProvider } from '../hooks/useI18n';
import * as api from '../api/knowledge';
import type { KnowledgeEntryDetail, KnowledgeEntryItem } from '../types/knowledge';

vi.mock('../api/knowledge', () => ({
  fetchKnowledgeEntryIndex: vi.fn(),
  fetchKnowledgeEntry: vi.fn(),
}));

const ITEM = (code: string, overrides: Partial<KnowledgeEntryItem> = {}): KnowledgeEntryItem => ({
  code, kind: 'ITB', source: 'ITB', source_designation: 'ITB', locator: null, title_pl: `Tytuł ${code}`, title_ru: `Название ${code}`,
  status: 'DRAFT', tags: [], substrates: [], qualities: [], ...overrides,
});

const DETAIL = (code: string): KnowledgeEntryDetail => ({
  entry: {
    code, source: 'ITB', locator: null, title_pl: `Tytuł ${code}`, title_ru: `Название ${code}`, summary_pl: `Punkty ${code}.`,
    explanation_ru: `Пояснение ${code}.`, tags: [], status: 'DRAFT', approved_by: null, approved_on: null, checked_on: null, review_notes: [],
  },
  source: { code: 'ITB', kind: 'ITB', title_pl: 'ITB', designation: 'ITB', url: 'https://example.org/itb', status: 'DRAFT' },
  linked_from: [],
  places: [],
});

const INDEX = {
  total: 4,
  items: [
    ITEM('TECH.MOISTURE', { substrates: ['CONCRETE', 'GYPSUM_PLASTER'] }),
    ITEM('TECH.GK-Q', { substrates: ['GYPSUM_BOARD'], qualities: ['Q1', 'Q2', 'Q3', 'Q4'] }),
    ITEM('TECH.COEF', { tags: ['wspolczynnik'] }),
    ITEM('KC.627'),
  ],
};

function renderHelp(match: Parameters<typeof FieldHelp>[0]['match'], name = 'substrate') {
  return render(<I18nProvider><FieldHelp name={name} field="Podłoże" match={match} /></I18nProvider>);
}

describe('FieldHelp (U-12)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchKnowledgeEntryIndex).mockResolvedValue(INDEX);
    vi.mocked(api.fetchKnowledgeEntry).mockImplementation(async (code) => DETAIL(code));
  });

  it('opens a sheet with the entries of the substrate, their key points and the source', async () => {
    renderHelp({ substrate: 'CONCRETE' });
    const button = await screen.findByLabelText('field-help-substrate');
    expect(button).toHaveAttribute('title', 'Wyjaśnienie: Podłoże');
    fireEvent.click(button);
    const sheet = await screen.findByRole('dialog', { name: 'field-help-sheet-substrate' });
    expect(await within(sheet).findByText('Punkty TECH.MOISTURE.')).toBeInTheDocument();
    expect(within(sheet).queryByLabelText('field-help-entry-TECH.GK-Q')).toBeNull();
    expect(within(sheet).getByLabelText('knowledge-source-link')).toHaveAttribute('href', 'https://example.org/itb');
    fireEvent.click(within(sheet).getByLabelText('field-help-close-substrate'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows the Russian title and the explanation in the Russian interface', async () => {
    localStorage.setItem('locale', 'ru');
    renderHelp({ qualities: ['Q3', 'S3'] }, 'quality');
    fireEvent.click(await screen.findByLabelText('field-help-quality'));
    const sheet = await screen.findByRole('dialog');
    expect(within(sheet).getByText('Название TECH.GK-Q')).toBeInTheDocument();
    expect(await within(sheet).findByText('Пояснение TECH.GK-Q.')).toBeInTheDocument();
  });

  it('finds the entries of a tag, and the button is a 44 px touch target', async () => {
    renderHelp({ tag: 'wspolczynnik' }, 'coefficient');
    const button = await screen.findByLabelText('field-help-coefficient');
    expect(button.className).toContain('min-h-11');
    expect(button.className).toContain('min-w-11');
  });

  it('shows no button while there is no entry for the field', async () => {
    renderHelp({ substrate: 'PAINTED' });
    await waitFor(() => expect(api.fetchKnowledgeEntryIndex).toHaveBeenCalled());
    expect(screen.queryByLabelText('field-help-substrate')).toBeNull();
  });

  it('shows no button when the server is unavailable', async () => {
    vi.mocked(api.fetchKnowledgeEntryIndex).mockRejectedValue(new Error('offline'));
    renderHelp({ substrate: 'CONCRETE' });
    await waitFor(() => expect(api.fetchKnowledgeEntryIndex).toHaveBeenCalled());
    expect(screen.queryByLabelText('field-help-substrate')).toBeNull();
  });
});
