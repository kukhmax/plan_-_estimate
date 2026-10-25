import { FormEvent, useCallback, useEffect, useState } from 'react';
import { createHours, deleteHours, fetchHours, updateHours } from '../api/paymentSchedule';
import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';
import type { WorkHour, WorkHours } from '../types/paymentSchedule';
import { MAX_HOUR_NOTE_LENGTH } from '../types/paymentSchedule';
import { localizeApiError } from '../utils/apiErrors';
import { formatDay, formatMoney, formatPlain, hoursAmount, todayInPoland, toInput } from '../utils/paymentFormat';
import { Ico } from './Ico';
import { dangerButton, fieldClass, labelClass, primaryButton, secondaryButton } from './paymentUi';
import { VoiceInput } from './VoiceInput';

interface WorkHoursTabProps {
  projectId: string;
  /** The log changed: the margin of the screen is read again. */
  onChanged: () => void;
}

/** V2-9 — the owner's own work log of an object: a day, the hours, a note. The sum is the server's; it feeds the margin. Needs the connection. */
export function WorkHoursTab({ projectId, onChanged }: WorkHoursTabProps) {
  const { t } = useI18n();
  const text = t.payments.hours;
  const { offline } = useConnection();
  const [log, setLog] = useState<WorkHours | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [form, setForm] = useState<{ entry?: WorkHour } | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    try {
      setLog(await fetchHours(projectId));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const saved = async () => {
    setForm(null);
    setMessage({ kind: 'ok', text: text.saved });
    await load();
    onChanged();
  };

  const remove = async (entry: WorkHour) => {
    if (busyId) return;
    setBusyId(entry.id);
    setMessage(null);
    try {
      await deleteHours(projectId, entry.id);
      setConfirmId(null);
      setMessage({ kind: 'ok', text: text.deleted });
      await load();
      onChanged();
    } catch (err) {
      const localized = localizeApiError(err, t);
      setMessage({ kind: 'error', text: localized && !localized.startsWith('Request failed') ? localized : text.save_error });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div aria-label="hours-tab" className="space-y-3">
      <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>
      {loading && <p className="text-sm text-slate-500 text-center py-3">{t.payments.loading}</p>}
      {!loading && loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
          <button type="button" aria-label="hours-retry" onClick={() => void load()} className={primaryButton}><Ico>🔄</Ico>{t.payments.retry}</button>
        </div>
      )}
      {log && (
        <>
          <article aria-label="hours-summary" className="pe-card rounded-2xl p-4 shadow-sm space-y-1.5 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="text-slate-500">{text.total}</span>
              <span aria-label="hours-total" className="font-semibold text-slate-900">{formatPlain(log.total_hours)} h</span>
            </div>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="text-slate-500">{text.rate}</span>
              <span aria-label="hours-rate" className="font-semibold text-slate-900 break-words">{log.hourly_rate === null ? text.rate_not_set : `${formatMoney(log.hourly_rate)} / h`}</span>
            </div>
          </article>
          {form === null ? (
            <>
              <button type="button" aria-label="hours-add" disabled={offline} onClick={() => setForm({})} className={primaryButton}>
                <Ico>➕</Ico>{text.add}
              </button>
              {offline && <p aria-label="hours-offline" className="text-xs text-slate-500 break-words">{text.needs_connection}</p>}
            </>
          ) : (
            <HoursForm key={form.entry?.id ?? 'new'} projectId={projectId} entry={form.entry} onSaved={() => void saved()} onCancel={() => setForm(null)} />
          )}
          {message && (
            <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>
              {message.text}
            </p>
          )}
          {log.items.length === 0 ? (
            <p aria-label="hours-empty" className="text-sm text-slate-500 text-center py-4">{text.empty}</p>
          ) : (
            <ul aria-label="hours-list" className="space-y-2">
              {log.items.map((entry) => (
                <li key={entry.id} aria-label={`hour-${entry.id}`} className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
                  <p className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <span className="text-sm text-slate-700">{formatDay(entry.worked_on)}</span>
                    <span aria-label={`hour-value-${entry.id}`} className="text-lg font-bold text-slate-900">{formatPlain(entry.hours)} h</span>
                  </p>
                  {entry.note && <p className="text-xs text-slate-600 whitespace-pre-wrap break-words">{entry.note}</p>}
                  {confirmId !== entry.id ? (
                    <div className="flex flex-col gap-2">
                      <button type="button" aria-label={`hour-edit-${entry.id}`} disabled={offline} onClick={() => { setMessage(null); setForm({ entry }); }} className={secondaryButton}>
                        <Ico>✏️</Ico>{t.common.edit}
                      </button>
                      <button type="button" aria-label={`hour-delete-${entry.id}`} disabled={busyId === entry.id || offline} onClick={() => setConfirmId(entry.id)} className={secondaryButton}>
                        <Ico>🗑️</Ico>{text.delete}
                      </button>
                    </div>
                  ) : (
                    <div aria-label={`hour-confirm-${entry.id}`} className="space-y-2">
                      <p className="text-sm text-slate-800 break-words">{text.delete_confirm}</p>
                      <button type="button" aria-label={`hour-delete-yes-${entry.id}`} disabled={busyId === entry.id} onClick={() => void remove(entry)} className={dangerButton}>
                        <Ico>🗑️</Ico>{text.delete_yes}
                      </button>
                      <button type="button" aria-label={`hour-delete-no-${entry.id}`} onClick={() => setConfirmId(null)} className={secondaryButton}>
                        <Ico>✖️</Ico>{t.common.cancel}
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function HoursForm({ projectId, entry, onSaved, onCancel }: { projectId: string; entry?: WorkHour; onSaved: () => void; onCancel: () => void }) {
  const { t } = useI18n();
  const text = t.payments.hours;
  const [day, setDay] = useState(entry?.worked_on ?? todayInPoland());
  const [hours, setHours] = useState(toInput(entry?.hours));
  const [note, setNote] = useState(entry?.note ?? '');
  const [bad, setBad] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const value = hoursAmount(hours);
    setBad(value === null);
    if (value === null || day === '') return;
    const fields = { worked_on: day, hours: value, note: note.trim() !== '' ? note.trim() : null };
    setBusy(true);
    setFailure(null);
    try {
      if (entry) await updateHours(projectId, entry.id, fields);
      else await createHours(projectId, fields);
      onSaved();
    } catch (err) {
      const localized = localizeApiError(err, t);
      setFailure(localized && !localized.startsWith('Request failed') ? localized : text.save_error);
      setBusy(false);
    }
  };

  return (
    <form aria-label="hours-form" onSubmit={submit} noValidate className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="text-sm font-semibold text-slate-900 break-words">{entry ? text.edit_title : text.add_title}</h3>
      <div>
        <label htmlFor="hours-day" className={labelClass}>{text.date_label}</label>
        <input id="hours-day" aria-label="hours-day" type="date" value={day} onChange={(event) => setDay(event.target.value)} className={fieldClass} />
      </div>
      <div>
        <label htmlFor="hours-value" className={labelClass}>{text.hours_label}</label>
        <VoiceInput name="hours-value" mode="plain" onValue={(value) => setHours(value.replace('.', ','))}>
          <input id="hours-value" aria-label="hours-value" inputMode="decimal" autoComplete="off" value={hours} placeholder="8" onChange={(event) => setHours(event.target.value)} className={`${fieldClass} min-w-0 flex-1`} />
        </VoiceInput>
        {bad && <p role="alert" className="text-xs text-red-600 mt-1">{text.errors.hours}</p>}
      </div>
      <div>
        <label htmlFor="hours-note" className={labelClass}>{text.note_label}</label>
        <textarea id="hours-note" aria-label="hours-note" value={note} maxLength={MAX_HOUR_NOTE_LENGTH} onChange={(event) => setNote(event.target.value)} className={`${fieldClass} min-h-24`} />
      </div>
      {failure && <p role="alert" className="text-sm text-red-600 break-words">{failure}</p>}
      <div className="flex flex-col gap-2">
        <button type="submit" aria-label="hours-save" disabled={busy} className={primaryButton}>
          <Ico>{busy ? '⏳' : '💾'}</Ico>{busy ? t.common.saving : t.common.save}
        </button>
        <button type="button" aria-label="hours-cancel" onClick={onCancel} className={secondaryButton}>
          <Ico>✖️</Ico>{t.common.cancel}
        </button>
      </div>
    </form>
  );
}
