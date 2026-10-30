import { apiRequest } from './http';
import {
  ChecklistTemplate,
  ChecklistTemplateListResponse,
} from '../types/checklist';

function templatesPath(): string {
  return '/api/checklist-templates';
}

/** `forFloor`: the templates a floor is inspected with (the floor variants of concrete / old paint / other and the substrates of the floor only), else the ones of walls and ceilings. */
export function fetchChecklistTemplates(
  substrate?: string,
  options?: { forFloor?: boolean },
): Promise<ChecklistTemplateListResponse> {
  const params = new URLSearchParams();
  if (substrate) params.set('substrate', substrate);
  if (options?.forFloor) params.set('for_floor', 'true');
  const query = params.toString();
  return apiRequest(`${templatesPath()}${query ? `?${query}` : ''}`);
}

export function fetchChecklistTemplate(
  templateId: string,
): Promise<ChecklistTemplate> {
  return apiRequest(`${templatesPath()}/${templateId}`);
}