import { useEffect } from 'react';
import { useI18n } from '../hooks/useI18n';
import { User } from '../types/auth';

interface AccountModalProps {
  user: User;
  isDevAuth: boolean;
  onClose: () => void;
}

export function AccountModal({ user, isDevAuth, onClose }: AccountModalProps) {
  const { t } = useI18n();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const displayName =
    user.first_name || user.last_name
      ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
      : user.username || '—';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.45)' }}
      aria-modal="true"
      role="dialog"
      aria-label={t.auth.account_title}
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-2xl p-5 shadow-xl border border-slate-200"
        style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)' }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <span
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: 'var(--tg-theme-hint-color)' }}
            >
              {t.auth.account_title}
            </span>
            <h2
              className="text-lg font-bold break-words"
              style={{ color: 'var(--tg-theme-text-color)' }}
            >
              {displayName}
            </h2>
          </div>
          <button
            type="button"
            aria-label="close-account-modal"
            onClick={onClose}
            className="min-h-11 min-w-11 flex items-center justify-center rounded-xl border text-xl font-semibold transition shrink-0"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              color: 'var(--tg-theme-hint-color)',
              borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))',
            }}
          >
            ×
          </button>
        </div>

        <div className="mt-1 mb-4">
          <span
            className={`inline-flex items-center px-2.5 py-1 text-xs rounded-full font-semibold ${
              isDevAuth ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
            }`}
          >
            {isDevAuth ? t.auth.mock_auth : t.auth.telegram_verified}
          </span>
        </div>

        <dl className="space-y-3 text-sm">
          <div className="flex flex-col gap-0.5">
            <dt
              className="text-xs font-medium"
              style={{ color: 'var(--tg-theme-hint-color)' }}
            >
              {t.auth.telegram_user_id}
            </dt>
            <dd
              className="font-mono font-medium break-all"
              style={{ color: 'var(--tg-theme-text-color)' }}
            >
              {user.telegram_user_id}
            </dd>
          </div>

          {user.username && (
            <div className="flex flex-col gap-0.5">
              <dt
                className="text-xs font-medium"
                style={{ color: 'var(--tg-theme-hint-color)' }}
              >
                {t.auth.username}
              </dt>
              <dd
                className="font-medium break-all"
                style={{ color: 'var(--tg-theme-link-color)' }}
              >
                @{user.username}
              </dd>
            </div>
          )}

          <div className="flex flex-col gap-0.5">
            <dt
              className="text-xs font-medium"
              style={{ color: 'var(--tg-theme-hint-color)' }}
            >
              {t.auth.uuid}
            </dt>
            <dd
              className="font-mono text-xs break-all"
              style={{ color: 'var(--tg-theme-hint-color)' }}
            >
              {user.id}
            </dd>
          </div>
        </dl>

        <button
          type="button"
          onClick={onClose}
          className="min-h-11 w-full mt-5 text-sm font-semibold rounded-xl border border-slate-200 transition"
          style={{
            backgroundColor: 'var(--tg-theme-secondary-bg-color)',
            color: 'var(--tg-theme-text-color)',
            borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))',
          }}
        >
          {t.common.close}
        </button>
      </div>
    </div>
  );
}