import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchKnowledgeEntry,
  fetchKnowledgeMeta,
  fetchKnowledgeSituation,
  listKnowledgeEntries,
  listKnowledgeSituations,
} from '../api/knowledge';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import type {
  KnowledgeEntryDetail,
  KnowledgeEntryItem,
  KnowledgeMeta,
  KnowledgeSituation,
  KnowledgeSituationItem,
} from '../types/knowledge';
import { documentKindLabel } from '../utils/documentFormat';
import { clientPhraseText } from '../utils/knowledgePhrases';
import type { DocumentKind } from '../types/document';
import { KeyPoints, SourceLink, StatusBadge } from './KnowledgeEntryParts';
import { Ico } from './Ico';

type View = { kind: 'list' } | { kind: 'entry'; code: string } | { kind: 'situation'; code: string };

interface KnowledgeBaseProps {
  backSuspended?: boolean;
}

const SEARCH_DELAY_MS = 250;
const CARD = 'bg-white border border-slate-200 rounded-2xl p-3 shadow-sm';

function fill(template: string, values: Record<string, string | number>): string {
  return Object.entries(values).reduce((text, [key, value]) => text.replace(`{${key}}`, String(value)), template);
}

/**
 * The knowledge base (Stage 17D), read only. Q6: a list of titles first, the details and the links on tap. The server
 * searches and decides what exists; the screen only shows it, in the language of the application. A draft is marked as a
 * draft everywhere (Q7) -- the owner sees it, a client never does.
 */
export function KnowledgeBase({ backSuspended = false }: KnowledgeBaseProps) {
  const { t, locale } = useI18n();
  const text = t.knowledge;
  const [stack, setStack] = useState<View[]>([{ kind: 'list' }]);
  const view = stack[stack.length - 1];
  const open = (next: View) => setStack((current) => [...current, next]);
  const back = useCallback(() => setStack((current) => (current.length > 1 ? current.slice(0, -1) : current)), []);

  useTelegramBackButton(stack.length > 1 && !backSuspended, back);

  const title = (item: { title_pl: string; title_ru: string }) => (locale === 'ru' ? item.title_ru : item.title_pl);

  return (
    <section aria-label="knowledge-section" className="w-full mt-4 space-y-3">
      {view.kind !== 'list' && (
        <button
          type="button"
          aria-label="knowledge-back"
          onClick={back}
          className="min-h-11 px-3 text-sm font-semibold rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-200"
        >
          ← {text.back}
        </button>
      )}
      {view.kind === 'list' && <KnowledgeList title={title} onOpenEntry={(code) => open({ kind: 'entry', code })} onOpenSituation={(code) => open({ kind: 'situation', code })} />}
      {view.kind === 'entry' && <KnowledgeEntryCard code={view.code} title={title} />}
      {view.kind === 'situation' && <KnowledgeSituationPlayer code={view.code} title={title} onOpenEntry={(code) => open({ kind: 'entry', code })} />}
    </section>
  );
}

interface TitleProps {
  title: (item: { title_pl: string; title_ru: string }) => string;
}

function KnowledgeList({ title, onOpenEntry, onOpenSituation }: TitleProps & { onOpenEntry: (code: string) => void; onOpenSituation: (code: string) => void }) {
  const { t, locale } = useI18n();
  const text = t.knowledge;
  const [meta, setMeta] = useState<KnowledgeMeta | null>(null);
  const [situations, setSituations] = useState<KnowledgeSituationItem[]>([]);
  const [entries, setEntries] = useState<KnowledgeEntryItem[] | null>(null);
  const [query, setQuery] = useState('');
  const [failed, setFailed] = useState(false);
  // only the answer of the last request counts: a slow earlier one must not replace a newer list
  const request = useRef(0);

  const loadEntries = useCallback(async (q: string) => {
    const mine = ++request.current;
    try {
      const data = await listKnowledgeEntries(q);
      if (mine === request.current) {
        setEntries(data.items);
        setFailed(false);
      }
    } catch {
      if (mine === request.current) setFailed(true);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    void fetchKnowledgeMeta().then((data) => alive && setMeta(data)).catch(() => undefined);
    void listKnowledgeSituations().then((data) => alive && setSituations(data.items)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadEntries(query), query ? SEARCH_DELAY_MS : 0);
    return () => window.clearTimeout(timer);
  }, [query, loadEntries]);

  const disclaimer = meta ? (locale === 'ru' ? meta.disclaimer_ru : meta.disclaimer_pl) : null;
  const hasDraft = entries?.some((entry) => entry.status === 'DRAFT') ?? false;

  return (
    <>
      <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{text.title}</h2>
      <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>
      {disclaimer && meta?.disclaimer_status === 'APPROVED' && (
        <p aria-label="knowledge-disclaimer" className="text-xs text-slate-600 break-words bg-slate-50 border border-slate-200 rounded-xl p-2">
          {disclaimer}
        </p>
      )}
      {hasDraft && (
        <p aria-label="knowledge-draft-notice" className="text-xs text-amber-900 break-words bg-amber-50 border border-amber-200 rounded-xl p-2">
          {text.draft_notice}
        </p>
      )}

      <input
        type="search"
        aria-label="knowledge-search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={text.search_placeholder}
        maxLength={100}
        autoComplete="off"
        enterKeyHint="search"
        className="w-full min-h-12 px-3 text-base rounded-xl border border-slate-300 bg-white text-slate-900"
      />

      {situations.length > 0 && !query && (
        <div aria-label="knowledge-situations" className="space-y-2">
          <h3 className="text-sm font-bold text-slate-700">{text.situations_title}</h3>
          <ul className="space-y-2">
            {situations.map((situation) => (
              <li key={situation.code}>
                <button
                  type="button"
                  aria-label={`knowledge-situation-${situation.code}`}
                  onClick={() => onOpenSituation(situation.code)}
                  className="w-full min-h-12 px-4 py-2 text-left text-sm font-semibold rounded-xl bg-blue-50 text-blue-900 hover:bg-blue-100 break-words"
                >
                  {title(situation)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {failed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{text.error_load}</p>
          <button
            type="button"
            aria-label="knowledge-retry"
            onClick={() => void loadEntries(query)}
            className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white"
          >
            <Ico>🔄</Ico>{text.retry}
          </button>
        </div>
      )}
      {!failed && entries === null && <p className="text-sm text-slate-500">{text.loading}</p>}

      {!failed && entries !== null && (
        <div className="space-y-2">
          <h3 className="text-sm font-bold text-slate-700">
            {text.entries_title}
            <span aria-label="knowledge-count" className="ml-2 font-normal text-slate-500">{fill(text.count, { count: entries.length })}</span>
          </h3>
          {entries.length === 0 ? (
            <p aria-label="knowledge-empty" className="text-sm text-slate-400 text-center py-6">{query ? text.empty : text.empty_all}</p>
          ) : (
            <ul aria-label="knowledge-entries" className="space-y-2">
              {entries.map((entry) => (
                <li key={entry.code}>
                  <button
                    type="button"
                    aria-label={`knowledge-entry-${entry.code}`}
                    onClick={() => onOpenEntry(entry.code)}
                    className={`${CARD} w-full min-h-14 text-left space-y-1 hover:bg-slate-50`}
                  >
                    <span className="block text-sm font-semibold text-slate-900 break-words">{title(entry)}</span>
                    <span className="block text-xs text-slate-500 break-words">
                      {[entry.source_designation, entry.locator].filter(Boolean).join(' · ')}
                    </span>
                    {entry.status === 'DRAFT' && <StatusBadge status="DRAFT" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}

function KnowledgeEntryCard({ code, title }: TitleProps & { code: string }) {
  const { t } = useI18n();
  const text = t.knowledge;
  const [detail, setDetail] = useState<KnowledgeEntryDetail | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      setDetail(await fetchKnowledgeEntry(code));
    } catch {
      setFailed(true);
    }
  }, [code]);

  useEffect(() => {
    void load();
  }, [load]);

  if (failed) {
    return (
      <div className="space-y-2">
        <p role="alert" className="text-sm text-red-600 break-words">{text.error_load}</p>
        <button type="button" aria-label="knowledge-retry" onClick={() => void load()} className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white">
          <Ico>🔄</Ico>{text.retry}
        </button>
      </div>
    );
  }
  if (!detail) return <p className="text-sm text-slate-500">{text.loading}</p>;

  const { entry, source, places } = detail;
  const openNotes = entry.review_notes.filter((note) => note.status === 'OPEN');
  // a person reads the paragraph of the contract and the name of a document; the many risks and phrases that share an entry
  // are counted, not listed (17E.1)
  const placeLabels: string[] = [];
  for (const place of places) {
    if (place.target_kind === 'CLAUSE') {
      placeLabels.push(
        place.section_number !== null && place.clause_number !== null
          ? fill(text.place_clause, { section: place.section_number, clause: place.clause_number, title: place.section_title_pl ?? '' })
          : place.target,
      );
    } else if (place.target_kind === 'DOCUMENT') {
      placeLabels.push(fill(text.place_document, { name: documentKindLabel(t.documents, place.target as DocumentKind) }));
    }
  }
  const risks = places.filter((place) => place.target_kind === 'RISK').length;
  const phrases = places.filter((place) => place.target_kind === 'PHRASE').length;
  if (risks > 0) placeLabels.push(fill(text.place_risks, { count: risks }));
  if (phrases > 0) placeLabels.push(fill(text.place_phrases, { count: phrases }));

  return (
    <article aria-label={`knowledge-card-${entry.code}`} className={`${CARD} space-y-3`}>
      <header className="space-y-1">
        <h2 className="text-lg font-bold text-slate-900 break-words">{title(entry)}</h2>
        <p className="text-xs text-slate-500 break-words">{[source.designation, entry.locator].filter(Boolean).join(' · ')}</p>
        <StatusBadge status={entry.status} />
        {entry.status === 'DRAFT' && <p className="text-xs text-amber-900 break-words">{text.draft_notice}</p>}
      </header>

      <KeyPoints entry={entry} />

      {placeLabels.length > 0 && (
        <section aria-label="knowledge-linked" className="space-y-1">
          <h3 className="text-sm font-bold text-slate-700">{text.linked_title}</h3>
          <ul className="space-y-1">
            {placeLabels.map((label) => (
              <li key={label} className="px-2 py-1 text-xs rounded-lg bg-slate-100 text-slate-700 break-words">
                {label}
              </li>
            ))}
          </ul>
        </section>
      )}

      {openNotes.length > 0 && (
        <details aria-label="knowledge-notes" className="rounded-xl border border-slate-200 p-2">
          <summary className="min-h-11 flex items-center text-sm font-semibold text-slate-700">{fill(text.notes_title, { count: openNotes.length })}</summary>
          <ul className="space-y-2 pt-1">
            {openNotes.map((note) => (
              <li key={note.ref} className="text-xs text-slate-700 break-words">
                <span className="font-semibold">{note.ref}:</span> {note.text}
              </li>
            ))}
          </ul>
        </details>
      )}

      <footer aria-label="knowledge-source" className="space-y-1 border-t border-slate-200 pt-2">
        <h3 className="text-sm font-bold text-slate-700">{text.source_title}</h3>
        <p className="text-xs text-slate-600 break-words">{text[`kind_${source.kind}` as const]} — {source.title_pl}</p>
        <p aria-label="knowledge-current-text" className="text-xs font-semibold text-slate-700 break-words">{fill(text.current_text, { designation: source.designation })}</p>
        <p className="text-xs text-slate-500 break-words">
          {entry.checked_on ? fill(text.checked_on, { date: entry.checked_on }) : text.not_checked}
        </p>
        {entry.approved_by && entry.approved_on && (
          <p className="text-xs text-slate-500 break-words">{fill(text.approved_by, { name: entry.approved_by, date: entry.approved_on })}</p>
        )}
        <SourceLink source={source} />
      </footer>
    </article>
  );
}

function KnowledgeSituationPlayer({ code, title, onOpenEntry }: TitleProps & { code: string; onOpenEntry: (code: string) => void }) {
  const { t, locale } = useI18n();
  const text = t.knowledge;
  const [situation, setSituation] = useState<KnowledgeSituation | null>(null);
  const [failed, setFailed] = useState(false);
  // the nodes the owner has passed, then the node on the screen
  const [path, setPath] = useState<string[]>([]);
  // the titles of the entries an outcome points at (the situation itself holds only their codes)
  const [titles, setTitles] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setFailed(false);
    try {
      const data = await fetchKnowledgeSituation(code);
      setSituation(data);
      setPath([data.start]);
    } catch {
      setFailed(true);
    }
  }, [code]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let alive = true;
    void listKnowledgeEntries()
      .then((data) => alive && setTitles(Object.fromEntries(data.items.map((item) => [item.code, locale === 'ru' ? item.title_ru : item.title_pl]))))
      .catch(() => undefined); // without titles the buttons show the codes
    return () => {
      alive = false;
    };
  }, [locale]);

  if (failed) {
    return (
      <div className="space-y-2">
        <p role="alert" className="text-sm text-red-600 break-words">{text.error_load}</p>
        <button type="button" aria-label="knowledge-retry" onClick={() => void load()} className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white">
          <Ico>🔄</Ico>{text.retry}
        </button>
      </div>
    );
  }
  if (!situation || path.length === 0) return <p className="text-sm text-slate-500">{text.loading}</p>;

  const pick = (pl: string, ru: string) => (locale === 'ru' ? ru : pl);
  const nodeId = path[path.length - 1];
  const question = situation.questions.find((q) => q.id === nodeId);
  const outcome = situation.outcomes.find((o) => o.id === nodeId);

  return (
    <div aria-label={`knowledge-situation-card-${situation.code}`} className="space-y-3">
      <h2 className="text-lg font-bold text-slate-900 break-words">{title(situation)}</h2>
      {situation.status === 'DRAFT' && (
        <p className="text-xs text-amber-900 break-words bg-amber-50 border border-amber-200 rounded-xl p-2">{text.draft_notice}</p>
      )}

      {question && (
        <section aria-label="knowledge-question" className={`${CARD} space-y-3`}>
          <p className="text-xs text-slate-500">{fill(text.situation_step, { n: path.length })}</p>
          <p className="text-base font-semibold text-slate-900 break-words">{pick(question.text_pl, question.text_ru)}</p>
          <div className="space-y-2">
            {question.answers.map((answer, index) => (
              <button
                key={`${answer.next}-${index}`}
                type="button"
                aria-label={`knowledge-answer-${index}`}
                onClick={() => setPath((current) => [...current, answer.next])}
                className="w-full min-h-12 px-4 py-2 text-left text-sm font-semibold rounded-xl bg-blue-50 text-blue-900 hover:bg-blue-100 break-words"
              >
                {pick(answer.text_pl, answer.text_ru)}
              </button>
            ))}
          </div>
        </section>
      )}

      {outcome && (
        <section aria-label="knowledge-outcome" className={`${CARD} space-y-3`}>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-slate-700">{text.outcome_steps}</h3>
            <ol className="list-decimal pl-5 space-y-1">
              {(locale === 'ru' ? outcome.steps_ru : outcome.steps_pl).map((step, index) => (
                <li key={index} className="text-sm text-slate-800 break-words">{step}</li>
              ))}
            </ol>
          </div>
          {outcome.lawyer && <p className="text-sm font-semibold text-red-700 break-words">{text.outcome_lawyer}</p>}
          {outcome.entries.length > 0 && (
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-slate-700">{text.outcome_entries}</h3>
              <ul className="space-y-2">
                {outcome.entries.map((entryCode) => (
                  <li key={entryCode}>
                    <button
                      type="button"
                      aria-label={`knowledge-outcome-entry-${entryCode}`}
                      onClick={() => onOpenEntry(entryCode)}
                      className="w-full min-h-11 px-3 py-2 text-left text-sm font-semibold rounded-xl bg-slate-100 text-slate-800 hover:bg-slate-200 break-words"
                    >
                      {titles[entryCode] ?? entryCode}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {outcome.phrases.length > 0 && (
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-slate-700">{text.outcome_phrases}</h3>
              <ul className="space-y-2">
                {outcome.phrases.map((phrase) => (
                  <li key={phrase} aria-label={`knowledge-outcome-phrase-${phrase}`} className="px-3 py-2 text-sm rounded-xl bg-slate-100 text-slate-800 break-words">
                    {clientPhraseText(t, phrase)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {outcome.documents.length > 0 && (
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-slate-700">{text.outcome_documents}</h3>
              <ul className="flex flex-wrap gap-2">
                {outcome.documents.map((kind) => (
                  <li key={kind} className="px-2 py-1 text-xs rounded-lg bg-slate-100 text-slate-700 break-words">{documentKindLabel(t.documents, kind)}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {!question && !outcome && <p role="alert" className="text-sm text-red-600 break-words">{text.situation_broken}</p>}

      <div className="flex flex-col gap-2">
        {path.length > 1 && (
          <button
            type="button"
            aria-label="knowledge-situation-previous"
            onClick={() => setPath((current) => current.slice(0, -1))}
            className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-200"
          >
            <Ico>⬅️</Ico>{text.situation_back}
          </button>
        )}
        {path.length > 1 && (
          <button
            type="button"
            aria-label="knowledge-situation-restart"
            onClick={() => setPath([situation.start])}
            className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-200"
          >
            {text.situation_restart}
          </button>
        )}
      </div>
    </div>
  );
}
