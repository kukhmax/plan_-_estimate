export type ProjectStatus = 'PLANNING' | 'IN_PROGRESS' | 'COMPLETED';

export interface ProjectType {
  id: string;
  owner_id: string;
  client_id: string | null;
  name: string;
  address: string;
  city: string;
  postal_code: string;
  description: string | null;
  status: ProjectStatus;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  items: ProjectType[];
  total: number;
}

export interface ProjectCreatePayload {
  name: string;
  address: string;
  city: string;
  postal_code: string;
  description?: string | null;
  status?: ProjectStatus;
  client_id?: string | null;
}

export interface ProjectUpdatePayload {
  name?: string;
  address?: string;
  city?: string;
  postal_code?: string;
  description?: string | null;
  status?: ProjectStatus;
  client_id?: string | null;
}
