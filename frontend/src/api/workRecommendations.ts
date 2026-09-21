import { apiRequest } from './http';
import {
  WorkRecommendationAcceptRequest,
  WorkRecommendationActivityValue,
  WorkRecommendationEvaluateResponse,
  WorkRecommendationListResponse,
  WorkRecommendationRead,
} from '../types/workRecommendation';

function recommendationsPath(projectId: string, roomId: string): string {
  return `/api/projects/${projectId}/rooms/${roomId}/work-recommendations`;
}

function recommendationPath(projectId: string, recommendationId: string): string {
  return `/api/projects/${projectId}/work-recommendations/${recommendationId}`;
}

export function fetchWorkRecommendations(
  projectId: string,
  roomId: string,
  { activity }: { activity?: WorkRecommendationActivityValue } = {},
): Promise<WorkRecommendationListResponse> {
  const params = new URLSearchParams();
  // "all" must be sent explicitly, not dropped: the backend defaults to active
  // when the activity query parameter is absent.
  if (activity) params.set('activity', activity);
  const query = params.toString();
  return apiRequest(`${recommendationsPath(projectId, roomId)}${query ? `?${query}` : ''}`);
}

export function evaluateWorkRecommendations(
  projectId: string,
  roomId: string,
): Promise<WorkRecommendationEvaluateResponse> {
  return apiRequest(`${recommendationsPath(projectId, roomId)}/evaluate`, {
    method: 'POST',
  });
}

export function dismissWorkRecommendation(
  projectId: string,
  recommendationId: string,
): Promise<WorkRecommendationRead> {
  return apiRequest(`${recommendationPath(projectId, recommendationId)}/dismiss`, {
    method: 'POST',
  });
}

export function reconsiderWorkRecommendation(
  projectId: string,
  recommendationId: string,
): Promise<WorkRecommendationRead> {
  return apiRequest(`${recommendationPath(projectId, recommendationId)}/reconsider`, {
    method: 'POST',
  });
}

export function acceptWorkRecommendation(
  projectId: string,
  recommendationId: string,
  payload: WorkRecommendationAcceptRequest = {},
): Promise<WorkRecommendationRead> {
  return apiRequest(`${recommendationPath(projectId, recommendationId)}/accept`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
