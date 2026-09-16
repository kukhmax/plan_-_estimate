export type OpeningTypeValue = 'DOOR' | 'WINDOW' | 'OTHER';

export interface OpeningType {
  id: string;
  surface_id: string;
  opening_type: OpeningTypeValue;
  name: string | null;
  width: string | number;
  height: string | number;
  quantity: number;
  single_area: string | number | null;
  total_area: string | number | null;
  description: string | null;
  reveal_enabled: boolean;
  reveal_depth: string | number | null;
  reveal_left: boolean;
  reveal_right: boolean;
  reveal_top: boolean;
  reveal_bottom: boolean;
  reveal_single_length: string | number | null;
  reveal_single_area: string | number | null;
  reveal_total_length: string | number | null;
  reveal_total_area: string | number | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface OpeningListResponse {
  items: OpeningType[];
  total: number;
}

export interface OpeningCreatePayload {
  opening_type: OpeningTypeValue;
  name?: string | null;
  width: number | string;
  height: number | string;
  quantity?: number;
  description?: string | null;
  reveal_enabled?: boolean;
  reveal_depth?: number | string | null;
  reveal_left?: boolean;
  reveal_right?: boolean;
  reveal_top?: boolean;
  reveal_bottom?: boolean;
}

export interface OpeningUpdatePayload {
  opening_type?: OpeningTypeValue;
  name?: string | null;
  width?: number | string;
  height?: number | string;
  quantity?: number;
  description?: string | null;
  reveal_enabled?: boolean;
  reveal_depth?: number | string | null;
  reveal_left?: boolean;
  reveal_right?: boolean;
  reveal_top?: boolean;
  reveal_bottom?: boolean;
}
