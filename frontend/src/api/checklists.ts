import { apiRequest } from './http';
import {
  ChecklistTemplate,
  ChecklistTemplateListResponse,
} from '../types/checklist';

function templatesPath(): string {
  return '/api/checklist-templates';
}

export function fetchChecklistTemplates(
  substrate?: string,
): Promise<ChecklistTemplateListResponse> {
  const query = substrate ? `?substrate=${encodeURIComponent(substrate)}` : '';
  return apiRequest(`${templatesPath()}${query}`);
}

export function fetchChecklistTemplate(
  templateId: string,
): Promise<ChecklistTemplate> {
  return apiRequest(`${templatesPath()}/${templateId}`);
}