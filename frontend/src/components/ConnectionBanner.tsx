import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';

const TAGS: Record<string, string> = { pl: 'pl-PL', ru: 'ru-RU' };

/**
 * A strip under the header, only while the server cannot be reached or the screen shows a copy kept on the phone (Stage 19B).
 * It is a status, not an alert: the work goes on.
 */
export function ConnectionBanner() {
  const { t, locale } = useI18n();
  const { offline, servedFrom } = useConnection();
  if (!offline && servedFrom === null) return null;
  const time = servedFrom === null ? '' : new Date(servedFrom).toLocaleString(TAGS[locale] ?? locale, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  const text = offline
    ? servedFrom === null
      ? t.offline.banner_offline
      : t.offline.banner_offline_copy.replace('{time}', time)
    : t.offline.banner_copy.replace('{time}', time);
  return (
    <p
      role="status"
      aria-label="connection-banner"
      className="w-full mb-3 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-900 break-words"
    >
      <span aria-hidden="true" className="mr-1.5">{offline ? '📴' : '🕘'}</span>
      {text}
    </p>
  );
}
