import { useI18n } from '../hooks/useI18n';
import type { KnowledgeEntry, KnowledgeSource, KnowledgeStatus } from '../types/knowledge';

/** The pieces of an entry shown both on its card (Stage 17D) and inside a screen that points at it (Stage 17E). */

export function StatusBadge({ status }: { status: KnowledgeStatus }) {
  const { t } = useI18n();
  return (
    <span
      className={`inline-block px-2 py-0.5 text-xs font-semibold rounded-full ${
        status === 'DRAFT' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
      }`}
    >
      {status === 'DRAFT' ? t.knowledge.status_draft : t.knowledge.status_approved}
    </span>
  );
}

/** The key points in Polish (the language of the law) and, in the Russian interface, the explanation for the contractor. */
export function KeyPoints({ entry }: { entry: KnowledgeEntry }) {
  const { t, locale } = useI18n();
  const text = t.knowledge;
  return (
    <>
      <section aria-label="knowledge-summary" className="space-y-1">
        <h3 className="text-sm font-bold text-slate-700">{text.summary_title}</h3>
        {entry.summary_pl ? (
          <p className="text-sm text-slate-800 whitespace-pre-line break-words">{entry.summary_pl}</p>
        ) : (
          <p className="text-sm text-slate-400">{text.no_summary}</p>
        )}
      </section>
      {locale === 'ru' && entry.explanation_ru && (
        <section aria-label="knowledge-explanation" className="space-y-1">
          <h3 className="text-sm font-bold text-slate-700">{text.explanation_title}</h3>
          <p className="text-sm text-slate-800 whitespace-pre-line break-words">{entry.explanation_ru}</p>
        </section>
      )}
    </>
  );
}

/** The link to the source, opened outside the application; a source without a link says so. */
export function SourceLink({ source }: { source: KnowledgeSource }) {
  const { t } = useI18n();
  return source.url ? (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="knowledge-source-link"
      className="flex items-center justify-center w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white"
    >
      {t.knowledge.source_open}
    </a>
  ) : (
    <p className="text-xs text-slate-400">{t.knowledge.no_link}</p>
  );
}
