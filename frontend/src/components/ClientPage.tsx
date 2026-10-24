import { FormEvent, ReactNode, useCallback, useEffect, useState } from 'react';
import { acceptPortalEstimate, decidePortalProposal, fetchPortalPage } from '../api/clientPortal';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import type { PortalConsent, PortalEstimate, PortalLine, PortalPage, PortalProposal, PortalStatement } from '../types/clientLink';
import { formatDecimalMoney, formatQuantity } from '../utils/format';
import { isLocale, LOCALES, LOCALE_NAMES, type Locale } from '../utils/locale';
import { formatNoteTime } from '../utils/noteFormat';

/** The secret of the link is what follows the `#` of the address: a browser never sends it to a server. */
export function tokenFromHash(hash: string): string {
  return hash.replace(/^#/, '').trim();
}

/** Where the open page of the client lives: `/c` (the secret is in the fragment). */
export function isClientPagePath(pathname: string): boolean {
  return pathname === '/c' || pathname === '/c/';
}

type Failure = 'not_found' | 'inactive' | 'limited' | 'error';

const CARD = 'pe-card rounded-2xl p-4 shadow-sm space-y-3';
const FIELD = 'w-full border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 pe-surface min-h-12';
const PRIMARY = 'w-full min-h-12 px-4 py-2 text-base bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50';
const SECONDARY = 'w-full min-h-12 px-4 py-2 text-base rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium hover:bg-slate-50 disabled:opacity-50';

function failureOf(err: unknown): Failure {
  if (err instanceof ApiError) {
    if (err.status === 404) return 'not_found';
    if (err.status === 410) return 'inactive';
    if (err.status === 429) return 'limited';
  }
  return 'error';
}

/** A box with the words the client agrees to, the name, and the button: the same for the estimate and for a proposal. */
function ConsentBox(props: {
  statement: PortalStatement;
  name: string;
  onName: (value: string) => void;
  agree: boolean;
  onAgree: (value: boolean) => void;
  label: string;
  busy: boolean;
  onSubmit: () => void;
  error: string | null;
  prefix: string;
  secondary?: { label: string; onClick: () => void };
}) {
  const { t } = useI18n();
  const text = t.client_page;
  const { statement, prefix } = props;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    event.stopPropagation();
    props.onSubmit();
  };
  return (
    <form aria-label={`${prefix}-form`} onSubmit={submit} className="space-y-3">
      <label className="block text-sm font-medium text-slate-700">
        {text.name_label}
        <input
          aria-label={`${prefix}-name`}
          autoComplete="name"
          value={props.name}
          maxLength={80}
          placeholder={text.name_placeholder}
          onChange={(e) => props.onName(e.target.value)}
          className={`${FIELD} mt-1`}
        />
      </label>
      <label className="flex items-start gap-3 text-sm text-slate-800 min-h-11 cursor-pointer">
        <input
          type="checkbox"
          aria-label={`${prefix}-agree`}
          checked={props.agree}
          onChange={(e) => props.onAgree(e.target.checked)}
          className="mt-1 h-6 w-6 shrink-0"
        />
        <span aria-label={`${prefix}-statement`} className="break-words">{statement.text}</span>
      </label>
      {statement.text !== statement.pl && (
        <p className="text-xs text-slate-500 break-words">
          <span className="font-semibold">{text.binding_pl}</span> {statement.pl}
        </p>
      )}
      {props.error && <p role="alert" className="text-sm text-red-600 break-words">{props.error}</p>}
      <button type="submit" aria-label={`${prefix}-submit`} disabled={props.busy} className={PRIMARY}>
        {props.busy ? text.sending : props.label}
      </button>
      {props.secondary && (
        <button type="button" aria-label={`${prefix}-back`} onClick={props.secondary.onClick} className={SECONDARY}>{props.secondary.label}</button>
      )}
    </form>
  );
}

function Totals({ estimate }: { estimate: PortalEstimate }) {
  const { t } = useI18n();
  const text = t.client_page;
  const money = (value: string | null) => `${formatDecimalMoney(value)} ${estimate.currency}`;
  const vatLine =
    estimate.vat_mode === 'RATE' && estimate.vat_rate_percent !== null
      ? { label: text.vat_rate.replace('{rate}', String(estimate.vat_rate_percent)), value: money(estimate.vat_amount) }
      : null;
  const row = 'flex items-baseline justify-between gap-3 text-sm';
  return (
    <div aria-label="client-totals" className="border-t border-slate-200 pt-3 space-y-1">
      {estimate.vat_mode === null ? (
        <div className={`${row} text-base font-semibold`}>
          <span>{text.total}</span>
          <span aria-label="client-total">{money(estimate.total)}</span>
        </div>
      ) : (
        <>
          <div className={row}>
            <span>{text.total_net}</span>
            <span aria-label="client-total-net">{money(estimate.total)}</span>
          </div>
          {vatLine ? (
            <div className={row}>
              <span>{vatLine.label}</span>
              <span aria-label="client-total-vat">{vatLine.value}</span>
            </div>
          ) : (
            <p className="text-xs text-slate-500">{text.vat_exempt}</p>
          )}
          <div className={`${row} text-base font-semibold`}>
            <span>{text.total_gross}</span>
            <span aria-label="client-total-gross">{money(estimate.gross_total)}</span>
          </div>
        </>
      )}
    </div>
  );
}

/** The lines of one room together (a room's walls are interleaved with the other rooms' in the estimate), the rooms in the order they first appear. */
function groupByRoom(lines: PortalLine[], other: string): { room: string; lines: PortalLine[] }[] {
  const groups: { room: string; lines: PortalLine[] }[] = [];
  for (const line of lines) {
    const room = line.room_name ?? other;
    const found = groups.find((group) => group.room === room);
    if (found) found.lines.push(line);
    else groups.push({ room, lines: [line] });
  }
  return groups;
}

/**
 * The open page of the client (V2-8): the contractor, the estimate with its sums, the approval, the proposals of extra work. No login, nothing is
 * kept in the browser; the language of the page is the one the contractor chose and the client may change it.
 */
export function ClientPage({ token }: { token: string }) {
  const { t, locale, setLocale } = useI18n();
  const text = t.client_page;
  const [page, setPage] = useState<PortalPage | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [name, setName] = useState('');
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState<{ id: string; decision: 'ACCEPT' | 'DECLINE' } | null>(null);

  useEffect(() => {
    document.title = 'Plan & Estimate';
    const meta = [
      ['robots', 'noindex, nofollow'],
      ['referrer', 'no-referrer'],
    ] as const;
    const added = meta.map(([key, content]) => {
      const el = document.createElement('meta');
      el.name = key;
      el.content = content;
      document.head.appendChild(el);
      return el;
    });
    return () => added.forEach((el) => el.remove());
  }, []);

  const load = useCallback(
    async (lang: Locale | null, first = false) => {
      if (token === '') {
        setFailure('not_found');
        return;
      }
      try {
        const loaded = await fetchPortalPage(token, lang);
        setPage(loaded);
        setFailure(null);
        if (first && isLocale(loaded.lang)) setLocale(loaded.lang);
      } catch (err) {
        setFailure(failureOf(err));
      }
    },
    [token, setLocale],
  );

  useEffect(() => {
    void load(null, true);
  }, [load]);

  const changeLanguage = (next: Locale) => {
    setLocale(next);
    void load(next);
  };

  const codeText = (err: unknown): string => {
    const code = err instanceof ApiError ? (err.status === 0 ? 'NETWORK' : err.code) : undefined;
    const table = text.errors as Record<string, string>;
    return (code && table[code]) || table.GENERIC;
  };

  const act = async (action: () => Promise<PortalPage>, done: () => void) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      setPage(await action());
      done();
    } catch (err) {
      setError(codeText(err));
      if (err instanceof ApiError && (err.status === 404 || err.status === 410)) setFailure(failureOf(err));
    } finally {
      setBusy(false);
    }
  };

  const accept = (estimate: PortalEstimate) =>
    act(
      () => acceptPortalEstimate(token, locale, { estimate_id: estimate.id, version: estimate.version, hash: estimate.hash, signer_name: name, agree }),
      () => {
        setAgree(false);
      },
    );
  const decide = (proposal: PortalProposal, decision: 'ACCEPT' | 'DECLINE') =>
    act(
      () => decidePortalProposal(token, proposal.id, locale, { decision, hash: proposal.hash, signer_name: name, agree }),
      () => {
        setChoice(null);
        setAgree(false);
      },
    );

  const date = (iso: string) => formatNoteTime(iso, locale);
  const consentLine = (consent: PortalConsent) => text.accepted_by.replace('{name}', consent.signer_name).replace('{date}', date(consent.created_at));

  const header = (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-semibold text-slate-700">Plan &amp; Estimate</span>
      <label className="text-xs text-slate-600 flex items-center gap-2">
        <span className="sr-only">{text.language}</span>
        <select
          aria-label="client-language"
          value={locale}
          onChange={(e) => changeLanguage(e.target.value as Locale)}
          className="border border-slate-200 rounded-xl px-2 min-h-11 text-sm pe-surface text-slate-900"
        >
          {LOCALES.map((code) => (
            <option key={code} value={code}>{LOCALE_NAMES[code]}</option>
          ))}
        </select>
      </label>
    </div>
  );

  const shell = (children: ReactNode) => (
    <main className="min-h-screen w-full max-w-xl mx-auto px-4 py-4 space-y-3 overflow-x-hidden" aria-label="client-page">
      {header}
      {children}
    </main>
  );

  if (failure !== null && (page === null || failure === 'inactive' || failure === 'not_found')) {
    const key = { not_found: 'not_found', inactive: 'inactive', limited: 'limited', error: 'error' }[failure];
    const title = text[`${key}_title` as 'not_found_title'];
    const body = text[`${key}_text` as 'not_found_text'];
    return shell(
      <div aria-label={`client-${failure}`} className={CARD}>
        <h1 className="text-lg font-semibold text-slate-900 break-words">{title}</h1>
        <p className="text-sm text-slate-600 break-words">{body}</p>
        {failure === 'error' && (
          <button type="button" aria-label="client-retry" onClick={() => void load(null, true)} className={PRIMARY}>{text.retry}</button>
        )}
      </div>,
    );
  }

  if (page === null) {
    return shell(<p aria-label="client-loading" className="text-sm text-slate-500 text-center py-6">{text.loading}</p>);
  }

  const { contractor, project, estimate, proposals } = page;
  const decided = proposals.filter((p) => p.status !== 'OPEN');
  const open = proposals.filter((p) => p.status === 'OPEN');

  return shell(
    <>
      <section aria-label="client-contractor" className={CARD}>
        <p className="text-xs font-semibold uppercase text-slate-500">{text.contractor}</p>
        <p className="text-lg font-semibold text-slate-900 break-words">{contractor.name ?? '—'}</p>
        <div className="flex flex-col gap-2">
          {contractor.phone && (
            <a aria-label="client-call" href={`tel:${contractor.phone}`} className={`${SECONDARY} flex items-center justify-center text-center`}>
              {text.call}: {contractor.phone}
            </a>
          )}
          {contractor.email && (
            <a aria-label="client-mail" href={`mailto:${contractor.email}`} className={`${SECONDARY} flex items-center justify-center text-center break-all`}>
              {text.write}: {contractor.email}
            </a>
          )}
        </div>
        <p className="text-xs font-semibold uppercase text-slate-500 pt-1">{text.object}</p>
        <p className="text-sm text-slate-900 break-words">
          {project.name}
          <br />
          {project.address}, {project.postal_code} {project.city}
        </p>
      </section>

      {estimate === null ? (
        <p aria-label="client-no-estimate" className="text-sm text-slate-600 text-center py-4 break-words">{text.no_estimate}</p>
      ) : (
        <section aria-label="client-estimate" className={CARD}>
          <h1 className="text-lg font-semibold text-slate-900 break-words">{text.estimate_title.replace('{version}', String(estimate.version))}</h1>
          {groupByRoom(estimate.lines, text.room_other).map((group, index) => (
            <div key={`${group.room}-${index}`} className="space-y-2">
              <h2 className="text-sm font-semibold text-slate-700 break-words">{group.room}</h2>
              <ul className="space-y-2">
                {group.lines.map((line) => (
                  <li key={line.position} className="rounded-xl border border-slate-200 p-3 space-y-1">
                    {line.surface_name && <p className="text-xs font-semibold text-slate-500 break-words">{line.surface_name}</p>}
                    <p className="text-sm text-slate-900 break-words">{line.description}</p>
                    <div className="flex items-baseline justify-between gap-3 text-xs text-slate-500">
                      <span className="break-words min-w-0">
                        {text.line_calc
                          .replace('{quantity}', formatQuantity(line.quantity, line.unit))
                          .replace('{unit}', t.pricebook.units[line.unit as keyof typeof t.pricebook.units] ?? line.unit)
                          .replace('{price}', formatDecimalMoney(line.unit_price))}
                      </span>
                      <span className="text-sm font-semibold text-slate-900 shrink-0">{formatDecimalMoney(line.amount)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <Totals estimate={estimate} />

          {estimate.consent ? (
            <div aria-label="client-estimate-accepted" className="rounded-xl bg-emerald-50 border border-emerald-200 p-3">
              <p className="text-sm font-semibold text-emerald-800 break-words">{text.accepted_title}</p>
              <p className="text-xs text-emerald-800 break-words">{consentLine(estimate.consent)}</p>
            </div>
          ) : estimate.accept_statement ? (
            <div className="space-y-3 border-t border-slate-200 pt-3">
              <h2 className="text-base font-semibold text-slate-900 break-words">{text.accept_heading}</h2>
              <ConsentBox
                prefix="client-accept"
                statement={estimate.accept_statement}
                name={name}
                onName={setName}
                agree={agree}
                onAgree={setAgree}
                label={text.accept_button}
                busy={busy}
                error={choice === null ? error : null}
                onSubmit={() => void accept(estimate)}
              />
            </div>
          ) : null}
        </section>
      )}

      {proposals.length > 0 && (
        <section aria-label="client-proposals" className={CARD}>
          <h2 className="text-lg font-semibold text-slate-900 break-words">{text.proposals_title}</h2>
          <p className="text-xs text-slate-500 break-words">{text.proposals_intro}</p>
          {[...open, ...decided].map((proposal) => {
            const picked = choice?.id === proposal.id ? choice.decision : null;
            const statement = picked === 'DECLINE' ? proposal.decline_statement : proposal.accept_statement;
            return (
              <article key={proposal.id} aria-label={`client-proposal-${proposal.id}`} className="rounded-xl border border-slate-200 p-3 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-base font-semibold text-slate-900">{formatDecimalMoney(proposal.amount)} {proposal.currency}</span>
                  {proposal.extra_days ? <span className="text-xs text-slate-500">{text.days_shift.replace('{days}', String(proposal.extra_days))}</span> : null}
                </div>
                <p className="text-sm font-medium text-slate-900 break-words">{proposal.title}</p>
                {proposal.description && <p className="text-sm text-slate-600 whitespace-pre-wrap break-words">{proposal.description}</p>}
                {proposal.consent ? (
                  <div
                    aria-label={`client-proposal-decided-${proposal.id}`}
                    className={`rounded-xl p-3 border ${proposal.status === 'ACCEPTED' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-slate-100 border-slate-200 text-slate-700'}`}
                  >
                    <p className="text-sm font-semibold break-words">{proposal.status === 'ACCEPTED' ? text.status_accepted : text.status_declined}</p>
                    <p className="text-xs break-words">{consentLine(proposal.consent)}</p>
                  </div>
                ) : picked === null ? (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-slate-500">{text.decision_label}</p>
                    <button type="button" aria-label={`client-proposal-agree-${proposal.id}`} onClick={() => { setChoice({ id: proposal.id, decision: 'ACCEPT' }); setAgree(false); setError(null); }} className={PRIMARY}>
                      {text.agree_button}
                    </button>
                    <button type="button" aria-label={`client-proposal-decline-${proposal.id}`} onClick={() => { setChoice({ id: proposal.id, decision: 'DECLINE' }); setAgree(false); setError(null); }} className={SECONDARY}>
                      {text.decline_button}
                    </button>
                  </div>
                ) : statement ? (
                  <ConsentBox
                    prefix={`client-decide-${proposal.id}`}
                    statement={statement}
                    name={name}
                    onName={setName}
                    agree={agree}
                    onAgree={setAgree}
                    label={text.send_decision}
                    busy={busy}
                    error={error}
                    onSubmit={() => void decide(proposal, picked)}
                    secondary={{ label: text.cancel, onClick: () => { setChoice(null); setError(null); } }}
                  />
                ) : null}
              </article>
            );
          })}
        </section>
      )}

      <p aria-label="client-expires" className="text-xs text-slate-500 text-center break-words pb-4">{text.expires.replace('{date}', date(page.link.expires_at))}</p>
    </>,
  );
}
