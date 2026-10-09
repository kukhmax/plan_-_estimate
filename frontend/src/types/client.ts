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
  /** Address of the customer for contracts and protocols (Stage 16B.1); the postal code is stored as `00-000`. */
  street: string | null;
  postal_code: string | null;
  city: string | null;
  /** Contact field only — never Telegram Mini App auth identity. Stored as "@username". */
  telegram_username: string | null;
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
  street?: string;
  postal_code?: string;
  city?: string;
  telegram_username?: string;
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
  /** null explicitly clears the address part (an empty field on the edit form); omit to leave unchanged. */
  street?: string | null;
  postal_code?: string | null;
  city?: string | null;
  /** null explicitly clears it back to unset; omit to leave unchanged. */
  telegram_username?: string | null;
  notes?: string;
}
