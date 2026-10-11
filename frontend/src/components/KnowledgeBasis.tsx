import { useEffect, useState } from 'react';
import { fetchKnowledgeEntry, fetchKnowledgeLinkIndex } from '../api/knowledge';
import { useI18n } from '../hooks/useI18n';
import type { KnowledgeEntryDetail, KnowledgeEntryItem, KnowledgeLinkKind } from '../types/knowledge';
import { KeyPoints, SourceLink, StatusBadge } from './KnowledgeEntryParts';

export interface KnowledgeBasisTarget {
  kind: KnowledgeLinkKind;
  target: string;
}

interface KnowledgeBasisProps {
  /** The places of the application whose basis is shown (a screen may stand for several, e.g. the notice and the protocol). */
  targets: KnowledgeBasisTarget[];
  /** The label for tests and for screen readers of this block. */
  name?: string;
  /** What the block answers, with `{count}` (default "Podstawa ({count})"). */
  heading?: string;
}

/**
 * "Podstawa / Основание" (Stage 17E): where the application points at the knowledge base -- a risk, a phrase for the client,
 * a document -- a folded list of the entries behind it. Nothing is shown while there is nothing to show (no link, not loaded,
 * the server unavailable): the screen it stands in must work the same without it. An entry opens inside the list, with its
 * key points and the link to its source; a draft is marked as a draft.
 */
export function KnowledgeBasis({ targets, name = 'knowledge-basis', heading }: KnowledgeBasisProps) {
  const { t, locale } = useI18n();
  const text = t.knowledge;
  const [entries, setEntries] = useState<KnowledgeEntryItem[]>([]);
  const [open, setOpen] = useState(false);
  const [openEntry, setOpenEntry] = useState<string | null>(null);
  const [detail, setDetail] = useState<KnowledgeEntryDetail | null>(null);
  const [detailFailed, setDetailFailed] = useState(false);
  const wanted = targets.map((item) => `${item.kind}:${item.target}`).join('|');

  useEffect(() => {
    let alive = true;
    const keys = new Set(wanted.split('|'));
    fetchKnowledgeLinkIndex()
      .then((index) => {
        if (!alive) return;
        const seen = new Set<string>();
        const found: KnowledgeEntryItem[] = [];
        for (const row of index.items) {
          if (!keys.has(`${row.target_kind}:${row.target}`)) continue;
          for (const entry of row.entries) {
            if (!seen.has(entry.code)) {
              seen.add(entry.code);
              found.push(entry);
            }
          }
        }
        // nothing found and nothing shown before: no state change, so the screen does not render again
        setEntries((before) => (before.length === 0 && found.length === 0 ? before : found));
      })
      .catch(() => alive && setEntries((before) => (before.length === 0 ? before : [])));
    return () => {
      alive = false;
    };
  }, [wanted]);

  useEffect(() => {
    if (!openEntry) return;
    let alive = true;
    setDetail(null);
    setDetailFailed(false);
    fetchKnowledgeEntry(openEntry)
      .then((data) => alive && setDetail(data))
      .catch(() => alive && setDetailFailed(true));
    return () => {
      alive = false;
    };
  }, [openEntry]);

  if (entries.length === 0) return null;

  const title = (entry: KnowledgeEntryItem) => (locale === 'ru' ? entry.title_ru : entry.title_pl);

  return (
    <div aria-label={name} className="rounded-lg border border-slate-200 bg-slate-50">
      <button
        type="button"
        aria-label={`${name}-toggle`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="w-full min-h-11 px-3 flex items-center justify-between gap-2 text-left text-sm font-semibold text-slate-700"
      >
        <span className="break-words">{(heading ?? text.basis_title).replace('{count}', String(entries.length))}</span>
        <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2">
          {entries.some((entry) => entry.status === 'DRAFT') && <p className="text-xs text-amber-900 break-words">{text.basis_draft}</p>}
          <ul className="space-y-2">
            {entries.map((entry) => (
              <li key={entry.code} className="rounded-lg border border-slate-200 bg-white">
                <button
                  type="button"
                  aria-label={`${name}-entry-${entry.code}`}
                  aria-expanded={openEntry === entry.code}
                  onClick={() => setOpenEntry((current) => (current === entry.code ? null : entry.code))}
                  className="w-full min-h-11 px-3 py-2 text-left space-y-1"
                >
                  <span className="block text-sm font-semibold text-slate-900 break-words">{title(entry)}</span>
                  <span className="block text-xs text-slate-500 break-words">
                    {[entry.source_designation, entry.locator].filter(Boolean).join(' · ')}
                  </span>
                  {entry.status === 'DRAFT' && <StatusBadge status="DRAFT" />}
                </button>
                {openEntry === entry.code && (
                  <div className="px-3 pb-3 space-y-3 border-t border-slate-100 pt-2">
                    {detailFailed && <p role="alert" className="text-sm text-red-600 break-words">{text.error_load}</p>}
                    {!detailFailed && !detail && <p className="text-sm text-slate-500">{text.basis_loading}</p>}
                    {!detailFailed && detail && detail.entry.code === entry.code && (
                      <>
                        <KeyPoints entry={detail.entry} />
                        <SourceLink source={detail.source} />
                      </>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
