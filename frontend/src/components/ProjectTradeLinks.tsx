import { useCallback, useEffect, useState } from 'react';
import {
  changeTradeLinkNote,
  createTradeLink,
  extendTradeLink,
  fetchTradeAnswers,
  fetchTradeLinks,
  revokeTradeLink,
} from '../api/tradeLinks';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import {
  LINK_TRADES,
  TRADE_LINK_LIMITS,
  tradeLinkUrl,
  type LinkTrade,
  type OwnAnswer,
  type TradeAnswersResponse,
  type TradeLinkInfo,
  type TradeLinksResponse,
  type TypicalAnswer,
} from '../types/tradeLink';
import { copyTextToClipboard } from '../utils/clipboard';
import { formatQuantity } from '../utils/format';
import { LOCALES, LOCALE_NAMES, type Locale } from '../utils/locale';
import { formatNoteTime } from '../utils/noteFormat';
import { Ico } from './Ico';

interface ProjectTradeLinksProps {
  projectId: string;
}

const PRIMARY = 'w-full min-h-11 px-4 py-1 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50';
const SECONDARY = 'w-full min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium hover:bg-slate-50 disabled:opacity-50';
const DANGER = 'w-full min-h-11 px-3 py-1 text-sm bg-red-600 text-white font-semibold rounded-xl hover:bg-red-700 disabled:opacity-50';
const FIELD = 'w-full border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 pe-surface min-h-11';

type Confirm = 'new' | 'revoke' | null;

function quantityText(row: { quantity: string | null; unit: 'PCS' | 'LM' }, pcs: string, lm: string): string {
  if (row.quantity === null) return '';
  return `${formatQuantity(row.quantity, row.unit)} ${row.unit === 'PCS' ? pcs : lm}`;
}

/** The answers of the craftsman, room by room: only the positions he answered. */
function Answers({ data, trade }: { data: TradeAnswersResponse; trade: LinkTrade }) {
  const { t, locale } = useI18n();
  const text = t.trade_links;
  const names = t.master_page.positions as Record<string, string>;
  const pcs = t.master_page.unit_PCS;
  const lm = t.master_page.unit_LM;
  const answered = data.rooms.filter((room) => room.typical.length > 0 || room.own.length > 0);

  const line = (row: TypicalAnswer | OwnAnswer, label: string, key: string) => (
    <li key={key} className="text-sm text-slate-800 break-words">
      <span className="font-medium">{label}</span>
      {row.quantity !== null && <span>{`: ${quantityText(row, pcs, lm)}`}</span>}
      {row.note && <span className="block text-xs text-slate-500 whitespace-pre-wrap">{row.note}</span>}
    </li>
  );

  return (
    <div aria-label={`trade-answers-${trade}`} className="space-y-3">
      <h4 className="text-sm font-semibold text-slate-800 break-words">{text.answers_title}</h4>
      {answered.length === 0 ? (
        <p aria-label={`trade-answers-empty-${trade}`} className="text-sm text-slate-500 break-words">{text.answers_empty}</p>
      ) : (
        answered.map((room) => (
          <div key={room.room_id} className="rounded-xl border border-slate-200 p-3 space-y-1">
            <p className="text-sm font-semibold text-slate-900 break-words">{room.room_name}</p>
            <ul className="space-y-1">
              {room.typical.map((row) => line(row, names[row.key] ?? row.key, `t-${row.key}`))}
              {room.own.map((row, index) => line(row, row.name, `o-${index}`))}
            </ul>
          </div>
        ))
      )}
      <h4 className="text-sm font-semibold text-slate-800 break-words">{text.journal_title}</h4>
      {data.submissions.length === 0 ? (
        <p aria-label={`trade-journal-empty-${trade}`} className="text-sm text-slate-500 break-words">{text.journal_empty}</p>
      ) : (
        <ul aria-label={`trade-journal-${trade}`} className="space-y-1">
          {data.submissions.map((row) => (
            <li key={row.id} className="text-sm text-slate-700 break-words">
              {text.journal_row.replace('{name}', row.master_name).replace('{count}', String(row.answers_count)).replace('{date}', formatNoteTime(row.created_at, locale))}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TradeCard(props: { projectId: string; trade: LinkTrade; link: TradeLinkInfo | null; onChange: (trade: LinkTrade, link: TradeLinkInfo | null) => void }) {
  const { projectId, trade, link, onChange } = props;
  const { t, locale } = useI18n();
  const text = t.trade_links;
  const [language, setLanguage] = useState<Locale>(link?.language ?? locale);
  const [note, setNote] = useState(link?.owner_note ?? '');
  const [token, setToken] = useState<string | null>(null);
  const [answers, setAnswers] = useState<TradeAnswersResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const say = (kind: 'ok' | 'error', value: string) => setMessage({ kind, text: value });
  const fail = (err: unknown) => {
    const code = err instanceof ApiError ? err.code : undefined;
    const known = code ? (text.errors as Record<string, string>)[code] : undefined;
    say('error', known ?? text.save_error);
  };
  const date = (iso: string) => formatNoteTime(iso, locale);

  const loadAnswers = useCallback(async () => {
    try {
      setAnswers(await fetchTradeAnswers(projectId, trade));
    } catch {
      setAnswers(null);
    }
  }, [projectId, trade]);

  const answersKey = link ? `${link.answers_count}-${link.submissions_count}-${link.last_submitted_at ?? ''}` : '';
  useEffect(() => {
    if (link) void loadAnswers();
    else setAnswers(null);
  }, [link === null, answersKey, loadAnswers]); // eslint-disable-line react-hooks/exhaustive-deps

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
      const issued = await createTradeLink(projectId, trade, language, note.trim() === '' ? null : note);
      onChange(trade, issued.link);
      setToken(issued.token);
      say('ok', text.created);
    });
  const extend = () =>
    run(async () => {
      onChange(trade, await extendTradeLink(projectId, trade));
      say('ok', text.extended);
    });
  const revoke = () =>
    run(async () => {
      await revokeTradeLink(projectId, trade);
      onChange(trade, null);
      setToken(null);
      say('ok', text.revoked);
    });
  const saveNote = () =>
    run(async () => {
      onChange(trade, await changeTradeLinkNote(projectId, trade, note.trim() === '' ? null : note));
      say('ok', text.note_saved);
    });

  const url = token ? tradeLinkUrl(window.location.origin, token) : null;
  const copy = async () => {
    if (!url) return;
    const done = await copyTextToClipboard(url);
    say(done ? 'ok' : 'error', done ? text.copied : text.copy_failed);
  };
  const share = () => {
    if (!url) return;
    const shareText = text.share_text.replace('{trade}', text.trade_short[trade]);
    const telegram = window.Telegram?.WebApp;
    if (telegram?.openTelegramLink) {
      telegram.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(shareText)}`);
    } else if (typeof navigator.share === 'function') {
      void navigator.share({ url, text: shareText }).catch(() => undefined);
    } else {
      void copy();
    }
  };

  const noteField = (
    <label className="block text-sm font-medium text-slate-700">
      {text.note_label}
      <textarea
        aria-label={`trade-link-note-${trade}`}
        value={note}
        maxLength={TRADE_LINK_LIMITS.comment}
        placeholder={text.note_placeholder}
        onChange={(e) => setNote(e.target.value)}
        className={`${FIELD} mt-1 min-h-24`}
      />
    </label>
  );

  return (
    <section aria-label={`trade-card-${trade}`} className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="text-base font-semibold text-slate-900 break-words">{text.trade_short[trade]}</h3>

      {link === null ? (
        <>
          <label className="block text-sm font-medium text-slate-700">
            {text.language_label}
            <select aria-label={`trade-link-language-${trade}`} value={language} onChange={(e) => setLanguage(e.target.value as Locale)} className={`${FIELD} mt-1`}>
              {LOCALES.map((code) => (
                <option key={code} value={code}>{LOCALE_NAMES[code]}</option>
              ))}
            </select>
          </label>
          {noteField}
          <button type="button" aria-label={`trade-link-create-${trade}`} disabled={busy} onClick={() => void makeLink()} className={PRIMARY}>
            <Ico>🔗</Ico>{text.create}
          </button>
        </>
      ) : (
        <>
          <p aria-label={`trade-link-term-${trade}`} className={`text-sm font-semibold break-words ${link.expired ? 'text-red-700' : 'text-emerald-700'}`}>
            {(link.expired ? text.expired_on : text.active_until).replace('{date}', date(link.expires_at))}
          </p>
          <p aria-label={`trade-link-views-${trade}`} className="text-xs text-slate-500 break-words">
            {link.view_count === 0 || !link.last_viewed_at
              ? text.never_opened
              : text.opened_times.replace('{count}', String(link.view_count)).replace('{date}', date(link.last_viewed_at))}
          </p>
          <p aria-label={`trade-link-sent-${trade}`} className="text-xs text-slate-500 break-words">
            {link.last_submitted_at
              ? text.sent_times.replace('{count}', String(link.submissions_count)).replace('{date}', date(link.last_submitted_at))
              : text.never_sent}
          </p>

          {url ? (
            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-700">
                {text.url_label}
                <input aria-label={`trade-link-url-${trade}`} readOnly value={url} onFocus={(e) => e.currentTarget.select()} className={`${FIELD} mt-1 text-sm break-all`} />
              </label>
              <p className="text-xs text-slate-500 break-words">{text.url_once}</p>
              <div className="flex flex-col gap-2">
                <button type="button" aria-label={`trade-link-share-${trade}`} onClick={share} className={PRIMARY}><Ico>📤</Ico>{text.share}</button>
                <button type="button" aria-label={`trade-link-copy-${trade}`} onClick={() => void copy()} className={SECONDARY}><Ico>📋</Ico>{text.copy}</button>
              </div>
            </div>
          ) : (
            <p aria-label={`trade-link-hidden-${trade}`} className="text-xs text-slate-500 break-words">{text.url_hidden}</p>
          )}

          {noteField}
          <button type="button" aria-label={`trade-link-note-save-${trade}`} disabled={busy || note.trim() === (link.owner_note ?? '')} onClick={() => void saveNote()} className={SECONDARY}>
            <Ico>💾</Ico>{text.note_save}
          </button>

          {confirm === 'new' ? (
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-800 break-words">{text.new_confirm}</p>
              <button type="button" aria-label={`trade-link-new-yes-${trade}`} disabled={busy} onClick={() => void makeLink()} className={PRIMARY}>{text.new_yes}</button>
              <button type="button" aria-label={`trade-link-new-cancel-${trade}`} onClick={() => setConfirm(null)} className={SECONDARY}>{t.common.cancel}</button>
            </div>
          ) : confirm === 'revoke' ? (
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-800 break-words">{text.revoke_confirm}</p>
              <button type="button" aria-label={`trade-link-revoke-yes-${trade}`} disabled={busy} onClick={() => void revoke()} className={DANGER}>{text.revoke_yes}</button>
              <button type="button" aria-label={`trade-link-revoke-cancel-${trade}`} onClick={() => setConfirm(null)} className={SECONDARY}>{t.common.cancel}</button>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <button type="button" aria-label={`trade-link-extend-${trade}`} disabled={busy} onClick={() => void extend()} className={SECONDARY}><Ico>⏳</Ico>{text.extend}</button>
              <button type="button" aria-label={`trade-link-new-${trade}`} disabled={busy} onClick={() => setConfirm('new')} className={SECONDARY}><Ico>🔄</Ico>{text.new_link}</button>
              <button type="button" aria-label={`trade-link-revoke-${trade}`} disabled={busy} onClick={() => setConfirm('revoke')} className={SECONDARY}><Ico>🚫</Ico>{text.revoke}</button>
            </div>
          )}
        </>
      )}

      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>
          {message.text}
        </p>
      )}

      {answers && link && <Answers data={answers} trade={trade} />}
    </section>
  );
}

/**
 * The links for the electrician and the plumber (V2-14), the owner's screen of an object: one card per trade -- make, copy, send, extend and revoke the
 * link, write a word to the craftsman, read what he answered by room and the journal of what he sent. The secret is shown only in the session that made it.
 */
export function ProjectTradeLinks({ projectId }: ProjectTradeLinksProps) {
  const { t } = useI18n();
  const text = t.trade_links;
  const [links, setLinks] = useState<TradeLinksResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      setLinks(await fetchTradeLinks(projectId));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const change = (trade: LinkTrade, link: TradeLinkInfo | null) =>
    setLinks((current) => (current ? { ...current, [trade === 'ELECTRIC' ? 'electric' : 'plumbing']: link } : current));

  if (loading) return <p className="text-sm text-slate-500 text-center py-4">{text.loading}</p>;
  if (loadFailed || links === null) {
    return (
      <div className="space-y-2">
        <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
        <button type="button" aria-label="trade-links-retry" onClick={() => void load()} className={PRIMARY}><Ico>🔄</Ico>{text.retry}</button>
      </div>
    );
  }

  return (
    <section aria-label="project-trade-links" className="space-y-3">
      <div className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
        <p className="text-sm text-slate-700 break-words">{text.intro}</p>
        <p className="text-xs text-slate-500 break-words">{text.no_prices_hint}</p>
      </div>
      {LINK_TRADES.map((trade) => (
        <TradeCard key={trade} projectId={projectId} trade={trade} link={trade === 'ELECTRIC' ? links.electric : links.plumbing} onChange={change} />
      ))}
    </section>
  );
}
