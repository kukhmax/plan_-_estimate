import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  createClientLink,
  createClientProposal,
  extendClientLink,
  fetchClientJournal,
  fetchClientLink,
  listClientProposals,
  revokeClientLink,
  withdrawClientProposal,
} from '../api/clientLink';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import { clientLinkUrl, type ClientConsent, type ClientLinkInfo, type ClientProposal } from '../types/clientLink';
import { copyTextToClipboard } from '../utils/clipboard';
import { formatDecimalMoney } from '../utils/format';
import { LOCALES, LOCALE_NAMES, type Locale } from '../utils/locale';
import { formatNoteTime } from '../utils/noteFormat';
import { Ico } from './Ico';

interface ProjectClientLinkProps {
  projectId: string;
}

type Confirm = { kind: 'new' } | { kind: 'revoke' } | { kind: 'withdraw'; id: string } | null;

const PRIMARY = 'w-full min-h-11 px-4 py-1 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50';
const SECONDARY = 'w-full min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium hover:bg-slate-50 disabled:opacity-50';
const DANGER = 'w-full min-h-11 px-3 py-1 text-sm bg-red-600 text-white font-semibold rounded-xl hover:bg-red-700 disabled:opacity-50';
const FIELD = 'w-full border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 pe-surface min-h-11';

/**
 * The link for the client (V2-8), the owner's screen of an object: make, copy, send, extend and revoke the link; write the proposals of extra
 * work; read the journal of what the client agreed to. The secret is shown only in the session that made it (the server keeps its hash only).
 */
export function ProjectClientLink({ projectId }: ProjectClientLinkProps) {
  const { t, locale } = useI18n();
  const text = t.client_link;
  const [link, setLink] = useState<ClientLinkInfo | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [language, setLanguage] = useState<Locale>('pl');
  const [proposals, setProposals] = useState<ClientProposal[]>([]);
  const [journal, setJournal] = useState<ClientConsent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [amount, setAmount] = useState('');
  const [days, setDays] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const [status, list, entries] = await Promise.all([fetchClientLink(projectId), listClientProposals(projectId), fetchClientJournal(projectId)]);
      setLink(status.link);
      if (status.link) setLanguage(status.link.language);
      setProposals(list.items);
      setJournal(entries.items);
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const say = (kind: 'ok' | 'error', value: string) => setMessage({ kind, text: value });
  const fail = (err: unknown) => {
    const code = err instanceof ApiError ? err.code : undefined;
    const known = code ? (text.errors as Record<string, string>)[code] : undefined;
    say('error', known ?? text.save_error);
  };
  const date = (iso: string) => formatNoteTime(iso, locale);

  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const makeLink = () =>
    run(async () => {
      const issued = await createClientLink(projectId, language);
      setLink(issued.link);
      setToken(issued.token);
      say('ok', text.created);
    });
  const extend = () =>
    run(async () => {
      const status = await extendClientLink(projectId);
      setLink(status.link);
      say('ok', text.extended);
    });
  const revoke = () =>
    run(async () => {
      await revokeClientLink(projectId);
      setLink(null);
      setToken(null);
      say('ok', text.revoked);
    });
  const withdraw = (id: string) =>
    run(async () => {
      const changed = await withdrawClientProposal(projectId, id);
      setProposals((current) => current.map((p) => (p.id === changed.id ? changed : p)));
      say('ok', text.withdrawn);
    });

  const addProposal = (event: FormEvent) => {
    event.preventDefault();
    event.stopPropagation();
    return run(async () => {
      const created = await createClientProposal(projectId, {
        title,
        description: description.trim() === '' ? null : description,
        amount: amount.replace(',', '.'),
        extra_days: days.trim() === '' ? null : Number(days),
      });
      setProposals((current) => [created, ...current]);
      setTitle('');
      setDescription('');
      setAmount('');
      setDays('');
      setFormOpen(false);
      say('ok', text.proposal_saved);
    });
  };

  const url = token ? clientLinkUrl(window.location.origin, token) : null;
  const copy = async () => {
    if (!url) return;
    const done = await copyTextToClipboard(url);
    say(done ? 'ok' : 'error', done ? text.copied : text.copy_failed);
  };
  const share = () => {
    if (!url) return;
    const shareText = text.share_text;
    const telegram = window.Telegram?.WebApp;
    if (telegram?.openTelegramLink) {
      telegram.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(shareText)}`);
    } else if (typeof navigator.share === 'function') {
      void navigator.share({ url, text: shareText }).catch(() => undefined);
    } else {
      void copy();
    }
  };

  const statusLabel = (status: ClientProposal['status']) =>
    ({ OPEN: text.status_open, ACCEPTED: text.status_accepted, DECLINED: text.status_declined, WITHDRAWN: text.status_withdrawn })[status];
  const kindLabel = (kind: ClientConsent['kind']) =>
    ({ ESTIMATE_ACCEPTED: text.kind_estimate_accepted, ESTIMATE_DECLINED: text.kind_estimate_declined, PROPOSAL_ACCEPTED: text.kind_proposal_accepted, PROPOSAL_DECLINED: text.kind_proposal_declined })[kind];
  const badge = (status: ClientProposal['status']) =>
    status === 'ACCEPTED' ? 'bg-emerald-100 text-emerald-800' : status === 'DECLINED' ? 'bg-red-100 text-red-800' : status === 'OPEN' ? 'bg-amber-100 text-amber-800' : 'bg-slate-200 text-slate-700';

  if (loading) return <p className="text-sm text-slate-500 text-center py-4">{text.loading}</p>;
  if (loadFailed) {
    return (
      <div className="space-y-2">
        <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
        <button type="button" aria-label="client-link-retry" onClick={() => void load()} className={PRIMARY}><Ico>🔄</Ico>{text.retry}</button>
      </div>
    );
  }

  return (
    <section aria-label="project-client-link" className="space-y-3">
      <div className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
        <p className="text-sm text-slate-700 break-words">{text.intro}</p>
        <p className="text-xs text-slate-500 break-words">{text.no_estimate_hint}</p>

        {link === null ? (
          <>
            <label className="block text-sm font-medium text-slate-700">
              {text.language_label}
              <select aria-label="client-link-language" value={language} onChange={(e) => setLanguage(e.target.value as Locale)} className={`${FIELD} mt-1`}>
                {LOCALES.map((code) => (
                  <option key={code} value={code}>{LOCALE_NAMES[code]}</option>
                ))}
              </select>
            </label>
            <button type="button" aria-label="client-link-create" disabled={busy} onClick={() => void makeLink()} className={PRIMARY}>
              <Ico>🔗</Ico>{text.create}
            </button>
          </>
        ) : (
          <>
            <p aria-label="client-link-term" className={`text-sm font-semibold break-words ${link.expired ? 'text-red-700' : 'text-emerald-700'}`}>
              {(link.expired ? text.expired_on : text.active_until).replace('{date}', date(link.expires_at))}
            </p>
            <p aria-label="client-link-views" className="text-xs text-slate-500 break-words">
              {link.view_count === 0 || !link.last_viewed_at
                ? text.never_opened
                : text.opened_times.replace('{count}', String(link.view_count)).replace('{date}', date(link.last_viewed_at))}
            </p>

            {url ? (
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-700">
                  {text.url_label}
                  <input
                    aria-label="client-link-url"
                    readOnly
                    value={url}
                    onFocus={(e) => e.currentTarget.select()}
                    className={`${FIELD} mt-1 text-sm break-all`}
                  />
                </label>
                <p className="text-xs text-slate-500 break-words">{text.url_once}</p>
                <div className="flex flex-col gap-2">
                  <button type="button" aria-label="client-link-share" onClick={share} className={PRIMARY}><Ico>📤</Ico>{text.share}</button>
                  <button type="button" aria-label="client-link-copy" onClick={() => void copy()} className={SECONDARY}><Ico>📋</Ico>{text.copy}</button>
                </div>
              </div>
            ) : (
              <p aria-label="client-link-hidden" className="text-xs text-slate-500 break-words">{text.url_hidden}</p>
            )}

            {confirm?.kind === 'new' ? (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-slate-800 break-words">{text.new_confirm}</p>
                <button type="button" aria-label="client-link-new-yes" disabled={busy} onClick={() => void makeLink()} className={PRIMARY}>{text.new_yes}</button>
                <button type="button" aria-label="client-link-new-cancel" onClick={() => setConfirm(null)} className={SECONDARY}>{t.common.cancel}</button>
              </div>
            ) : confirm?.kind === 'revoke' ? (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-slate-800 break-words">{text.revoke_confirm}</p>
                <button type="button" aria-label="client-link-revoke-yes" disabled={busy} onClick={() => void revoke()} className={DANGER}>{text.revoke_yes}</button>
                <button type="button" aria-label="client-link-revoke-cancel" onClick={() => setConfirm(null)} className={SECONDARY}>{t.common.cancel}</button>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <button type="button" aria-label="client-link-extend" disabled={busy} onClick={() => void extend()} className={SECONDARY}><Ico>⏳</Ico>{text.extend}</button>
                <button type="button" aria-label="client-link-new" disabled={busy} onClick={() => setConfirm({ kind: 'new' })} className={SECONDARY}><Ico>🔄</Ico>{text.new_link}</button>
                <button type="button" aria-label="client-link-revoke" disabled={busy} onClick={() => setConfirm({ kind: 'revoke' })} className={SECONDARY}><Ico>🚫</Ico>{text.revoke}</button>
              </div>
            )}
          </>
        )}
      </div>

      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>
          {message.text}
        </p>
      )}

      <div className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
        <h3 className="text-base font-semibold text-slate-900 break-words">{text.proposals_title}</h3>
        <p className="text-xs text-slate-500 break-words">{text.proposals_intro}</p>

        {formOpen ? (
          <form aria-label="client-proposal-form" onSubmit={(e) => void addProposal(e)} className="space-y-2">
            <label className="block text-sm font-medium text-slate-700">
              {text.field_title}
              <input aria-label="client-proposal-title" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} className={`${FIELD} mt-1`} />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              {text.field_description}
              <textarea aria-label="client-proposal-description" value={description} maxLength={2000} onChange={(e) => setDescription(e.target.value)} className={`${FIELD} mt-1 min-h-24`} />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              {text.field_amount}
              <input aria-label="client-proposal-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} className={`${FIELD} mt-1`} />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              {text.field_days}
              <input aria-label="client-proposal-days" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ''))} className={`${FIELD} mt-1`} />
            </label>
            <button type="submit" aria-label="client-proposal-save" disabled={busy || title.trim() === '' || amount.trim() === ''} className={PRIMARY}>
              <Ico>💾</Ico>{text.save_proposal}
            </button>
            <button type="button" aria-label="client-proposal-cancel" onClick={() => setFormOpen(false)} className={SECONDARY}>{t.common.cancel}</button>
          </form>
        ) : (
          <button type="button" aria-label="client-proposal-add" onClick={() => { setFormOpen(true); setMessage(null); }} className={PRIMARY}>
            <Ico>➕</Ico>{text.add_proposal}
          </button>
        )}

        {proposals.length === 0 ? (
          <p aria-label="client-proposals-empty" className="text-sm text-slate-500 text-center py-2">{text.proposals_empty}</p>
        ) : (
          <ul aria-label="client-proposals-list" className="space-y-2">
            {proposals.map((p) => (
              <li key={p.id} aria-label={`client-proposal-${p.id}`} className="rounded-xl border border-slate-200 p-3 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-xs font-semibold px-2 py-1 rounded-full ${badge(p.status)}`}>{statusLabel(p.status)}</span>
                  <span className="text-sm font-semibold text-slate-900">{formatDecimalMoney(p.amount)} {p.currency}</span>
                  {p.extra_days ? <span className="text-xs text-slate-500">{text.days_shift.replace('{days}', String(p.extra_days))}</span> : null}
                </div>
                <p className="text-sm font-medium text-slate-900 break-words">{p.title}</p>
                {p.description && <p className="text-sm text-slate-600 whitespace-pre-wrap break-words">{p.description}</p>}
                {p.status === 'OPEN' &&
                  (confirm?.kind === 'withdraw' && confirm.id === p.id ? (
                    <div className="space-y-2 pt-1">
                      <p className="text-sm font-semibold text-slate-800 break-words">{text.withdraw_confirm}</p>
                      <button type="button" aria-label={`client-proposal-withdraw-yes-${p.id}`} disabled={busy} onClick={() => void withdraw(p.id)} className={DANGER}>{text.withdraw_yes}</button>
                      <button type="button" aria-label={`client-proposal-withdraw-cancel-${p.id}`} onClick={() => setConfirm(null)} className={SECONDARY}>{t.common.cancel}</button>
                    </div>
                  ) : (
                    <button type="button" aria-label={`client-proposal-withdraw-${p.id}`} onClick={() => setConfirm({ kind: 'withdraw', id: p.id })} className={SECONDARY}>
                      <Ico>↩️</Ico>{text.withdraw}
                    </button>
                  ))}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
        <h3 className="text-base font-semibold text-slate-900 break-words">{text.journal_title}</h3>
        {journal.length === 0 ? (
          <p aria-label="client-journal-empty" className="text-sm text-slate-500 text-center py-2">{text.journal_empty}</p>
        ) : (
          <ul aria-label="client-journal-list" className="space-y-2">
            {journal.map((entry) => (
              <li key={entry.id} aria-label={`client-journal-${entry.id}`} className="rounded-xl border border-slate-200 p-3 space-y-1">
                <p className="text-sm font-semibold text-slate-900 break-words">{kindLabel(entry.kind)}</p>
                <p className="text-xs text-slate-500 break-words">
                  {date(entry.created_at)} · {formatDecimalMoney(entry.amount)} {entry.currency}
                  {entry.estimate_version ? ` · ${text.estimate_version.replace('{version}', String(entry.estimate_version))}` : ''}
                </p>
                <p className="text-sm text-slate-700 break-words">{text.signed_by.replace('{name}', entry.signer_name)}</p>
                {entry.comment && <p className="text-sm text-slate-700 whitespace-pre-wrap break-words">{text.comment_of_client.replace('{comment}', entry.comment)}</p>}
                <details>
                  <summary className="text-xs text-blue-700 cursor-pointer min-h-11 flex items-center">{text.statement_toggle}</summary>
                  <p className="text-xs text-slate-600 break-words whitespace-pre-wrap">{entry.statement}</p>
                </details>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
