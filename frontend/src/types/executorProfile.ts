/** Stage 15C — the executor (contractor) profile printed in the header of every document. */
export interface ExecutorProfile {
  id: string;
  name: string;
  nip: string | null;
  street: string | null;
  postal_code: string | null;
  city: string | null;
  phone: string | null;
  email: string | null;
  bank_account: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExecutorProfileResponse {
  profile: ExecutorProfile | null;
}

/** PUT replaces the whole profile: a field that is not sent is cleared. */
export interface ExecutorProfilePayload {
  name: string;
  nip: string;
  street: string;
  postal_code: string;
  city: string;
  phone: string;
  email: string;
  bank_account: string;
}

export type ExecutorProfileField = keyof ExecutorProfilePayload;

/** Codes the backend puts in `detail.fields` of a 422 EXECUTOR_PROFILE_INVALID. */
export type ExecutorProfileFieldCode =
  | 'NAME_REQUIRED'
  | 'NIP_INVALID'
  | 'POSTAL_CODE_INVALID'
  | 'EMAIL_INVALID'
  | 'PHONE_INVALID'
  | 'BANK_ACCOUNT_INVALID';
