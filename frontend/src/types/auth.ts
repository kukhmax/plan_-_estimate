export interface User {
  id: string;
  telegram_user_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  language_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface TelegramAuthResponse {
  access_token: string;
  token_type: string;
  user: User;
  is_dev_auth: boolean;
}
