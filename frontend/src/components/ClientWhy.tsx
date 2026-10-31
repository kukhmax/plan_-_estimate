import { useState } from 'react';
import { fetchPortalWhy } from '../api/clientPortal';
import { useI18n } from '../hooks/useI18n';
import type { PortalWhy } from '../types/clientLink';
import { resolveKey } from '../utils/i18nKeys';
import { formatDay } from '../utils/paymentFormat';
import { Ico } from './Ico';

const BUTTON = 'w-full min-h-12 px-4 py-2 text-base rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium hover:bg-slate-50';

/**
 * Owner 2026-10-31: "Dlaczego te prace?" on the client's page -- read only on a tap: the agreed standard of each room (S1-S4 / Q1-Q4 with
 * its words) and, for each work taken from an inspection, what was found, on which day, with up to four photos (links signed for half an hour).
 */
export function ClientWhy({ token }: { token: string }) {
  const { t } = useI18n();
  const text = t.client_page;
  const [open, setOpen] = useState(false);
  const [why, setWhy] = useState<PortalWhy | null>(null);
  const [failed, setFailed] = useState(false);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (!next || why !== null) return;
    setFailed(false);
    try {
      setWhy(await fetchPortalWhy(token));
    } catch {
      setFailed(true);
    }
  };

  const words = (key: string | null | undefined) => (key ? resolveKey(t, key) : '');
  const standard = (level: string) => {
    const name = (t.contractCatalog.evaluation as Record<string, string>)[level] ?? level;
    const about = (t.workflow_templates.description as Record<string, string>)[level.toLowerCase()] ?? '';
    return { name, about };
  };

  return (
    <div className="space-y-3">
      <button type="button" aria-label="client-why" aria-expanded={open} onClick={() => void toggle()} className={BUTTON}>
        <Ico>{open ? '🔼' : '❓'}</Ico>{text.why_button}
      </button>
      {open && failed && <p role="alert" className="text-sm text-red-600 break-words">{text.why_error}</p>}
      {open && !failed && why === null && <p role="status" className="text-sm text-slate-500">{text.loading}</p>}
      {open && why && (
        <div aria-label="client-why-panel" className="space-y-3">
          {why.rooms.length === 0 && <p className="text-sm text-slate-600 break-words">{text.why_empty}</p>}
          {why.rooms.map((room, index) => (
            <section key={`${room.room_name}-${index}`} aria-label={`client-why-room-${index}`} className="rounded-xl border border-slate-200 p-3 space-y-2">
              <h3 className="text-sm font-semibold text-slate-900 break-words">{room.room_name}</h3>
              {room.quality_target && (
                <div className="rounded-lg border border-slate-200 p-2 space-y-0.5">
                  <p className="text-xs font-semibold text-slate-800 break-words">
                    {text.why_standard}: {standard(room.quality_target).name}
                  </p>
                  {standard(room.quality_target).about && <p className="text-xs text-slate-600 break-words">{standard(room.quality_target).about}</p>}
                </div>
              )}
              {room.reasons.map((reason, r) => (
                <div key={r} aria-label={`client-why-reason-${index}-${r}`} className="space-y-1.5 border-t border-slate-100 pt-2">
                  <p className="text-sm text-slate-900 break-words">
                    {reason.surface_name ? `${reason.surface_name}: ` : ''}
                    <strong>{reason.work_name ?? words(reason.work_name_key)}</strong>
                  </p>
                  <p className="text-xs text-slate-700 break-words">
                    {text.why_reason}: {words(reason.reason_key)}
                    {reason.inspected_on ? ` · ${text.why_inspected.replace('{date}', formatDay(reason.inspected_on))}` : ''}
                  </p>
                  {reason.photos.length > 0 && (
                    <div className="grid grid-cols-4 gap-1.5">
                      {reason.photos.map((photo, p) => (
                        <a key={p} href={photo.url} target="_blank" rel="noopener noreferrer" aria-label={`client-why-photo-${index}-${r}-${p}`} className="block">
                          <img src={photo.thumb_url} alt={text.why_photo} loading="lazy" className="aspect-square w-full rounded-lg object-cover" />
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
