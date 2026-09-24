export type CoefficientSelectionMode = 'SINGLE_SELECT';

export interface CoefficientOptionRead {
  id: string;
  group_id: string;
  code: string;
  name_key: string | null;
  display_name: string | null;
  percentage: string;
  is_base: boolean;
  position: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CoefficientGroupRead {
  id: string;
  code: string;
  name_key: string | null;
  display_name: string | null;
  selection_mode: CoefficientSelectionMode;
  position: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  options: CoefficientOptionRead[];
}

export interface CoefficientGroupListResponse {
  items: CoefficientGroupRead[];
  total: number;
}

export interface CoefficientGroupCreatePayload {
  display_name: string;
}

export interface CoefficientGroupUpdatePayload {
  display_name?: string;
  position?: number;
}

export interface CoefficientOptionCreatePayload {
  display_name: string;
  percentage: string;
  is_base?: boolean;
}

export interface CoefficientOptionUpdatePayload {
  display_name?: string;
  percentage?: string;
  is_base?: boolean;
}
