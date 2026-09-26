/**
 * Stage 13F.3 FIX.3 — real-contract regression.
 *
 * `workflowTemplate.TECH_BETON_S4-01.json` is the actual endpoint serializer
 * output for the seeded TECH_BETON_S4-01 of the local dev database (ids
 * anonymized), not a hand-built fixture. The backend test
 * `TestRealContractFixture` asserts the fixture's localization keys still
 * equal what the API returns for a freshly seeded owner.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as templatesApi from '../api/workflowTemplates';
import { I18nProvider } from '../hooks/useI18n';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { WorkflowTemplateRead } from '../types/workflowTemplate';
import { WorkflowTemplateManager } from './WorkflowTemplateManager';
import realS4 from '../__fixtures__/workflowTemplate.TECH_BETON_S4-01.json';

vi.mock('../api/workflowTemplates', async (orig) => ({
  ...(await orig<typeof import('../api/workflowTemplates')>()),
  fetchWorkflowTemplates: vi.fn(),
}));

const real = realS4 as unknown as WorkflowTemplateRead;

const leaf = (key: string) => key.split('.').pop() as string;
type Texts = { description: Record<string, string>; step_note: Record<string, string> };
const PL = pl.workflow_templates as unknown as Texts;
const RU = ru.workflow_templates as unknown as Texts;

describe('Real API contract: TECH_BETON_S4-01 localization (13F.3 FIX.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(templatesApi.fetchWorkflowTemplates).mockResolvedValue({ items: [real], total: 1 });
  });

  it('the captured response carries description_key and a note_key for every noted step', () => {
    expect(real.code).toBe('TECH_BETON_S4-01');
    expect(real.description_key).toBe('workflow_templates.description.s4');
    const noted = real.steps.filter((s) => s.note);
    expect(noted.length).toBe(real.steps.length);
    for (const step of noted) expect(step.note_key).toMatch(/^workflow_templates\.step_note\./);
    // every requested key exists in BOTH locales under the path the app resolves
    expect(PL.description[leaf(real.description_key!)]).toBe(real.description);
    expect(RU.description[leaf(real.description_key!)]).toBeTruthy();
    for (const step of noted) {
      expect(PL.step_note[leaf(step.note_key!)]).toBe(step.note);
      expect(RU.step_note[leaf(step.note_key!)]).toBeTruthy();
    }
  });

  it('RU detail shows the Russian description and Russian notes, no Polish canonical text', async () => {
    localStorage.setItem('locale', 'ru');
    render(<I18nProvider><WorkflowTemplateManager /></I18nProvider>);
    fireEvent.click(await screen.findByLabelText(`process-card-${real.id}`));
    const detail = screen.getByLabelText(`process-detail-${real.id}`);
    expect(within(detail).getByLabelText('process-description')).toHaveTextContent(RU.description.s4);
    for (const step of real.steps) {
      expect(screen.getByLabelText(`process-step-note-${step.id}`)).toHaveTextContent(RU.step_note[leaf(step.note_key!)]);
    }
    expect(detail).not.toHaveTextContent('Standard Wykończenia Powierzchni');
    expect(detail).not.toHaveTextContent('Zabezpieczenie podłóg');
    expect(detail).not.toHaveTextContent('Kolejny etap po całkowitym wyschnięciu');
  });

  it('PL detail shows the canonical Polish texts', async () => {
    render(<I18nProvider><WorkflowTemplateManager /></I18nProvider>);
    fireEvent.click(await screen.findByLabelText(`process-card-${real.id}`));
    expect(screen.getByLabelText('process-description')).toHaveTextContent(real.description!);
    expect(screen.getByLabelText(`process-step-note-${real.steps[0].id}`)).toHaveTextContent(real.steps[0].note!);
  });

  it('without the keys (a backend that predates FIX.1/FIX.2) the stored Polish text is shown -- the observed symptom', async () => {
    localStorage.setItem('locale', 'ru');
    const stale: WorkflowTemplateRead = {
      ...real, description_key: undefined, steps: real.steps.map((s) => ({ ...s, note_key: undefined })),
    };
    vi.mocked(templatesApi.fetchWorkflowTemplates).mockResolvedValue({ items: [stale], total: 1 });
    render(<I18nProvider><WorkflowTemplateManager /></I18nProvider>);
    fireEvent.click(await screen.findByLabelText(`process-card-${real.id}`));
    expect(screen.getByLabelText('process-description')).toHaveTextContent('Standard Wykończenia Powierzchni S4');
  });
});
