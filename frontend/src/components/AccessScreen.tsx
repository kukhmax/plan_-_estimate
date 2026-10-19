import { useCallback, useEffect, useState } from 'react';
import { decideAccess, fetchAccess, removeAccess, saveAccessSettings } from '../api/access';
import { useI18n } from '../hooks/useI18n';
import type { AccessEntry, AccessOverview, AccessStatus } from '../types/access';

const button = 'w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-slate-300 bg-white text-slate-900 hover:bg-slate-50 disabled:opacity-50 transition break-words';
const primary = 'w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition break-words';
const GROUPS: AccessStatus[] = ['PENDING', 'ACTIVE', 'BLOCKED'];

/**
 * The access list (closed registration): the administrator sees who asked to enter, admits or blocks an account, and closes or opens the
 * registration. A person who is refused sees the contact text written here. Mobile first: one column, large buttons, nothing side by side.
 */
export function AccessScreen() {
  const { t, locale } = useI18n();
  const text = t.access;
  const [overview, setOverview] = useState<AccessOverview | null>(null);
  const [failed, setFailed] = useState<'load' | 'save' | null>(null);
  const [busy, setBusy] = useState(false);
  const [contact, setContact] = useState('');
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setFailed(null);
    try {
      const value = await fetchAccess();
      setOverview(value);
      setContact(value.settings.contact);
    } catch {
      setFailed('load');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (work: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    setFailed(null);
    setSaved(false);
    try {
      await work();
      const value = await fetchAccess();
      setOverview(value);
      setContact(value.settings.contact);
    } catch {
      setFailed('save');
    } finally {
      setBusy(false);
    }
  };

  const toggleClosed = (closed: boolean) => act(() => saveAccessSettings({ closed }));
  const saveContact = () =>
    act(async () => {
      await saveAccessSettings({ contact });
      setSaved(true);
    });

  const nameOf = (entry: AccessEntry) => [entry.first_name, entry.last_name].filter(Boolean).join(' ') || text.no_name;
  const dateOf = (value: string) => new Date(value).toLocaleDateString(locale === 'ru' ? 'ru-RU' : 'pl-PL');
  const label = (status: AccessStatus) => (status === 'PENDING' ? text.pending : status === 'ACTIVE' ? text.active : text.blocked);

  return (
    <section aria-label="access-screen" className="w-full space-y-4">
      <div>
        <h2 className="break-words text-lg font-bold">{text.title}</h2>
        <p className="break-words text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.intro}</p>
      </div>

      {failed === 'load' && (
        <div role="alert" className="space-y-2 rounded-xl border border-red-300 p-3">
          <p className="break-words text-sm text-red-700">{text.error_load}</p>
          <button type="button" aria-label="access-retry" className={button} onClick={() => void load()}>{text.retry}</button>
        </div>
      )}

      {overview && (
        <>
          <div className="space-y-3 rounded-xl border border-slate-300 p-3">
            <label className="flex min-h-11 items-start gap-3 font-semibold">
              <input
                type="checkbox"
                aria-label="access-closed"
                checked={overview.settings.closed}
                disabled={busy}
                onChange={(event) => void toggleClosed(event.target.checked)}
                className="mt-0.5 h-6 w-6 shrink-0"
              />
              <span className="break-words text-sm">{text.registration_closed}</span>
            </label>
            <p className="break-words text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {overview.settings.closed ? text.hint_closed : text.hint_open}
            </p>
            <label className="block space-y-1">
              <span className="break-words text-sm font-semibold">{text.contact_label}</span>
              <input
                type="text"
                aria-label="access-contact"
                value={contact}
                maxLength={300}
                placeholder={text.contact_hint}
                onChange={(event) => {
                  setContact(event.target.value);
                  setSaved(false);
                }}
                className="w-full min-h-11 rounded-xl border border-slate-300 bg-white px-3 text-base text-slate-900"
              />
            </label>
            <button type="button" aria-label="access-save-contact" className={primary} disabled={busy || contact.trim() === overview.settings.contact} onClick={() => void saveContact()}>
              {text.save}
            </button>
            {saved && <p role="status" className="break-words text-sm text-emerald-700">{text.saved}</p>}
          </div>

          {failed === 'save' && <p role="alert" className="break-words text-sm text-red-700">{text.error_save}</p>}

          {GROUPS.map((status) => {
            const rows = overview.entries.filter((entry) => entry.status === status);
            return (
              <div key={status} aria-label={`access-group-${status.toLowerCase()}`} className="space-y-2">
                <h3 className="text-sm font-bold uppercase tracking-wide">{label(status)} ({rows.length})</h3>
                {rows.length === 0 && <p className="break-words text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.empty}</p>}
                {rows.map((entry) => (
                  <div key={entry.id} aria-label={`access-row-${entry.telegram_user_id}`} className="space-y-2 rounded-xl border border-slate-300 p-3">
                    <p className="break-words text-sm font-semibold">{nameOf(entry)}</p>
                    <p className="break-all text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
                      {entry.username ? `@${entry.username} · ` : ''}ID {entry.telegram_user_id}
                    </p>
                    {entry.status === 'PENDING' && (
                      <p className="break-words text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.requested.replace('{date}', dateOf(entry.created_at))}</p>
                    )}
                    {entry.is_admin ? (
                      <p className="inline-block rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-800">{text.admin_badge}</p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        {entry.status !== 'ACTIVE' && (
                          <button type="button" aria-label={`access-admit-${entry.telegram_user_id}`} className={primary} disabled={busy} onClick={() => void act(() => decideAccess(entry.id, 'ACTIVE'))}>
                            {entry.status === 'BLOCKED' ? text.unblock : text.admit}
                          </button>
                        )}
                        {entry.status !== 'BLOCKED' && (
                          <button type="button" aria-label={`access-block-${entry.telegram_user_id}`} className={button} disabled={busy} onClick={() => void act(() => decideAccess(entry.id, 'BLOCKED'))}>
                            {text.block}
                          </button>
                        )}
                        {entry.status !== 'ACTIVE' && (
                          <button type="button" aria-label={`access-remove-${entry.telegram_user_id}`} className={button} disabled={busy} onClick={() => void act(() => removeAccess(entry.id))}>
                            {text.remove}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            );
          })}
        </>
      )}
    </section>
  );
}
