export interface TelegramUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
}

export interface TelegramThemeParams {
  bg_color?: string;
  secondary_bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  header_bg_color?: string;
  bottom_bar_bg_color?: string;
  accent_text_color?: string;
  section_bg_color?: string;
  section_header_text_color?: string;
  subtitle_text_color?: string;
  destructive_text_color?: string;
  [key: string]: string | undefined;
}

export interface TelegramBackButton {
  isVisible: boolean;
  show: () => void;
  hide: () => void;
  onClick: (callback: () => void) => void;
  offClick: (callback: () => void) => void;
}

export interface TelegramHapticFeedback {
  notificationOccurred?: (type: 'error' | 'success' | 'warning') => void;
  impactOccurred?: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void;
  selectionChanged?: () => void;
}

/** What the Mini App sees of the storages of Telegram (EN-1 spike): each is optional, the older clients of Telegram do not have them. */
type StorageCallback<T> = (error: string | null, value?: T, extra?: unknown) => void;

export interface TelegramCloudStorage {
  setItem: (key: string, value: string, callback?: StorageCallback<boolean>) => void;
  getItem: (key: string, callback: StorageCallback<string>) => void;
  removeItem: (key: string, callback?: StorageCallback<boolean>) => void;
  getKeys: (callback: StorageCallback<string[]>) => void;
}

/** DeviceStorage and SecureStorage (Bot API 9.0): the same shape; the secure one lives in the Keychain / Keystore of the phone. */
export interface TelegramKeyStorage {
  setItem: (key: string, value: string, callback?: StorageCallback<boolean>) => void;
  getItem: (key: string, callback: StorageCallback<string>) => void;
  removeItem: (key: string, callback?: StorageCallback<boolean>) => void;
  clear?: (callback?: StorageCallback<boolean>) => void;
  restoreItem?: (key: string, callback?: StorageCallback<string>) => void;
}

export interface TelegramBiometricManager {
  isInited: boolean;
  isBiometricAvailable: boolean;
  biometricType: 'finger' | 'face' | 'unknown';
  isAccessRequested: boolean;
  isAccessGranted: boolean;
  isBiometricTokenSaved: boolean;
  deviceId: string;
  init: (callback?: () => void) => void;
  requestAccess: (params: { reason?: string }, callback?: (granted: boolean) => void) => void;
  authenticate: (params: { reason?: string }, callback?: (success: boolean, token?: string) => void) => void;
}

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    query_id?: string;
    user?: TelegramUser;
    auth_date?: string;
    hash?: string;
  };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  themeParams: TelegramThemeParams;
  isExpanded: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  BackButton?: TelegramBackButton;
  /** Bot API 8.0: the native "download a file" sheet; the client downloads the address itself (owner 2026-10-31: PDF in the application). */
  downloadFile?: (params: { url: string; file_name: string }, callback?: (accepted: boolean) => void) => void;
  CloudStorage?: TelegramCloudStorage;
  DeviceStorage?: TelegramKeyStorage;
  SecureStorage?: TelegramKeyStorage;
  BiometricManager?: TelegramBiometricManager;
  isVersionAtLeast?: (version: string) => boolean;
  HapticFeedback?: TelegramHapticFeedback;
  ready: () => void;
  expand: () => void;
  close: () => void;
  /** Opens a link outside the Mini App (the browser of the phone). */
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void;
  /** Opens a t.me link inside Telegram (a share dialog: `https://t.me/share/url?url=...`). */
  openTelegramLink?: (url: string) => void;
  onEvent?: (eventType: string, eventHandler: (payload?: unknown) => void) => void;
  offEvent?: (eventType: string, eventHandler: (payload?: unknown) => void) => void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}
