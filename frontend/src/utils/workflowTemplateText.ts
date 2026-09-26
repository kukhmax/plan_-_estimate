import { WorkflowTemplateRead, WorkflowTemplateStepRead } from '../types/workflowTemplate';
import { resolveKey } from './i18nKeys';

/**
 * Description to show for a workflow template (Stage 13F.3 FIX.1).
 *
 * The server sets `description_key` only for an untouched canonical built-in
 * description; it is then localized (PL/RU) like built-in names. Custom
 * templates and owner-edited built-in descriptions have no key and are shown
 * exactly as stored -- user content is never translated. A key the locale
 * does not know falls back to the stored text.
 */
export function templateDescription(t: unknown, tpl: WorkflowTemplateRead): string | null {
  return localizedOrStored(t, tpl.description_key, tpl.description);
}

/**
 * Note to show for one template step (Stage 13F.3 FIX.2). Same rule as the
 * description: `note_key` is set by the server only while the step's note is
 * exactly a canonical built-in note of that default recipe; edited notes and
 * custom templates are shown verbatim. Per step, so repeated PriceItems are
 * independent.
 */
export function templateStepNote(t: unknown, step: WorkflowTemplateStepRead): string | null {
  return localizedOrStored(t, step.note_key, step.note);
}

function localizedOrStored(t: unknown, key: string | null | undefined, stored: string | null): string | null {
  if (key) {
    const localized = resolveKey(t, key);
    if (localized !== key) return localized;
  }
  return stored;
}
