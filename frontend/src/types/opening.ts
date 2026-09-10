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
}

export interface OpeningUpdatePayload {
  opening_type?: OpeningTypeValue;
  name?: string | null;
  width?: number | string;
  height?: number | string;
  quantity?: number;
  description?: string | null;
}
