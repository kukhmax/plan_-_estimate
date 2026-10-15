import { useEffect, useRef, useState } from 'react';
import { fetchCalendarSettings, saveCalendarSettings } from '../api/calendar';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import type { CalendarSettings } from '../types/calendar';
import { Ico } from './Ico';

const input = 'w-full min-h-11 px-3 text-sm rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-control-bg-color)] text-[var(--tg-control-text-color)]';
const hhmm = (value: string) => value.slice(0, 5);

/**
 * The settings of the calendar (Stage 18E): whether Telegram messages are sent, the zone, the quiet hours, the time of the morning
 * digest, the language and which kinds of events send a message. The defaults are the server's; only a choice is stored.
 */
export function CalendarSettingsForm({ onSaved }: { onSaved?: (settings: CalendarSettings) => void }) {
  const { t } = useI18n();
  const s = t.calendar.settings_page;
  const [loaded, setLoaded] = useState<CalendarSettings | null>(null);
  const [failed, setFailed] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [timezone, setTimezone] = useState('Europe/Warsaw');
  const [quietFrom, setQuietFrom] = useState('21:00');
  const [quietTo, setQuietTo] = useState('07:00');
  const [digestAt, setDigestAt] = useState('08:00');
  const [language, setLanguage] = useState<'' | 'pl' | 'ru'>('');
  const [sends, setSends] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const alive = useRef(true);

  const adopt = (settings: CalendarSettings) => {
    setLoaded(settings);
    setEnabled(settings.enabled);
    setTimezone(settings.timezone);
    setQuietFrom(hhmm(settings.quiet_from));
    setQuietTo(hhmm(settings.quiet_to));
    setDigestAt(hhmm(settings.digest_at));
    setLanguage(settings.language ?? '');
    setSends(Object.fromEntries(settings.kinds.map((kind) => [kind.kind, kind.sends])));
  };

  useEffect(() => {
    alive.current = true;
    fetchCalendarSettings()
      .then((settings) => alive.current && adopt(settings))
      .catch(() => alive.current && setFailed(true));
    return () => {
      alive.current = false;
    };
  }, []);

  if (failed) return <p role="alert" className="text-sm text-[var(--tg-theme-destructive-text-color)] break-words">{t.calendar.load_error}</p>;
  if (!loaded) return <p className="text-sm text-[var(--tg-theme-hint-color)]">{t.calendar.loading}</p>;

  const save = async () => {
    setBusy(true);
    setMessage(null);
    // Only a choice that differs from the default of the kind is stored.
    const overrides: Record<string, boolean> = {};
    for (const kind of loaded.kinds) if (sends[kind.kind] !== kind.default_push) overrides[kind.kind] = sends[kind.kind];
    try {
      const saved = await saveCalendarSettings({
        timezone, enabled, kind_overrides: overrides, quiet_from: quietFrom, quiet_to: quietTo, digest_at: digestAt, language: language || null,
      });
      if (!alive.current) return;
      adopt(saved);
      setMessage({ kind: 'ok', text: s.saved });
      onSaved?.(saved);
    } catch (cause) {
      const code = cause instanceof ApiError ? cause.code : undefined;
      const known = s.errors as Record<string, string>;
      if (alive.current) setMessage({ kind: 'error', text: (code && known[code]) || s.errors.generic });
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  return (
    <div aria-label="calendar-settings-form" className="space-y-4">
      <label className="flex items-center gap-3 min-h-11">
        <input type="checkbox" aria-label="settings-enabled" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="h-6 w-6 shrink-0" />
        <span className="min-w-0 text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">{s.enabled}</span>
      </label>

      <label className="block space-y-1">
        <span className="text-xs text-[var(--tg-theme-hint-color)]">{s.timezone}</span>
        <select aria-label="settings-timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)} className={input}>
          {loaded.timezones.map((zone) => <option key={zone} value={zone}>{zone}</option>)}
        </select>
      </label>

      <fieldset className="space-y-1">
        <legend className="text-xs text-[var(--tg-theme-hint-color)]">{s.quiet}</legend>
        <div className="grid grid-cols-2 gap-2">
          <label className="min-w-0 space-y-1">
            <span className="text-xs text-[var(--tg-theme-hint-color)]">{s.quiet_from}</span>
            <input type="time" aria-label="settings-quiet-from" value={quietFrom} onChange={(event) => setQuietFrom(event.target.value)} className={input} />
          </label>
          <label className="min-w-0 space-y-1">
            <span className="text-xs text-[var(--tg-theme-hint-color)]">{s.quiet_to}</span>
            <input type="time" aria-label="settings-quiet-to" value={quietTo} onChange={(event) => setQuietTo(event.target.value)} className={input} />
          </label>
        </div>
      </fieldset>

      <label className="block space-y-1">
        <span className="text-xs text-[var(--tg-theme-hint-color)]">{s.digest}</span>
        <input type="time" aria-label="settings-digest" value={digestAt} onChange={(event) => setDigestAt(event.target.value)} className={input} />
      </label>

      <label className="block space-y-1">
        <span className="text-xs text-[var(--tg-theme-hint-color)]">{s.language}</span>
        <select aria-label="settings-language" value={language} onChange={(event) => setLanguage(event.target.value as '' | 'pl' | 'ru')} className={input}>
          <option value="">{s.language_auto}</option>
          <option value="pl">Polski</option>
          <option value="ru">Русский</option>
        </select>
      </label>

      <fieldset className="space-y-1">
        <legend className="text-xs text-[var(--tg-theme-hint-color)]">{s.kinds}</legend>
        {loaded.kinds.map((kind) => (
          <label key={kind.kind} className="flex items-center gap-3 min-h-11">
            <input
              type="checkbox"
              aria-label={`settings-kind-${kind.kind}`}
              checked={Boolean(sends[kind.kind])}
              onChange={(event) => setSends((current) => ({ ...current, [kind.kind]: event.target.checked }))}
              className="h-6 w-6 shrink-0"
            />
            <span className="min-w-0 text-sm text-[var(--tg-theme-text-color)] break-words">
              {(t.calendar.kind as Record<string, string>)[kind.kind] ?? kind.kind}
            </span>
          </label>
        ))}
      </fieldset>

      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm font-semibold break-words ${message.kind === 'error' ? 'text-[var(--tg-theme-destructive-text-color)]' : 'text-[var(--tg-theme-text-color)]'}`}>
          {message.text}
        </p>
      )}
      <button type="button" aria-label="settings-save" disabled={busy} onClick={() => void save()} className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] disabled:opacity-60">
        <Ico>💾</Ico>{s.save}
      </button>
    </div>
  );
}
