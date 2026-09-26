/**
 * Stage 13F.3 — Cennik → Procesy: template list + read-only detail.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as priceItemsApi from '../api/priceItems';
import * as templatesApi from '../api/workflowTemplates';
import { I18nProvider, useI18n } from '../hooks/useI18n';
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { WorkflowTemplateRead, WorkflowTemplateStepRead } from '../types/workflowTemplate';
import { PriceBook } from './PriceBook';
import { WorkflowTemplateManager } from './WorkflowTemplateManager';

vi.mock('../api/priceItems', () => ({
  fetchPriceItems: vi.fn(), createPriceItem: vi.fn(), updatePriceItem: vi.fn(),
  archivePriceItem: vi.fn(), restorePriceItem: vi.fn(),
}));
vi.mock('../api/coefficients', () => ({ fetchCoefficientGroups: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('../api/workflowTemplates', async (orig) => ({
  ...(await orig<typeof import('../api/workflowTemplates')>()),
  fetchWorkflowTemplates: vi.fn(),
  applyTemplateToWorkPlan: vi.fn(),
}));

function item(id: string, name: string, extra: Partial<SurfacePriceItemSummaryRead> = {}): SurfacePriceItemSummaryRead {
  return {
    id, code: id.toUpperCase(), name_key: null, display_name: name, category: 'SKIM_COAT', unit: 'M2',
    price_scope: 'LABOR', price: '10.00', currency: 'PLN', is_archived: false, quality_level: null, ...extra,
  };
}
function step(id: string, position: number, priceItem: SurfacePriceItemSummaryRead | null, extra: Partial<WorkflowTemplateStepRead> = {}): WorkflowTemplateStepRead {
  return {
    id, position, price_item_id: priceItem?.id ?? 'gone', is_optional: false, note: null, wait_after_hours: null,
    price_item: priceItem, ...extra,
  };
}

const PRIME = item('p1', 'Gruntowanie');
const SKIM = item('p2', 'Gładź szpachlowa — 2 warstwy (pakiet)');
const NO_PRICE = item('p3', 'Szpachlowanie dodatkowe', { price: null });
const OLD = item('p4', 'Stara pozycja', { is_archived: true });
const CORNER = item('p5', 'Narożniki', { unit: 'LM' });

const builtin: WorkflowTemplateRead = {
  id: 'tpl-builtin', code: 'TECH_BETON_S2-01', name_key: 'workflow_templates.seed.tech_beton_s2', display_name: null,
  description: 'Opis procesu', applies_to_substrates: ['CONCRETE'], applies_to_quality: ['S2'],
  applies_to_surface_types: ['WALL', 'CEILING', 'OTHER'], position: 0, is_archived: false, is_default: true,
  created_at: '', updated_at: '',
  steps: [
    step('s1', 0, PRIME, { wait_after_hours: 24 }),
    step('s2', 1, SKIM, { is_optional: true, note: 'Po wyschnięciu' }),
    step('s3', 2, PRIME), // same PriceItem again: an independent step
    step('s4', 3, NO_PRICE),
    step('s5', 4, OLD),
    step('s6', 5, CORNER),
  ],
};
const custom: WorkflowTemplateRead = {
  ...builtin, id: 'tpl-custom', code: 'CUSTOM_ABC123', name_key: null, display_name: 'Mój proces',
  description: null, applies_to_substrates: [], applies_to_quality: [], applies_to_surface_types: [],
  is_default: false, steps: [],
};
const archived: WorkflowTemplateRead = { ...custom, id: 'tpl-arch', display_name: 'Stary proces', is_archived: true };

function renderManager() {
  return render(<I18nProvider><WorkflowTemplateManager /></I18nProvider>);
}

describe('Workflow template management — list + read-only detail (13F.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(templatesApi.fetchWorkflowTemplates).mockImplementation(async ({ archived: which }) =>
      which === 'archived' ? { items: [archived], total: 1 } : { items: [builtin, custom], total: 2 });
  });

  it('Cennik → Procesy navigation and return to the Price Book items', async () => {
    render(<I18nProvider><PriceBook /></I18nProvider>);
    const tab = await screen.findByLabelText('pricebook-maintab-processes');
    expect(tab).toHaveTextContent('Procesy');
    fireEvent.click(tab);
    expect(await screen.findByLabelText('processes-list')).toBeInTheDocument();
    expect(templatesApi.fetchWorkflowTemplates).toHaveBeenCalledWith({ archived: 'active', surface_type: undefined });
    fireEvent.click(screen.getByLabelText('pricebook-maintab-items'));
    await waitFor(() => expect(screen.queryByLabelText('processes-section')).not.toBeInTheDocument());
  });

  it('lists templates with name, default badge, surfaces and step counts', async () => {
    renderManager();
    const card = await screen.findByLabelText('process-card-tpl-builtin');
    expect(card).toHaveTextContent('Beton — S2 — standard malarski'); // localized name_key
    expect(card).toHaveTextContent('Domyślny');
    expect(card).toHaveTextContent('Ściana, Sufit, Inna');
    expect(card).toHaveTextContent('Kroki: 6');
    expect(card).toHaveTextContent('w tym opcjonalne: 1');
    expect(card).toHaveTextContent('pozycje zarchiwizowane: 1');
    expect(card).toHaveTextContent('bez ceny: 1');
    const customCard = screen.getByLabelText('process-card-tpl-custom');
    expect(customCard).toHaveTextContent('Mój proces');
    expect(customCard).not.toHaveTextContent('Domyślny');
    expect(customCard).toHaveTextContent('Dowolne');
    expect(customCard).toHaveTextContent('Kroki: 0');
    expect(screen.queryByText('Zarchiwizowany')).not.toBeInTheDocument();
  });

  it('active vs archived tabs', async () => {
    renderManager();
    await screen.findByLabelText('process-card-tpl-builtin');
    fireEvent.click(screen.getByLabelText('processes-tab-archived'));
    const card = await screen.findByLabelText('process-card-tpl-arch');
    expect(card).toHaveTextContent('Zarchiwizowany');
    expect(templatesApi.fetchWorkflowTemplates).toHaveBeenLastCalledWith({ archived: 'archived', surface_type: undefined });
    expect(screen.queryByLabelText('process-card-tpl-builtin')).not.toBeInTheDocument();
    vi.mocked(templatesApi.fetchWorkflowTemplates).mockResolvedValueOnce({ items: [], total: 0 });
    fireEvent.click(screen.getByLabelText('processes-tab-active'));
    expect(await screen.findByLabelText('processes-empty')).toHaveTextContent('Brak procesów technologicznych dla tego filtra.');
  });

  it('surface-type filter uses the server filter', async () => {
    renderManager();
    await screen.findByLabelText('process-card-tpl-builtin');
    fireEvent.click(screen.getByLabelText('processes-filter-CEILING'));
    await waitFor(() =>
      expect(templatesApi.fetchWorkflowTemplates).toHaveBeenLastCalledWith({ archived: 'active', surface_type: 'CEILING' }));
    expect(screen.getByLabelText('processes-filter-CEILING')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByLabelText('processes-filter-all'));
    await waitFor(() =>
      expect(templatesApi.fetchWorkflowTemplates).toHaveBeenLastCalledWith({ archived: 'active', surface_type: undefined }));
  });

  it('read-only detail: metadata and ordered steps incl. duplicates, waits, units, null price, archived item', async () => {
    renderManager();
    fireEvent.click(await screen.findByLabelText('process-card-tpl-builtin'));
    const detail = screen.getByLabelText('process-detail-tpl-builtin');
    expect(detail).toHaveTextContent('Beton — S2 — standard malarski');
    expect(detail).toHaveTextContent('Domyślny');
    expect(detail).toHaveTextContent('Kod: TECH_BETON_S2-01');
    expect(detail).toHaveTextContent('Opis procesu');
    const applicability = within(detail).getByLabelText('process-applicability');
    expect(applicability).toHaveTextContent('Ściana, Sufit, Inna');
    expect(applicability).toHaveTextContent('Beton');
    expect(applicability).toHaveTextContent('S2');
    expect(detail).toHaveTextContent('Kroki technologiczne (6)');

    const rows = within(within(detail).getByLabelText('process-steps')).getAllByRole('listitem');
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual(['s1', 's2', 's3', 's4', 's5', 's6'].map((s) => `process-step-${s}`));
    expect(rows[0]).toHaveTextContent('1.Gruntowanie');
    expect(rows[0]).toHaveTextContent('Wymagany');
    expect(rows[0]).toHaveTextContent('m²');
    expect(rows[0]).toHaveTextContent('Przerwa technologiczna: 24 h');
    expect(rows[1]).toHaveTextContent('Opcjonalny');
    expect(rows[1]).toHaveTextContent('Po wyschnięciu');
    expect(rows[1]).not.toHaveTextContent('Przerwa');
    expect(rows[2]).toHaveTextContent('3.Gruntowanie'); // duplicate PriceItem stays its own step
    expect(rows[3]).toHaveTextContent('Brak ceny w cenniku');
    expect(rows[4]).toHaveTextContent('Pozycja zarchiwizowana — niedostępna');
    expect(rows[4]).not.toHaveTextContent('Brak ceny');
    expect(rows[5]).toHaveTextContent('mb');
    // read-only: no editing or applying controls
    expect(within(detail).getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual(['process-detail-back']);

    fireEvent.click(screen.getByLabelText('process-detail-back'));
    expect(await screen.findByLabelText('processes-list')).toBeInTheDocument();
  });

  it('empty template and a step whose PriceItem is missing render safely', async () => {
    vi.mocked(templatesApi.fetchWorkflowTemplates).mockResolvedValue({
      items: [custom, { ...custom, id: 'tpl-missing', display_name: 'Brakująca pozycja', steps: [step('m1', 0, null)] }], total: 2,
    });
    renderManager();
    fireEvent.click(await screen.findByLabelText('process-card-tpl-custom'));
    expect(screen.getByLabelText('process-steps-empty')).toHaveTextContent('Ten proces nie ma jeszcze kroków.');
    expect(screen.getByLabelText('process-applicability')).toHaveTextContent('Dowolne');
    fireEvent.click(screen.getByLabelText('process-detail-back'));
    fireEvent.click(await screen.findByLabelText('process-card-tpl-missing'));
    expect(screen.getByLabelText('process-step-m1')).toHaveTextContent('Pozycja zarchiwizowana — niedostępna');
  });

  it('load error offers a retry', async () => {
    vi.mocked(templatesApi.fetchWorkflowTemplates).mockRejectedValueOnce(new Error('network'));
    renderManager();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać procesów technologicznych.');
    fireEvent.click(screen.getByText('Ponów próbę'));
    expect(await screen.findByLabelText('process-card-tpl-builtin')).toBeInTheDocument();
  });

  it('renders in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    render(<I18nProvider><PriceBook /></I18nProvider>);
    fireEvent.click(await screen.findByLabelText('pricebook-maintab-processes'));
    expect(screen.getByLabelText('pricebook-maintab-processes')).toHaveTextContent('Процессы');
    const card = await screen.findByLabelText('process-card-tpl-builtin');
    expect(card).toHaveTextContent('По умолчанию');
    expect(screen.getByLabelText('processes-tab-archived')).toHaveTextContent('Архив');
    fireEvent.click(card);
    const detail = screen.getByLabelText('process-detail-tpl-builtin');
    expect(detail).toHaveTextContent('Технологические шаги (6)');
    expect(detail).toHaveTextContent('Нет цены в прайсе');
    expect(screen.getByLabelText('process-detail-back')).toHaveTextContent('Процессы');
  });
});

describe('Built-in description localization (13F.3 FIX.1)', () => {
  const S2_PL = "Standard Wykończenia Powierzchni S2 — Wewnętrzna klasyfikacja wykonawcy. Typowy standard powierzchni gotowej do zwykłego malowania wnętrz. Bez malowania — powierzchnia gotowa do kolejnego systemu wykończeniowego.";
  const S2_RU = "Стандарт отделки поверхности S2 — Внутренняя классификация подрядчика. Типовой стандарт поверхности, готовой к обычной покраске интерьеров. Без покраски — поверхность готова к следующей отделочной системе.";
  const untouched: WorkflowTemplateRead = {
    ...builtin, id: 'tpl-s2', description: S2_PL, description_key: 'workflow_templates.description.s2', steps: [],
  };
  const ownerEdited: WorkflowTemplateRead = {
    ...builtin, id: 'tpl-edited', description: 'Moja wersja opisu', description_key: null, steps: [],
  };
  const customWithText: WorkflowTemplateRead = { ...custom, id: 'tpl-own', description: 'Własny opis procesu' };
  const noDescription: WorkflowTemplateRead = { ...custom, id: 'tpl-nodesc', description: null, description_key: null };
  const unknownKey: WorkflowTemplateRead = {
    ...builtin, id: 'tpl-unknown', description: 'Tekst z serwera', description_key: 'workflow_templates.description.zz', steps: [],
  };

  function LocaleSwitch() {
    const { setLocale } = useI18n();
    return <button type="button" aria-label="switch-ru" onClick={() => setLocale('ru')}>ru</button>;
  }
  function renderWithSwitch() {
    return render(<I18nProvider><LocaleSwitch /><WorkflowTemplateManager /></I18nProvider>);
  }
  const openDetail = async (id: string) => {
    fireEvent.click(await screen.findByLabelText(`process-card-${id}`));
    return screen.getByLabelText(`process-detail-${id}`);
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(templatesApi.fetchWorkflowTemplates).mockResolvedValue({
      items: [untouched, ownerEdited, customWithText, noDescription, unknownKey], total: 5,
    });
  });

  it('untouched built-in: canonical Polish in PL, switches to Russian after PL -> RU', async () => {
    renderWithSwitch();
    await openDetail('tpl-s2');
    expect(screen.getByLabelText('process-description')).toHaveTextContent(S2_PL);
    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(screen.getByLabelText('process-description')).toHaveTextContent(S2_RU));
    expect(screen.getByLabelText('process-description')).not.toHaveTextContent('Wewnętrzna');
  });

  it('untouched built-in shows the Russian description when opened in RU', async () => {
    localStorage.setItem('locale', 'ru');
    renderManager();
    await openDetail('tpl-s2');
    expect(screen.getByLabelText('process-description')).toHaveTextContent(S2_RU);
  });

  it('owner-edited built-in description is preserved verbatim in PL and RU', async () => {
    renderWithSwitch();
    await openDetail('tpl-edited');
    expect(screen.getByLabelText('process-description')).toHaveTextContent('Moja wersja opisu');
    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(screen.getByLabelText('process-detail-back')).toHaveTextContent('Процессы'));
    expect(screen.getByLabelText('process-description')).toHaveTextContent('Moja wersja opisu');
  });

  it('custom template description is preserved verbatim in PL and RU', async () => {
    renderWithSwitch();
    await openDetail('tpl-own');
    expect(screen.getByLabelText('process-description')).toHaveTextContent('Własny opis procesu');
    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(screen.getByLabelText('process-detail-back')).toHaveTextContent('Процессы'));
    expect(screen.getByLabelText('process-description')).toHaveTextContent('Własny opis procesu');
  });

  it('missing description renders safely; an unknown key falls back to the stored text', async () => {
    renderManager();
    const detail = await openDetail('tpl-nodesc');
    expect(within(detail).queryByLabelText('process-description')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('process-detail-back'));
    await openDetail('tpl-unknown');
    expect(screen.getByLabelText('process-description')).toHaveTextContent('Tekst z serwera');
  });
});

describe('Built-in step note localization (13F.3 FIX.2)', () => {
  const CLEAN_PL = "Podłoże odpylone i oczyszczone przed gruntowaniem i naprawami.";
  const CLEAN_RU = "Основание обеспылено и очищено перед грунтованием и ремонтом.";
  const KEY = 'workflow_templates.step_note.clean';
  const tpl: WorkflowTemplateRead = {
    ...builtin, id: 'tpl-notes', steps: [
      step('n1', 0, PRIME, { note: CLEAN_PL, note_key: KEY }),
      step('n2', 1, PRIME, { note: 'Notatka właściciela', note_key: null }), // same PriceItem, edited note
      step('n3', 2, PRIME, { note: CLEAN_PL, note_key: KEY }),               // same PriceItem, canonical again
      step('n4', 3, SKIM, { note: null, note_key: null }),
      step('n5', 4, SKIM, { note: 'Tekst z serwera', note_key: 'workflow_templates.step_note.zz' }),
    ],
  };
  const customTpl: WorkflowTemplateRead = { ...custom, id: 'tpl-cnote', steps: [step('c1', 0, PRIME, { note: 'Moja notatka' })] };

  function LocaleSwitch() {
    const { setLocale } = useI18n();
    return <button type="button" aria-label="switch-ru" onClick={() => setLocale('ru')}>ru</button>;
  }
  const note = (id: string) => screen.queryByLabelText(`process-step-note-${id}`);

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(templatesApi.fetchWorkflowTemplates).mockResolvedValue({ items: [tpl, customTpl], total: 2 });
  });

  it('PL shows canonical notes; PL -> RU localizes only canonical notes, per step', async () => {
    render(<I18nProvider><LocaleSwitch /><WorkflowTemplateManager /></I18nProvider>);
    fireEvent.click(await screen.findByLabelText('process-card-tpl-notes'));
    const rows = within(screen.getByLabelText('process-steps')).getAllByRole('listitem');
    expect(rows).toHaveLength(5); // repeated PriceItems stay separate steps
    expect(note('n1')).toHaveTextContent(CLEAN_PL);
    expect(note('n2')).toHaveTextContent('Notatka właściciela');
    expect(note('n3')).toHaveTextContent(CLEAN_PL);
    expect(note('n4')).toBeNull();
    expect(note('n5')).toHaveTextContent('Tekst z serwera');

    fireEvent.click(screen.getByLabelText('switch-ru'));
    await waitFor(() => expect(note('n1')).toHaveTextContent(CLEAN_RU));
    expect(note('n3')).toHaveTextContent(CLEAN_RU);
    expect(note('n2')).toHaveTextContent('Notatka właściciela'); // owner edit never translated
    expect(note('n4')).toBeNull();
    expect(note('n5')).toHaveTextContent('Tekst z serwera');     // unknown key -> stored text
    expect(within(screen.getByLabelText('process-steps')).getAllByRole('listitem')).toHaveLength(5);
  });

  it('RU from the start; custom template notes stay verbatim', async () => {
    localStorage.setItem('locale', 'ru');
    renderManager();
    fireEvent.click(await screen.findByLabelText('process-card-tpl-notes'));
    expect(note('n1')).toHaveTextContent(CLEAN_RU);
    fireEvent.click(screen.getByLabelText('process-detail-back'));
    fireEvent.click(await screen.findByLabelText('process-card-tpl-cnote'));
    expect(note('c1')).toHaveTextContent('Moja notatka');
  });
});
