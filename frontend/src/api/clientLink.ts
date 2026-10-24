import type {
  ClientJournal,
  ClientLinkIssued,
  ClientLinkStatus,
  ClientProposal,
  ClientProposalInput,
  ClientProposalList,
} from '../types/clientLink';
import type { Locale } from '../utils/locale';
import { apiRequest } from './http';

const base = (projectId: string) => `/api/projects/${encodeURIComponent(projectId)}`;

export function fetchClientLink(projectId: string): Promise<ClientLinkStatus> {
  return apiRequest(`${base(projectId)}/client-link`);
}

export function createClientLink(projectId: string, language: Locale): Promise<ClientLinkIssued> {
  return apiRequest(`${base(projectId)}/client-link`, { method: 'POST', body: JSON.stringify({ language }) });
}

export function extendClientLink(projectId: string): Promise<ClientLinkStatus> {
  return apiRequest(`${base(projectId)}/client-link/extend`, { method: 'POST' });
}

export function revokeClientLink(projectId: string): Promise<void> {
  return apiRequest(`${base(projectId)}/client-link`, { method: 'DELETE' });
}

export function listClientProposals(projectId: string): Promise<ClientProposalList> {
  return apiRequest(`${base(projectId)}/client-proposals`);
}

export function createClientProposal(projectId: string, input: ClientProposalInput): Promise<ClientProposal> {
  return apiRequest(`${base(projectId)}/client-proposals`, { method: 'POST', body: JSON.stringify(input) });
}

export function withdrawClientProposal(projectId: string, proposalId: string): Promise<ClientProposal> {
  return apiRequest(`${base(projectId)}/client-proposals/${encodeURIComponent(proposalId)}/withdraw`, { method: 'POST' });
}

export function fetchClientJournal(projectId: string): Promise<ClientJournal> {
  return apiRequest(`${base(projectId)}/client-journal`);
}
