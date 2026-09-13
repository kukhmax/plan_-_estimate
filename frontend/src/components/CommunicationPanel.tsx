import { useEffect, useRef, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { resolveKey } from '../utils/i18nKeys';
import { formatMetric } from '../utils/format';
import { copyTextToClipboard } from '../utils/clipboard';
import {
  evaluateCommunications,
  fetchCommunicationDetail,
  fetchCommunications,
} from '../api/communications';
import {
  CommunicationApplicationRead,
  CommunicationCategoryValue,
  CommunicationSource,
  CommunicationStatusValue,
} from '../types/communication';
import { RiskSeverityValue, RiskSourceFindingRead } from '../types/risk';

export interface CommunicationPanelProps {
  projectId: string;
  roomId: string;
  inspectionId: string;
}

const STATUS_VALUES: CommunicationStatusValue[] = ['active', 'resolved', 'all'];

const CATEGORY_LABEL_KEY: Record<
  CommunicationCategoryValue,
  | 'explain_condition'
  | 'explain_consequence'
  | 'recommend_preparation'
  | 'require_client_decision'
  | 'scope_clarification'
  | 'quality_expectation'
  | 'document_agreement'
  | 'general'
> = {
  EXPLAIN_CONDITION: 'explain_condition',
  EXPLAIN_CONSEQUENCE: 'explain_consequence',
  RECOMMEND_PREPARATION: 'recommend_preparation',
  REQUIRE_CLIENT_DECISION: 'require_client_decision',
  SCOPE_CLARIFICATION: 'scope_clarification',
  QUALITY_EXPECTATION: 'quality_expectation',
  DOCUMENT_AGREEMENT: 'document_agreement',
  GENERAL: 'general',
};

/**
 * Categories that warrant a slightly stronger visual priority. This is a
 * presentation-only hint — it carries no implied legal status.
 */
const CATEGORY_EMPHASIS: ReadonlySet<CommunicationCategoryValue> = new Set([
  'REQUIRE_CLIENT_DECISION',
  'DOCUMENT_AGREEMENT',
]);

const SEVERITY_LABEL_KEY: Record<
  RiskSeverityValue,
  'severity_low' | 'severity_medium' | 'severity_high' | 'severity_critical'
> = {
  LOW: 'severity_low',
  MEDIUM: 'severity_medium',
  HIGH: 'severity_high',
  CRITICAL: 'severity_critical',
};

const SEVERITY_TONE: Record<RiskSeverityValue, string> = {
  LOW: 'border-neutral-200 bg-neutral-100 text-neutral-700',
  MEDIUM: 'border-amber-300 bg-amber-50 text-amber-800',
  HIGH: 'border-orange-300 bg-orange-100 text-orange-800',
  CRITICAL: 'border-red-700 bg-red-600 text-white font-bold',
};

/** Resolve a backend dotted key; '' when unresolved so a raw key never renders. */
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
    return t.communication.error_not_completed;
  }
  return fallback;
}

function statusLabel(
  t: ReturnType<typeof useI18n>['t'],
  value: CommunicationStatusValue,
): string {
  if (value === 'resolved') return t.communication.status_resolved;
  if (value === 'all') return t.communication.status_all;
  return t.communication.status_active;
}

function categoryLabel(
  t: ReturnType<typeof useI18n>['t'],
  category: CommunicationCategoryValue,
): string {
  return t.communication.category[CATEGORY_LABEL_KEY[category]];
}

/** Phrase text with a localized fallback; a raw backend key is never shown. */
function phraseText(
  t: ReturnType<typeof useI18n>['t'],
  app: CommunicationApplicationRead,
): string {
  const text = localizedText(t, app.phrase_key);
  return text === '' ? t.communication.fallback_phrase : text;
}

function substrateLabel(
  t: ReturnType<typeof useI18n>['t'],
  substrate: string,
): string {
  return localizedText(t, `inspections.substrate_${substrate.toLowerCase()}`);
}

/** Human readable snapshot value following the two-decimal policy; '' otherwise. */
function snapshotValue(
  value: Record<string, unknown> | null,
  t: ReturnType<typeof useI18n>['t'],
): string {
  if (!value) return '';
  if ('number' in value && typeof value.number === 'string') {
    return `${formatMetric(value.number)} ${t.inspections.unit_mm}`;
  }
  if ('text' in value && typeof value.text === 'string' && value.text !== '') {
    return value.text;
  }
  if ('bool' in value) {
    return value.bool === true ? t.inspections.yes : t.inspections.no;
  }
  return '';
}

export function CommunicationPanel({
  projectId,
  roomId,
  inspectionId,
}: CommunicationPanelProps) {
  const { t } = useI18n();
  const [status, setStatus] = useState<CommunicationStatusValue>('active');
  const [items, setItems] = useState<CommunicationApplicationRead[]>([]);
  const [detailById, setDetailById] = useState<Record<string, CommunicationSource>>(
    {},
  );
  const [expanded, setExpanded] = useState<string[]>([]);
  const [loadingPending, setLoadingPending] = useState<string[]>([]);
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [listLoading, setListLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<
    { id: string; ok: boolean } | null
  >(null);
  const copyTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadInitial(): Promise<void> {
      setListLoading(true);
      setError(null);
      try {
        const response = await fetchCommunications(projectId, roomId, inspectionId, {
          status: 'active',
        });
        if (cancelled) return;
        setItems(response.items);
        setStatus('active');
      } catch (err) {
        if (!cancelled) {
          setError(localizedServiceError(t, err, t.communication.error_load));
        }
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

  async function switchStatus(next: CommunicationStatusValue): Promise<void> {
    if (next === status) return;
    setStatus(next);
    setExpanded([]);
    setListLoading(true);
    setError(null);
    try {
      const response = await fetchCommunications(projectId, roomId, inspectionId, {
        status: next,
      });
      setItems(response.items);
    } catch (err) {
      setError(localizedServiceError(t, err, t.communication.error_load));
    } finally {
      setListLoading(false);
    }
  }

  async function handleEvaluate(): Promise<void> {
    setEvaluating(true);
    setError(null);
    try {
      const response = await evaluateCommunications(projectId, roomId, inspectionId);
      setItems(response.items);
      setStatus('active');
    } catch (err) {
      setError(localizedServiceError(t, err, t.communication.error_evaluate));
    } finally {
      setEvaluating(false);
    }
  }

  async function loadSource(communicationId: string): Promise<void> {
    setLoadingPending((prev) => [...prev, communicationId]);
    try {
      const detail = await fetchCommunicationDetail(
        projectId,
        roomId,
        inspectionId,
        communicationId,
      );
      setDetailById((prev) => ({ ...prev, [communicationId]: detail.source }));
    } catch (err) {
      setDetailErrors((prev) => ({
        ...prev,
        [communicationId]: localizedServiceError(t, err, t.communication.error_detail),
      }));
    } finally {
      setLoadingPending((prev) => prev.filter((id) => id !== communicationId));
    }
  }

  function toggleDetails(communicationId: string): void {
    const isOpen = expanded.includes(communicationId);
    setExpanded(
      isOpen
        ? expanded.filter((id) => id !== communicationId)
        : [...expanded, communicationId],
    );
    if (
      !isOpen &&
      detailById[communicationId] === undefined &&
      !loadingPending.includes(communicationId)
    ) {
      void loadSource(communicationId);
    }
  }

  function handleCopy(app: CommunicationApplicationRead): void {
    if (copyTimerRef.current !== null) {
      window.clearTimeout(copyTimerRef.current);
    }
    void copyTextToClipboard(phraseText(t, app)).then((ok) => {
      setCopyState({ id: app.id, ok });
      copyTimerRef.current = window.setTimeout(() => {
        setCopyState(null);
      }, 2500);
    });
  }

  const hasAny = items.length > 0;

  return (
    <div
      aria-label={t.communication.section_title}
      className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-neutral-50 p-3"
    >
      <h4 className="text-sm font-semibold text-neutral-900">
        {t.communication.section_title}
      </h4>
      <p className="text-xs text-neutral-600">{t.communication.evaluate_hint}</p>

      {error ? (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        aria-label={t.communication.evaluate}
        className="min-h-11 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
        disabled={evaluating}
        onClick={() => void handleEvaluate()}
      >
        {evaluating
          ? t.communication.evaluating
          : hasAny
            ? t.communication.reevaluate
            : t.communication.evaluate}
      </button>

      <div className="flex gap-2" role="group" aria-label={t.communication.section_title}>
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
        <p className="text-sm text-neutral-500">{t.communication.loading}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-neutral-500">
          {status === 'active'
            ? t.communication.empty_active
            : status === 'resolved'
              ? t.communication.empty_resolved
              : t.communication.empty_all}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((app) => (
            <CommunicationCard
              key={app.id}
              app={app}
              source={detailById[app.id]}
              expanded={expanded.includes(app.id)}
              sourceLoading={loadingPending.includes(app.id)}
              sourceError={detailErrors[app.id]}
              copyState={copyState}
              onToggle={toggleDetails}
              onCopy={handleCopy}
              t={t}
            />
          ))}
        </ul>
      )}

      <span aria-live="polite" className="sr-only">
        {copyState
          ? (copyState.ok
              ? t.communication.copied
              : t.communication.copy_failed)
          : ''}
      </span>
    </div>
  );
}

function CommunicationCard({
  app,
  source,
  expanded,
  sourceLoading,
  sourceError,
  copyState,
  onToggle,
  onCopy,
  t,
}: {
  app: CommunicationApplicationRead;
  source: CommunicationSource | undefined;
  expanded: boolean;
  sourceLoading: boolean;
  sourceError: string | undefined;
  copyState: { id: string; ok: boolean } | null;
  onToggle: (communicationId: string) => void;
  onCopy: (app: CommunicationApplicationRead) => void;
  t: ReturnType<typeof useI18n>['t'];
}) {
  const active = app.is_active;
  const text = phraseText(t, app);
  const whyText = app.why_key ? localizedText(t, app.why_key) : '';
  const category = categoryLabel(t, app.category);
  const chipTone = CATEGORY_EMPHASIS.has(app.category)
    ? 'border-blue-600 bg-blue-50 text-blue-800 font-semibold'
    : 'border-neutral-300 bg-neutral-100 text-neutral-700 font-medium';
  const resolvedDate = app.resolved_at ? app.resolved_at.slice(0, 10) : null;
  const copied = copyState !== null && copyState.id === app.id && copyState.ok;
  const copyFailed =
    copyState !== null && copyState.id === app.id && !copyState.ok;

  return (
    <li
      className={`flex flex-col gap-2 rounded-lg border bg-white p-3 text-sm ${
        active ? 'border-neutral-200' : 'border-neutral-200 bg-neutral-50 opacity-80'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${chipTone}`}
        >
          {category}
        </span>
        {!active ? (
          <span className="inline-flex items-center rounded-full border border-neutral-300 bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-600">
            {t.communication.status_resolved}
          </span>
        ) : null}
        {resolvedDate ? (
          <span className="text-xs text-neutral-500">
            {t.communication.resolved_at.replace('{date}', resolvedDate)}
          </span>
        ) : null}
      </div>

      <p className={`font-medium ${active ? 'text-neutral-900' : 'text-neutral-600'}`}>
        {text}
      </p>

      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={`${text} — ${expanded ? t.communication.hide_why : t.communication.why}`}
          className="min-h-10 self-start rounded-lg border border-neutral-300 px-3 text-sm font-medium text-neutral-700"
          onClick={() => onToggle(app.id)}
        >
          {expanded ? t.communication.hide_why : t.communication.why}
        </button>
        <button
          type="button"
          aria-label={`${text} — ${t.communication.copy}`}
          className={`min-h-11 self-start rounded-lg border px-3 text-sm font-medium ${
            copied
              ? 'border-green-700 bg-green-50 text-green-800'
              : 'border-neutral-300 bg-white text-neutral-700'
          }`}
          onClick={() => onCopy(app)}
        >
          {copied ? t.communication.copied : t.communication.copy}
        </button>
        {copyFailed ? (
          <p className="rounded-md bg-red-50 px-2 py-1 text-xs text-red-700" role="alert">
            {t.communication.copy_failed}
          </p>
        ) : null}
      </div>

      {expanded ? (
        <div className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-neutral-50 p-3">
          {whyText !== '' ? (
            <p className="text-xs text-neutral-700">{whyText}</p>
          ) : null}
          {sourceLoading ? (
            <p className="text-xs text-neutral-500">{t.communication.loading}</p>
          ) : null}
          {!sourceLoading && sourceError ? (
            <p className="rounded-md bg-red-50 px-2 py-1 text-xs text-red-700" role="alert">
              {sourceError}
            </p>
          ) : null}
          {!sourceLoading && source ? (
            <SourceContext source={source} t={t} />
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function SourceContext({
  source,
  t,
}: {
  source: CommunicationSource;
  t: ReturnType<typeof useI18n>['t'];
}) {
  if (source.kind === 'RISK') {
    const riskTitle =
      source.risk_code
        ? localizedText(t, `risk.${source.risk_code.toLowerCase()}.title`)
        : '';
    return (
      <div className="flex flex-col gap-2">
        <h5 className="text-xs font-semibold text-neutral-700">
          {t.communication.source_risk_title}
        </h5>
        {riskTitle !== '' ? (
          <p className="text-xs font-medium text-neutral-900">{riskTitle}</p>
        ) : null}
        {source.severity ? (
          <span
            className={`self-start inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${SEVERITY_TONE[source.severity]}`}
          >
            {t.risk[SEVERITY_LABEL_KEY[source.severity]]}
          </span>
        ) : null}
        {source.source_findings.length > 0 ? (
          <div>
            <h5 className="text-xs font-semibold text-neutral-700">
              {t.communication.source_findings}
            </h5>
            <ul className="mt-1 flex flex-col gap-1">
              {source.source_findings.map((finding, index) => (
                <SourceFindingRow key={index} finding={finding} t={t} />
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  }

  if (source.kind === 'FINDING') {
    const rows = source.findings
      .map((finding) => {
        const label = finding.label_key ? localizedText(t, finding.label_key) : '';
        const value = snapshotValue(finding.value_snapshot, t);
        return { finding, label, value };
      })
      .filter((row) => row.label !== '');
    return (
      <div className="flex flex-col gap-1">
        <h5 className="text-xs font-semibold text-neutral-700">
          {t.communication.source_finding_title}
        </h5>
        {rows.length === 0 ? (
          <p className="text-xs text-neutral-500">{t.communication.fallback_phrase}</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {rows.map(({ finding, label, value }) => (
              <li key={finding.finding_id ?? label} className="text-xs text-neutral-700">
                {label}
                {value !== '' ? ` — ${value}` : ''}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  const substrate = source.substrate ? substrateLabel(t, source.substrate) : '';
  return (
    <div className="flex flex-col gap-2">
      <h5 className="text-xs font-semibold text-neutral-700">
        {t.communication.source_quality_title}
      </h5>
      {substrate !== '' ? (
        <DetailRow label={t.inspections.substrate} text={substrate} />
      ) : null}
      {source.quality_level ? (
        <DetailRow label={t.inspections.quality_target} text={source.quality_level} />
      ) : null}
    </div>
  );
}

function SourceFindingRow({
  finding,
  t,
}: {
  finding: RiskSourceFindingRead;
  t: ReturnType<typeof useI18n>['t'];
}) {
  const label = localizedText(
    t,
    `risk.finding.${finding.finding_key_snapshot.toLowerCase()}`,
  );
  const value = snapshotValue(finding.value_snapshot, t);
  if (label === '' && value === '') {
    return null;
  }
  return (
    <li key={finding.finding_id ?? label} className="text-xs text-neutral-700">
      {label}
      {value !== '' ? ` — ${value}` : ''}
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