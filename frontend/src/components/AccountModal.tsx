import { useEffect, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { User } from '../types/auth';
import { ExecutorProfileModal } from './ExecutorProfileModal';
import { Ico } from './Ico';
import { usePhotoUploadQueue } from '../hooks/usePhotoUploadQueue';
import { useOutboxCounts } from '../offline/outboxState';
import { clearOfflineData } from '../offline/readCache';

interface AccountModalProps {
  user: User;
  isDevAuth: boolean;
  onClose: () => void;
}

export function AccountModal({ user, isDevAuth, onClose }: AccountModalProps) {
  const { t } = useI18n();
  const [showProfile, setShowProfile] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const { pending, failed } = useOutboxCounts();
  // photos that wait on the phone are lost by the removal as well (Stage 19D)
  const waitingPhotos = usePhotoUploadQueue().items.filter((entry) => entry.state !== 'done' && entry.state !== 'canceled').length;
  const [cleared, setCleared] = useState(false);

  // Escape and the Telegram BackButton close the top-most layer: the profile screen first, then this dialog.
  const closeTop = () => (showProfile ? setShowProfile(false) : onClose());
  useTelegramBackButton(true, closeTop);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (showProfile) setShowProfile(false);
      else onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, showProfile]);

  const displayName =
    user.first_name || user.last_name
      ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
      : user.username || '—';

  return (
    <>
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
          {/* Stage 19B: what the phone keeps for work without a signal can be removed here (the objects stay on the server) */}
          <div className="mt-4 space-y-2 border-t border-slate-200 pt-3" aria-label="offline-data">
            <p className="text-xs break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>{t.offline.clear_note}</p>
            {confirmClear ? (
              <div className="space-y-2">
                <p className="text-sm font-semibold break-words" style={{ color: 'var(--tg-theme-text-color)' }}>{t.offline.clear_confirm}</p>
                {pending + failed > 0 && (
                  <p role="alert" aria-label="clear-offline-pending" className="text-xs font-semibold text-red-700 break-words">
                    {t.offline.clear_pending.replace('{n}', String(pending + failed))}
                  </p>
                )}
                {waitingPhotos > 0 && (
                  <p role="alert" aria-label="clear-offline-photos" className="text-xs font-semibold text-red-700 break-words">
                    {t.offline.clear_pending_photos.replace('{n}', String(waitingPhotos))}
                  </p>
                )}
                <div className="flex gap-2">
                  <button type="button" aria-label="clear-offline-cancel" onClick={() => setConfirmClear(false)} className="flex-1 min-h-10 px-3 py-1 text-sm rounded-xl border border-slate-200 bg-white text-slate-700 font-medium">
                    <Ico>✖️</Ico>{t.common.cancel}
                  </button>
                  <button
                    type="button"
                    aria-label="clear-offline-confirm"
                    onClick={() => {
                      void clearOfflineData().then(() => {
                        setConfirmClear(false);
                        setCleared(true);
                      });
                    }}
                    className="flex-1 min-h-10 px-3 py-1 text-sm rounded-xl bg-red-600 text-white font-semibold"
                  >
                    <Ico>🗑️</Ico>{t.offline.clear_yes}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                aria-label="clear-offline-button"
                onClick={() => {
                  setCleared(false);
                  setConfirmClear(true);
                }}
                className="w-full min-h-10 px-3 py-1 text-sm rounded-xl border border-slate-200 bg-white text-slate-700 font-medium"
              >
                <Ico>🧹</Ico>{t.offline.clear_button}
              </button>
            )}
            {cleared && <p role="status" className="text-xs font-medium text-emerald-700">{t.offline.cleared}</p>}
          </div>

          <button
            type="button"
            onClick={() => setShowProfile(true)}
            className="min-h-11 w-full mt-5 px-3 text-sm font-semibold rounded-xl break-words"
            style={{
              backgroundColor: 'var(--tg-theme-button-color)',
              color: 'var(--tg-theme-button-text-color)',
            }}
          >
            <Ico>👷</Ico>{t.executor_profile.button}
          </button>

          <button
            type="button"
            onClick={onClose}
            className="min-h-11 w-full mt-2 text-sm font-semibold rounded-xl border border-slate-200 transition"
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              color: 'var(--tg-theme-text-color)',
              borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))',
            }}
          >
            <Ico>✖️</Ico>{t.common.close}
          </button>
        </div>
      </div>
      {/* A sibling, not a child: clicks inside the profile screen must not reach this dialog's backdrop. */}
      {showProfile && <ExecutorProfileModal onClose={() => setShowProfile(false)} />}
    </>
  );
}