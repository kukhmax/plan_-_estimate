/** Materialized deterministic risks of a COMPLETED inspection (Stage 7). */

export type RiskSeverityValue = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type RiskStatusValue = 'active' | 'resolved' | 'all';

export interface RiskRead {
  id: string;
  room_id: string;
  inspection_id: string;
  risk_code: string;
  rule_code: string;
  rule_version: number;
  severity: RiskSeverityValue;
  title_key: string;
  explanation_key: string;
  consequence_key: string;
  mitigation_key: string;
  communication_key: string;
  warranty_exclusion_candidate: boolean;
  blocks_finishing: boolean;
  source_signature: string;
  is_active: boolean;
  resolved_at: string | null;
  position: number | null;
  created_at: string;
  updated_at: string;
}

export interface RiskSourceFindingRead {
  finding_id: string | null;
  finding_key_snapshot: string;
  value_snapshot: Record<string, unknown> | null;
  position: number | null;
}

export interface RiskDetail extends RiskRead {
  source_findings: RiskSourceFindingRead[];
}

export interface RiskEvaluateRequest {
  inspection_id: string;
}

export interface RiskListResponse {
  items: RiskRead[];
  total: number;
}

export interface RiskDetailResponse {
  items: RiskDetail[];
  total: number;
}