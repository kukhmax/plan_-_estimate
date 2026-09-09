export interface RoomType {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface RoomListResponse {
  items: RoomType[];
  total: number;
}

export interface RoomCreatePayload {
  name: string;
  description?: string | null;
}

export interface RoomUpdatePayload {
  name?: string;
  description?: string | null;
}
