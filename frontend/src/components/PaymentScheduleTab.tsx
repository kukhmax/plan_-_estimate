import { FormEvent, useCallback, useEffect, useState } from 'react';
import { createStage, deleteStage, fetchSchedule, receiveStage, updateStage } from '../api/paymentSchedule';
import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';
import type { PaymentStage, Schedule, StageState } from '../types/paymentSchedule';
import { MAX_STAGE_TITLE_LENGTH } from '../types/paymentSchedule';
import { localizeApiError } from '../utils/apiErrors';
import { formatDay, formatMoney, formatPlain, percentAmount, positiveAmount, toInput } from '../utils/paymentFormat';
import { Ico } from './Ico';
import { dangerButton, fieldClass, labelClass, primaryButton, secondaryButton, segmentClass } from './paymentUi';
import { VoiceInput } from './VoiceInput';

interface PaymentScheduleTabProps {
  projectId: string;
  /** Money was booked (the one-tap "received") or the schedule changed: the totals and the margin of the screen are read again. */
  onMoneyChanged: () => void;
  /** Opens the document "Harmonogram płatności" (the documents of the object); without it the button is not shown. */
  onOpenPdf?: () => void;
}

const STATE_STYLE: Record<StageState, string> = {
  PAID: 'bg-emerald-100 text-emerald-800',
  PARTIAL: 'bg-amber-100 text-amber-900',
  OVERDUE: 'bg-red-100 text-red-800',
  OPEN: 'bg-slate-100 text-slate-700',
};

/**
 * V2-9 — the payment schedule of an object: the owner's own stages (a share of the agreed amount or a fixed amount, an optional day), what each is worth,
 * what was received for it and where it stands — all the server's. "Otrzymano" books the rest of a stage in one tap. Needs the connection (like the agreed amount).
 */
export function PaymentScheduleTab({ projectId, onMoneyChanged, onOpenPdf }: PaymentScheduleTabProps) {
  const { t } = useI18n();
  const text = t.payments.schedule;
  const { offline } = useConnection();
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [form, setForm] = useState<{ stage?: PaymentStage } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    try {
      setSchedule(await fetchSchedule(projectId));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const failure = (err: unknown, fallback: string) => {
    const localized = localizeApiError(err, t);
    setMessage({ kind: 'error', text: localized && !localized.startsWith('Request failed') ? localized : fallback });
  };

  const receive = async (stage: PaymentStage) => {
    if (busyId) return;
    setBusyId(stage.id);
    setMessage(null);
    try {
      await receiveStage(projectId, stage.id);
      setMessage({ kind: 'ok', text: text.received_ok });
      await load();
      onMoneyChanged();
    } catch (err) {
      failure(err, text.save_error);
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (stage: PaymentStage) => {
    if (busyId) return;
    setBusyId(stage.id);
    setMessage(null);
    try {
      await deleteStage(projectId, stage.id);
      setConfirmId(null);
      setMessage({ kind: 'ok', text: text.deleted });
      await load();
      onMoneyChanged();
    } catch (err) {
      failure(err, text.save_error);
    } finally {
      setBusyId(null);
    }
  };

  const saved = async () => {
    setForm(null);
    setMessage({ kind: 'ok', text: text.saved });
    await load();
    onMoneyChanged();
  };

  return (
    <div aria-label="schedule-tab" className="space-y-3">
      <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>
      {loading && <p className="text-sm text-slate-500 text-center py-3">{t.payments.loading}</p>}
      {!loading && loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
          <button type="button" aria-label="schedule-retry" onClick={() => void load()} className={primaryButton}><Ico>🔄</Ico>{t.payments.retry}</button>
        </div>
      )}
      {schedule && (
        <>
          <ScheduleSummaryCard summary={schedule.summary} />
          {onOpenPdf && schedule.items.length > 0 && (
            <button type="button" aria-label="schedule-pdf" onClick={onOpenPdf} className={secondaryButton}>
              <Ico>📆</Ico>{text.pdf_button}
            </button>
          )}
          {form === null ? (
            <>
              <button type="button" aria-label="stage-add" disabled={offline} onClick={() => setForm({})} className={primaryButton}>
                <Ico>➕</Ico>{text.add}
              </button>
              {offline && <p aria-label="schedule-offline" className="text-xs text-slate-500 break-words">{text.needs_connection}</p>}
            </>
          ) : (
            <StageForm key={form.stage?.id ?? 'new'} projectId={projectId} stage={form.stage} onSaved={() => void saved()} onCancel={() => setForm(null)} />
          )}
          {message && (
            <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>
              {message.text}
            </p>
          )}
          {schedule.items.length === 0 ? (
            <p aria-label="schedule-empty" className="text-sm text-slate-500 text-center py-4">{text.empty}</p>
          ) : (
            <ul aria-label="schedule-list" className="space-y-2">
              {schedule.items.map((stage) => (
                <StageCard
                  key={stage.id}
                  stage={stage}
                  busy={busyId === stage.id}
                  offline={offline}
                  confirming={confirmId === stage.id}
                  onReceive={() => void receive(stage)}
                  onEdit={() => {
                    setMessage(null);
                    setForm({ stage });
                  }}
                  onAskDelete={() => setConfirmId(stage.id)}
                  onCancelDelete={() => setConfirmId(null)}
                  onDelete={() => void remove(stage)}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function ScheduleSummaryCard({ summary }: { summary: Schedule['summary'] }) {
  const { t } = useI18n();
  const text = t.payments.schedule.summary;
  const difference = summary.difference;
  // the sign of what the server sent decides the sentence; the amount shown is the server's (without the sign)
  const note =
    difference === null
      ? null
      : difference.startsWith('-')
        ? text.difference_less.replace('{amount}', formatMoney(difference.slice(1)))
        : Number(difference) === 0
          ? text.difference_ok
          : text.difference_more.replace('{amount}', formatMoney(difference));
  const rows: { key: string; label: string; value: string | null }[] = [
    { key: 'agreed', label: text.agreed, value: summary.agreed },
    { key: 'total', label: text.total, value: summary.stages_total },
    { key: 'received', label: text.received, value: summary.received },
    { key: 'to_receive', label: text.to_receive, value: summary.to_receive },
  ];
  return (
    <article aria-label="schedule-summary" className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
      <dl className="space-y-1.5 text-sm">
        {rows.map((row) => (
          <div key={row.key} aria-label={`schedule-summary-${row.key}`} className="flex flex-wrap items-baseline justify-between gap-x-3">
            <dt className="text-slate-500 min-w-0 break-words">{row.label}</dt>
            <dd className="font-semibold text-slate-900 break-words">{row.value === null ? text.not_set : formatMoney(row.value)}</dd>
          </div>
        ))}
      </dl>
      {note && <p aria-label="schedule-difference" className="text-xs text-slate-700 break-words">{note}</p>}
      {summary.unpriced > 0 && <p aria-label="schedule-unpriced" className="text-xs text-amber-900 break-words">{text.unpriced.replace('{n}', String(summary.unpriced))}</p>}
    </article>
  );
}

interface StageCardProps {
  stage: PaymentStage;
  busy: boolean;
  offline: boolean;
  confirming: boolean;
  onReceive: () => void;
  onEdit: () => void;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
}

function StageCard({ stage, busy, offline, confirming, onReceive, onEdit, onAskDelete, onCancelDelete, onDelete }: StageCardProps) {
  const { t } = useI18n();
  const text = t.payments.schedule;
  const canReceive = stage.state !== 'PAID' && stage.remaining !== null && Number(stage.remaining) > 0;
  return (
    <li aria-label={`stage-${stage.id}`} className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-slate-900 break-words min-w-0">{stage.title}</p>
        <span aria-label={`stage-state-${stage.id}`} className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATE_STYLE[stage.state]}`}>{text.state[stage.state]}</span>
      </div>
      {stage.amount !== null ? (
        <p aria-label={`stage-amount-${stage.id}`} className="text-lg font-bold text-slate-900 break-words">{formatMoney(stage.amount)}</p>
      ) : (
        <p aria-label={`stage-waits-${stage.id}`} className="text-sm text-amber-900 break-words">{text.share_waits}</p>
      )}
      <div className="text-xs text-slate-600 space-y-0.5">
        {stage.percent !== null && <p>{text.share_of.replace('{percent}', formatPlain(stage.percent))}</p>}
        {stage.due_on && <p>{text.due}: {formatDay(stage.due_on)}</p>}
        <p aria-label={`stage-received-${stage.id}`}>
          {text.received}: {formatMoney(stage.received)}
          {stage.remaining !== null && <> · {text.remaining}: {formatMoney(stage.remaining)}</>}
        </p>
      </div>
      {canReceive && (
        <button type="button" aria-label={`stage-receive-${stage.id}`} disabled={busy || offline} onClick={onReceive} className={primaryButton}>
          <Ico>✅</Ico>{text.received_btn}
        </button>
      )}
      {!confirming ? (
        <div className="flex flex-col gap-2">
          <button type="button" aria-label={`stage-edit-${stage.id}`} disabled={offline} onClick={onEdit} className={secondaryButton}>
            <Ico>✏️</Ico>{t.common.edit}
          </button>
          <button type="button" aria-label={`stage-delete-${stage.id}`} disabled={busy || offline} onClick={onAskDelete} className={secondaryButton}>
            <Ico>🗑️</Ico>{text.delete}
          </button>
        </div>
      ) : (
        <div aria-label={`stage-confirm-${stage.id}`} className="space-y-2">
          <p className="text-sm text-slate-800 break-words">{text.delete_confirm}</p>
          <button type="button" aria-label={`stage-delete-yes-${stage.id}`} disabled={busy} onClick={onDelete} className={dangerButton}>
            <Ico>🗑️</Ico>{text.delete_yes}
          </button>
          <button type="button" aria-label={`stage-delete-no-${stage.id}`} onClick={onCancelDelete} className={secondaryButton}>
            <Ico>✖️</Ico>{t.common.cancel}
          </button>
        </div>
      )}
    </li>
  );
}

type Mode = 'percent' | 'amount';

function StageForm({ projectId, stage, onSaved, onCancel }: { projectId: string; stage?: PaymentStage; onSaved: () => void; onCancel: () => void }) {
  const { t } = useI18n();
  const text = t.payments.schedule;
  const [title, setTitle] = useState(stage?.title ?? '');
  const [mode, setMode] = useState<Mode>(stage && stage.percent === null ? 'amount' : 'percent');
  const [value, setValue] = useState(stage ? toInput(stage.percent ?? stage.amount_fixed) : '');
  const [due, setDue] = useState(stage?.due_on ?? '');
  const [errors, setErrors] = useState<('title' | 'value')[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const bad: ('title' | 'value')[] = [];
    const number = mode === 'percent' ? percentAmount(value) : positiveAmount(value);
    if (title.trim() === '') bad.push('title');
    if (number === null) bad.push('value');
    setErrors(bad);
    if (bad.length > 0 || number === null) return;
    const fields = { title: title.trim(), due_on: due !== '' ? due : null, ...(mode === 'percent' ? { percent: number } : { amount: number }) };
    setBusy(true);
    setFailure(null);
    try {
      if (stage) await updateStage(projectId, stage.id, fields);
      else await createStage(projectId, fields);
      onSaved();
    } catch (err) {
      const localized = localizeApiError(err, t);
      setFailure(localized && !localized.startsWith('Request failed') ? localized : text.save_error);
      setBusy(false);
    }
  };

  return (
    <form aria-label="stage-form" onSubmit={submit} noValidate className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="text-sm font-semibold text-slate-900 break-words">{stage ? text.edit_title : text.add_title}</h3>
      <div>
        <label htmlFor="stage-title" className={labelClass}>{text.title_label}</label>
        <input id="stage-title" aria-label="stage-title" value={title} maxLength={MAX_STAGE_TITLE_LENGTH} onChange={(event) => setTitle(event.target.value)} className={fieldClass} />
        {!stage && (
          <div className="flex flex-wrap gap-2 mt-2">
            {(['hint_1', 'hint_2', 'hint_3'] as const).map((key) => (
              <button key={key} type="button" aria-label={`stage-${key}`} onClick={() => setTitle(text[key])} className="min-h-11 px-3 py-1 text-xs rounded-full border border-slate-200 bg-slate-50 text-slate-700 break-words">
                {text[key]}
              </button>
            ))}
          </div>
        )}
        {errors.includes('title') && <p role="alert" className="text-xs text-red-600 mt-1">{text.errors.title}</p>}
      </div>
      <div role="group" aria-label="stage-mode" className="flex gap-2">
        {(['percent', 'amount'] as const).map((id) => (
          <button key={id} type="button" aria-pressed={mode === id} aria-label={`stage-mode-${id}`} onClick={() => setMode(id)} className={segmentClass(mode === id)}>
            {id === 'percent' ? text.mode_percent : text.mode_amount}
          </button>
        ))}
      </div>
      <div>
        <label htmlFor="stage-value" className={labelClass}>{mode === 'percent' ? text.percent_label : text.amount_label}</label>
        <VoiceInput name="stage-value" mode="plain" onValue={(value) => setValue(value.replace('.', ','))}>
          <input id="stage-value" aria-label="stage-value" inputMode="decimal" autoComplete="off" value={value} placeholder={mode === 'percent' ? '30' : '0,00'} onChange={(event) => setValue(event.target.value)} className={`${fieldClass} min-w-0 flex-1`} />
        </VoiceInput>
        {errors.includes('value') && <p role="alert" className="text-xs text-red-600 mt-1">{text.errors.value}</p>}
      </div>
      <div>
        <label htmlFor="stage-due" className={labelClass}>{text.due_label}</label>
        <input id="stage-due" aria-label="stage-due" type="date" value={due} onChange={(event) => setDue(event.target.value)} className={fieldClass} />
      </div>
      {failure && <p role="alert" className="text-sm text-red-600 break-words">{failure}</p>}
      <div className="flex flex-col gap-2">
        <button type="submit" aria-label="stage-save" disabled={busy} className={primaryButton}>
          <Ico>{busy ? '⏳' : '💾'}</Ico>{busy ? t.common.saving : t.common.save}
        </button>
        <button type="button" aria-label="stage-cancel" onClick={onCancel} className={secondaryButton}>
          <Ico>✖️</Ico>{t.common.cancel}
        </button>
      </div>
    </form>
  );
}
