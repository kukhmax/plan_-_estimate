export interface User {
  id: string;
  telegram_user_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  language_code: string | null;
  created_at: string;
  updated_at: string;
  /** closed registration: may open the screen of the access list */
  is_admin?: boolean;
}

export interface TelegramAuthResponse {
  access_token: string;
  token_type: string;
  user: User;
  is_dev_auth: boolean;
}

/** What the sign-in screen needs before anyone is signed in (V2-1). */
export interface AuthConfig {
  password_login: boolean;
}
