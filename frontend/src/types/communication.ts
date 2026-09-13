/**
 * Materialized client-communication applications of a COMPLETED inspection
 * (Stage 8 "Co powiedzieć klientowi"). DTOs mirror backend schemas; all
 * selection/versioning/identity decisions stay on the backend.
 */

import { RiskSeverityValue, RiskSourceFindingRead } from './risk';

export type CommunicationCategoryValue =
  | 'EXPLAIN_CONDITION'
  | 'EXPLAIN_CONSEQUENCE'
  | 'RECOMMEND_PREPARATION'
  | 'REQUIRE_CLIENT_DECISION'
  | 'SCOPE_CLARIFICATION'
  | 'QUALITY_EXPECTATION'
  | 'DOCUMENT_AGREEMENT'
  | 'GENERAL';

export type CommunicationStatusValue = 'active' | 'resolved' | 'all';

export type CommunicationSourceKind = 'RISK' | 'FINDING' | 'QUALITY';

export interface CommunicationApplicationRead {
  id: string;
  inspection_id: string;
  phrase_code: string;
  phrase_version: number;
  category: CommunicationCategoryValue;
  priority: number;
  phrase_key: string;
  why_key: string | null;
  seed_key: string | null;
  source_kind: CommunicationSourceKind;
  source_signature: string;
  is_active: boolean;
  resolved_at: string | null;
  position: number | null;
  created_at: string;
  updated_at: string;
}

export interface CommunicationRiskSource {
  kind: 'RISK';
  risk_id: string | null;
  risk_code: string | null;
  severity: RiskSeverityValue | null;
  risk_is_active: boolean | null;
  source_findings: RiskSourceFindingRead[];
}

export interface CommunicationFindingSnapshot {
  finding_id: string;
  label_key: string | null;
  value_snapshot: Record<string, unknown> | null;
  is_active: boolean;
  position: number | null;
}

export interface CommunicationFindingSource {
  kind: 'FINDING';
  finding_key: string;
  findings: CommunicationFindingSnapshot[];
}

export interface CommunicationQualitySource {
  kind: 'QUALITY';
  substrate: string | null;
  quality_level: string | null;
}

export type CommunicationSource =
  | CommunicationRiskSource
  | CommunicationFindingSource
  | CommunicationQualitySource;

export interface CommunicationApplicationDetailRead
  extends CommunicationApplicationRead {
  source: CommunicationSource;
}

export interface CommunicationListResponse {
  items: CommunicationApplicationRead[];
  total: number;
}