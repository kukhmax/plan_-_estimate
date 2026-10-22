import { useEffect, useState } from 'react';
import { fetchKnowledgeEntry, fetchKnowledgeEntryIndex } from '../api/knowledge';
import { useI18n } from '../hooks/useI18n';
import type { KnowledgeEntryDetail, KnowledgeEntryItem } from '../types/knowledge';
import { KeyPoints, SourceLink, StatusBadge } from './KnowledgeEntryParts';

export interface FieldHelpMatch {
  /** Entries whose `substrates` contain this value (`CONCRETE` ...). */
  substrate?: string;
  /** Entries whose `qualities` contain any of these values (`Q1` ...). */
  qualities?: readonly string[];
  /** Entries that carry this tag. */
  tag?: string;
}

interface FieldHelpProps {
  /** The name of the field the help explains; it names the button for screen readers (`Wyjaśnienie: Podłoże`). */
  field: string;
  /** A stable word for the label of tests (`substrate`, `quality`, `coefficient`). */
  name: string;
  match: FieldHelpMatch;
}

function matches(entry: KnowledgeEntryItem, match: FieldHelpMatch): boolean {
  if (match.substrate) return (entry.substrates ?? []).includes(match.substrate);
  if (match.qualities) return (entry.qualities ?? []).some((quality) => match.qualities?.includes(quality));
  if (match.tag) return entry.tags.includes(match.tag);
  return false;
}

/**
 * "?" beside a field (U-12): a 44 px button that opens a bottom sheet with the explanation from the knowledge base of the
 * server (the texts are never in the application). While there is no entry for the field, the server is unavailable or the list is
 * not loaded, nothing is shown: the field works the same without the help.
 */
export function FieldHelp({ field, name, match }: FieldHelpProps) {
  const { t, locale } = useI18n();
  const text = t.knowledge;
  const [entries, setEntries] = useState<KnowledgeEntryItem[]>([]);
  const [open, setOpen] = useState(false);
  const [details, setDetails] = useState<Record<string, KnowledgeEntryDetail>>({});
  const [failed, setFailed] = useState(false);
  const wanted = `${match.substrate ?? ''}|${(match.qualities ?? []).join(',')}|${match.tag ?? ''}`;

  useEffect(() => {
    let alive = true;
    fetchKnowledgeEntryIndex()
      .then((index) => {
        if (!alive) return;
        const found = index.items.filter((entry) => matches(entry, match));
        setEntries((before) => (before.length === 0 && found.length === 0 ? before : found));
      })
      .catch(() => alive && setEntries((before) => (before.length === 0 ? before : [])));
    return () => {
      alive = false;
    };
    // `match` is rebuilt on every render; `wanted` is its value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted]);

  const codes = entries.map((entry) => entry.code).join('|');
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setFailed(false);
    for (const code of codes.split('|')) {
      fetchKnowledgeEntry(code)
        .then((detail) => alive && setDetails((before) => ({ ...before, [code]: detail })))
        .catch(() => alive && setFailed(true));
    }
    return () => {
      alive = false;
    };
  }, [open, codes]);

  if (entries.length === 0) return null;

  const title = (entry: KnowledgeEntryItem) => (locale === 'ru' ? entry.title_ru : entry.title_pl);

  return (
    <>
      <button
        type="button"
        aria-label={`field-help-${name}`}
        title={text.help_open.replace('{field}', field)}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full border border-[var(--tg-control-border-color)] text-base font-semibold text-[var(--tg-theme-link-color)]"
      >
        <span aria-hidden="true">?</span>
      </button>
      {open && (
        <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50" role="dialog" aria-modal="true" aria-label={`field-help-sheet-${name}`}>
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-t-2xl bg-[var(--tg-theme-bg-color)] p-4 space-y-3 pb-[max(1rem,env(safe-area-inset-bottom))]">
            <h4 className="text-base font-semibold text-[var(--tg-theme-text-color)] break-words">{field}</h4>
            {entries.some((entry) => entry.status === 'DRAFT') && <p className="text-xs text-amber-900 break-words">{text.basis_draft}</p>}
            {failed && <p role="alert" className="text-sm text-red-600 break-words">{text.error_load}</p>}
            <ul className="space-y-3">
              {entries.map((entry) => {
                const detail = details[entry.code];
                return (
                  <li key={entry.code} aria-label={`field-help-entry-${entry.code}`} className="rounded-lg border border-slate-200 pe-surface p-3 space-y-2">
                    <span className="block text-sm font-semibold text-slate-900 break-words">{title(entry)}</span>
                    <span className="block text-xs text-slate-500 break-words">{[entry.source_designation, entry.locator].filter(Boolean).join(' · ')}</span>
                    {entry.status === 'DRAFT' && <StatusBadge status="DRAFT" />}
                    {detail ? (
                      <>
                        <KeyPoints entry={detail.entry} />
                        <SourceLink source={detail.source} />
                      </>
                    ) : (
                      !failed && <p className="text-sm text-slate-500">{text.basis_loading}</p>
                    )}
                  </li>
                );
              })}
            </ul>
            <button
              type="button"
              aria-label={`field-help-close-${name}`}
              onClick={() => setOpen(false)}
              className="w-full min-h-11 rounded-xl border border-[var(--tg-control-border-color)] px-4 text-sm font-semibold text-[var(--tg-theme-text-color)]"
            >
              {text.help_close}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
