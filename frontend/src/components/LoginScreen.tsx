import { FormEvent, useState } from 'react';
import { PasswordLoginError } from '../api/auth';
import { useI18n } from '../hooks/useI18n';

interface LoginScreenProps {
  /** Signs in; a refusal is thrown (`PasswordLoginError`) and told under the fields. */
  onSubmit: (email: string, password: string) => Promise<void>;
}

/**
 * The sign-in of an account that has no Telegram (V2-1): an e-mail and a password, for an application opened in an ordinary browser.
 * Shown only when the server says the sign-in by password is switched on; inside Telegram nothing changes.
 */
export function LoginScreen({ onSubmit }: LoginScreenProps) {
  const { t } = useI18n();
  const text = t.auth.login;
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const explain = (error: unknown): string => {
    if (!(error instanceof PasswordLoginError)) return text.failed;
    if (error.code === 'INVALID_CREDENTIALS') return text.invalid;
    if (error.code === 'ACCOUNT_LOCKED') return text.locked.replace('{minutes}', String(Math.max(1, Math.ceil((error.retryAfterSeconds ?? 60) / 60))));
    if (error.code === 'PASSWORD_LOGIN_DISABLED') return text.disabled;
    if (error.code === 'ACCESS_BLOCKED') return t.auth.errors.access_blocked;
    if (error.code === 'ACCESS_DENIED') return t.auth.errors.access_denied;
    if (error.status === 0 || error.status >= 500) return text.unavailable;
    return text.failed;
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !email.trim() || !password) return;
    setBusy(true);
    setMessage(null);
    try {
      await onSubmit(email.trim(), password);
    } catch (error) {
      setMessage(explain(error));
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  const field =
    'w-full min-h-11 rounded-xl border px-3 py-2 text-base bg-[var(--tg-control-bg-color)] text-[var(--tg-control-text-color)] border-[var(--tg-control-border-color)]';

  return (
    <form
      aria-label="login-form"
      onSubmit={(event) => void submit(event)}
      className="w-full rounded-2xl p-5 border border-slate-200 shadow-sm space-y-3"
      style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }}
    >
      <h2 className="text-lg font-semibold break-words">{text.title}</h2>
      <p className="text-sm break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.hint}</p>

      <label className="block text-sm font-medium">
        {text.email}
        <input
          aria-label="login-email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className={`mt-1 ${field}`}
        />
      </label>

      <label className="block text-sm font-medium">
        {text.password}
        <div className="mt-1 flex items-stretch gap-2">
          <input
            aria-label="login-password"
            type={visible ? 'text' : 'password'}
            autoComplete="current-password"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={`min-w-0 flex-1 ${field}`}
          />
          <button
            type="button"
            aria-label="login-password-toggle"
            aria-pressed={visible}
            title={visible ? text.hide_password : text.show_password}
            onClick={() => setVisible((value) => !value)}
            className="shrink-0 min-h-11 min-w-11 rounded-xl border text-lg border-[var(--tg-control-border-color)]"
          >
            <span aria-hidden="true">{visible ? '🙈' : '👁'}</span>
          </button>
        </div>
      </label>

      {message && (
        <p role="alert" aria-label="login-error" className="text-sm font-medium text-red-600 break-words">
          {message}
        </p>
      )}

      <button
        type="submit"
        aria-label="login-submit"
        disabled={busy || !email.trim() || !password}
        className="w-full min-h-11 rounded-xl text-sm font-semibold disabled:opacity-50"
        style={{ backgroundColor: 'var(--tg-theme-button-color)', color: 'var(--tg-theme-button-text-color)' }}
      >
        {busy ? text.signing_in : text.submit}
      </button>
    </form>
  );
}
