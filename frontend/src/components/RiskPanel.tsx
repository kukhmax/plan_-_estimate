import { useEffect, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { resolveKey } from '../utils/i18nKeys';
import { evaluateRisks, fetchRiskDetail, fetchRisks } from '../api/risks';
import {
  RiskRead,
  RiskSeverityValue,
  RiskSourceFindingRead,
  RiskStatusValue,
} from '../types/risk';

export interface RiskPanelProps {
  projectId: string;
  roomId: string;
  inspectionId: string;
}

const STATUS_VALUES: RiskStatusValue[] = ['active', 'resolved', 'all'];

const SEVERITY_LABEL_KEY: Record<
  RiskSeverityValue,
  'severity_low' | 'severity_medium' | 'severity_high' | 'severity_critical'
> = {
  LOW: 'severity_low',
  MEDIUM: 'severity_medium',
  HIGH: 'severity_high',
  CRITICAL: 'severity_critical',
};

/** Distinguishable, restrained severity chip tones; CRITICAL is solid red. */
const SEVERITY_TONE: Record<RiskSeverityValue, string> = {
  LOW: 'border-neutral-200 bg-neutral-100 text-neutral-700',
  MEDIUM: 'border-amber-300 bg-amber-50 text-amber-800',
  HIGH: 'border-orange-300 bg-orange-100 text-orange-800',
  CRITICAL: 'border-red-700 bg-red-600 text-white font-bold',
};

/** Resolve a backend dotted key without ever leaking an unresolved machine key. */
function localizedText(t: ReturnType<typeof useI18n>['t'], dotted: string): string {
  const resolved = resolveKey(t, dotted);
  return resolved === dotted ? '' : resolved;
}

function localizedServiceError(
  t: ReturnType<typeof useI18n>['t'],
  err: unknown,
  fallback: string,
): string {
  const message = err instanceof Error ? err.message : '';
  if (message.includes('COMPLETED') || message.includes('completed')) {
    return t.risk.error_not_completed;
  }
  if (message.includes('not found') || message.includes('Not found')) {
    return t.risk.error_not_found;
  }
  return fallback;
}

function statusLabel(
  t: ReturnType<typeof useI18n>['t'],
  value: RiskStatusValue,
): string {
  if (value === 'resolved') return t.risk.status_resolved;
  if (value === 'all') return t.risk.status_all;
  return t.risk.status_active;
}

/** Human readable value snapshot when it adds information; '' otherwise. */
function sourceFindingValue(
  finding: RiskSourceFindingRead,
  t: ReturnType<typeof useI18n>['t'],
): string {
  const value = finding.value_snapshot;
  if (!value) return '';
  if ('number' in value && typeof value.number === 'string') {
    return `${value.number} ${t.inspections.unit_mm}`;
  }
  if ('text' in value && typeof value.text === 'string' && value.text !== '') {
    return value.text;
  }
  if ('bool' in value) {
    return value.bool === true ? t.inspections.yes : t.inspections.no;
  }
  return '';
}

export function RiskPanel({ projectId, roomId, inspectionId }: RiskPanelProps) {
  const { t } = useI18n();
  const [status, setStatus] = useState<RiskStatusValue>('active');
  const [items, setItems] = useState<RiskRead[]>([]);
  const [sourcesById, setSourcesById] = useState<
    Record<string, RiskSourceFindingRead[]>
  >({});
  const [expanded, setExpanded] = useState<string[]>([]);
  const [loadingPending, setLoadingPending] = useState<string[]>([]);
  const [sourceErrors, setSourceErrors] = useState<Record<string, string>>({});
  const [listLoading, setListLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadInitial(): Promise<void> {
      setListLoading(true);
      setError(null);
      try {
        const response = await fetchRisks(projectId, roomId, {
          inspectionId,
          status: 'active',
        });
        if (cancelled) return;
        setItems(response.items);
        setStatus('active');
      } catch (err) {
        if (!cancelled) setError(localizedServiceError(t, err, t.risk.error_load));
      } finally {
        if (!cancelled) setListLoading(false);
      }
    }
    void loadInitial();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, roomId, inspectionId]);

  async function switchStatus(next: RiskStatusValue): Promise<void> {
    if (next === status) return;
    setStatus(next);
    setExpanded([]);
    setListLoading(true);
    setError(null);
    try {
      const response = await fetchRisks(projectId, roomId, {
        inspectionId,
        status: next,
      });
      setItems(response.items);
    } catch (err) {
      setError(localizedServiceError(t, err, t.risk.error_load));
    } finally {
      setListLoading(false);
    }
  }

  async function handleEvaluate(): Promise<void> {
    setEvaluating(true);
    setError(null);
    try {
      const response = await evaluateRisks(projectId, roomId, inspectionId);
      const sources: Record<string, RiskSourceFindingRead[]> = {};
      for (const detail of response.items) {
        sources[detail.id] = detail.source_findings;
      }
      setSourcesById(sources);
      setItems(response.items);
      setStatus('active');
    } catch (err) {
      setError(localizedServiceError(t, err, t.risk.error_evaluate));
    } finally {
      setEvaluating(false);
    }
  }

  async function loadSources(riskId: string): Promise<void> {
    setLoadingPending((prev) => [...prev, riskId]);
    try {
      const detail = await fetchRiskDetail(projectId, roomId, riskId);
      setSourcesById((prev) => ({ ...prev, [riskId]: detail.source_findings }));
    } catch (err) {
      setSourceErrors((prev) => ({
        ...prev,
        [riskId]: localizedServiceError(t, err, t.risk.error_load),
      }));
    } finally {
      setLoadingPending((prev) => prev.filter((id) => id !== riskId));
    }
  }

  function toggleDetails(riskId: string): void {
    const isOpen = expanded.includes(riskId);
    setExpanded(
      isOpen ? expanded.filter((id) => id !== riskId) : [...expanded, riskId],
    );
    if (!isOpen && sourcesById[riskId] === undefined && !loadingPending.includes(riskId)) {
      void loadSources(riskId);
    }
  }

  const anyActive = items.some((risk) => risk.is_active);

  return (
    <div
      aria-label={t.risk.section_title}
      className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-neutral-50 p-3"
    >
      <h4 className="text-sm font-semibold text-neutral-900">
        {t.risk.section_title}
      </h4>
      <p className="text-xs text-neutral-600">{t.risk.evaluate_hint}</p>

      {error ? (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        aria-label={t.risk.evaluate}
        className="min-h-11 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
        disabled={evaluating}
        onClick={() => void handleEvaluate()}
      >
        {evaluating ? t.risk.evaluating : anyActive ? t.risk.reevaluate : t.risk.evaluate}
      </button>

      <div className="flex gap-2" role="group" aria-label={t.risk.section_title}>
        {STATUS_VALUES.map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={status === value}
            className={`min-h-11 flex-1 rounded-lg border px-1 text-sm font-medium ${
              status === value
                ? 'border-blue-600 bg-blue-50 text-blue-800'
                : 'border-neutral-300 bg-white text-neutral-700'
            }`}
            onClick={() => void switchStatus(value)}
          >
            {statusLabel(t, value)}
          </button>
        ))}
      </div>

      {listLoading ? (
        <p className="text-sm text-neutral-500">{t.risk.loading}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-neutral-500">{t.risk.no_risks}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((risk) => (
            <RiskCard
              key={risk.id}
              risk={risk}
              sources={sourcesById[risk.id]}
              expanded={expanded.includes(risk.id)}
              sourcesLoading={loadingPending.includes(risk.id)}
              sourcesError={sourceErrors[risk.id]}
              onToggle={toggleDetails}
              t={t}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function RiskCard({
  risk,
  sources,
  expanded,
  sourcesLoading,
  sourcesError,
  onToggle,
  t,
}: {
  risk: RiskRead;
  sources: RiskSourceFindingRead[] | undefined;
  expanded: boolean;
  sourcesLoading: boolean;
  sourcesError: string | undefined;
  onToggle: (riskId: string) => void;
  t: ReturnType<typeof useI18n>['t'];
}) {
  const active = risk.is_active;
  const title = localizedText(t, risk.title_key) || risk.risk_code;
  const severityLabel = t.risk[SEVERITY_LABEL_KEY[risk.severity]];
  const severityTone = active ? SEVERITY_TONE[risk.severity] : 'border-neutral-300 bg-neutral-100 text-neutral-600';
  const resolvedDate = risk.resolved_at ? risk.resolved_at.slice(0, 10) : null;

  return (
    <li
      className={`flex flex-col gap-2 rounded-lg border bg-white p-3 text-sm ${
        active ? 'border-neutral-200' : 'border-neutral-200 bg-neutral-50 opacity-80'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${severityTone}`}
        >
          {severityLabel}
        </span>
        {!active ? (
          <span className="inline-flex items-center rounded-full border border-neutral-300 bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-600">
            {t.risk.status_resolved}
          </span>
        ) : null}
        {resolvedDate ? (
          <span className="text-xs text-neutral-500">
            {t.risk.resolved_at.replace('{date}', resolvedDate)}
          </span>
        ) : null}
      </div>

      <p className={`font-semibold ${active ? 'text-neutral-900' : 'text-neutral-600'}`}>
        {title}
      </p>

      {risk.blocks_finishing ? (
        <p
          className={`rounded-lg border px-3 py-2 text-sm font-medium ${
            active
              ? 'border-red-400 bg-red-50 text-red-800'
              : 'border-neutral-300 bg-neutral-100 text-neutral-600'
          }`}
        >
          <span aria-hidden="true">⚠ </span>
          {t.risk.blocks_finishing}
        </p>
      ) : null}

      {risk.warranty_exclusion_candidate ? (
        <span
          className={`self-start rounded-full border px-2 py-0.5 text-xs ${
            active
              ? 'border-neutral-300 bg-white text-neutral-700'
              : 'border-neutral-200 bg-neutral-50 text-neutral-500'
          }`}
        >
          {t.risk.warranty_candidate}
        </span>
      ) : null}

      <button
        type="button"
        aria-expanded={expanded}
        aria-label={`${title} — ${t.risk.details}`}
        className="min-h-10 self-start rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700"
        onClick={() => onToggle(risk.id)}
      >
        {expanded ? t.risk.hide_details : t.risk.details}
      </button>

      {expanded ? (
        <div className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-neutral-50 p-3">
          <DetailRow label={t.risk.explanation} text={localizedText(t, risk.explanation_key)} />
          <DetailRow label={t.risk.consequence} text={localizedText(t, risk.consequence_key)} />
          <DetailRow label={t.risk.mitigation} text={localizedText(t, risk.mitigation_key)} />
          {!sourcesLoading && sourcesError ? (
            <p className="rounded-md bg-red-50 px-2 py-1 text-xs text-red-700" role="alert">
              {sourcesError}
            </p>
          ) : null}
          {sourcesLoading ? (
            <p className="text-xs text-neutral-500">{t.risk.loading}</p>
          ) : sources && sources.length > 0 ? (
            <div>
              <h5 className="text-xs font-semibold text-neutral-700">{t.risk.why}</h5>
              <ul className="mt-1 flex flex-col gap-1">
                {sources.map((finding, index) => {
                  const rawKey = finding.finding_key_snapshot;
                  const label = localizedText(t, `risk.finding.${rawKey.toLowerCase()}`) || rawKey;
                  const value = sourceFindingValue(finding, t);
                  return (
                    <li key={`${finding.finding_id ?? 'finding'}-${index}`} className="text-xs text-neutral-700">
                      {label}
                      {value ? ` — ${value}` : ''}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function DetailRow({ label, text }: { label: string; text: string }) {
  if (text === '') {
    return null;
  }
  return (
    <p className="text-xs text-neutral-700">
      <span className="font-semibold text-neutral-900">{label}: </span>
      {text}
    </p>
  );
}