export interface ClientType {
  id: string;
  owner_user_id: string;
  client_type: 'PRIVATE_PERSON' | 'COMPANY';
  first_name: string | null;
  last_name: string | null;
  company_name: string | null;
  phone: string | null;
  email: string | null;
  nip: string | null;
  notes: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClientListResponse {
  items: ClientType[];
  total: number;
}

export interface ClientCreatePayload {
  client_type: 'PRIVATE_PERSON' | 'COMPANY';
  first_name?: string;
  last_name?: string;
  company_name?: string;
  phone?: string;
  email?: string;
  nip?: string;
  notes?: string;
}

export interface ClientUpdatePayload {
  client_type?: 'PRIVATE_PERSON' | 'COMPANY';
  first_name?: string;
  last_name?: string;
  company_name?: string;
  phone?: string;
  email?: string;
  nip?: string;
  notes?: string;
}
