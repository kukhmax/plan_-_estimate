export type AccessStatus = 'PENDING' | 'ACTIVE' | 'BLOCKED';

export interface AccessEntry {
  id: string;
  telegram_user_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  status: AccessStatus;
  is_admin: boolean;
  created_at: string;
  decided_at: string | null;
}

export interface AccessSettings {
  closed: boolean;
  contact: string;
}

export interface AccessOverview {
  settings: AccessSettings;
  entries: AccessEntry[];
}
