import { useEffect, useRef, useState } from 'react';
import {
  applyExecutionToRoomWalls,
  fetchSurfaceWorkPlan,
  isSurfaceWorkPlanMissing,
  isWorkExecutionConflict,
  isWorkExecutionSourceChanged,
  previewExecutionToRoomWalls,
  transitionWorkExecution,
} from '../api/workPlans';
import { useI18n } from '../hooks/useI18n';
import {
  BulkExecutionResultRead,
  SurfacePlannedWorkRead,
  SurfaceWorkPlanRead,
  WorkExecutionStatus,
} from '../types/workPlan';
import { localizeApiError } from '../utils/apiErrors';
import { formatRecordedDateTime, pluralCount, priceItemLabel } from '../utils/executionFormat';
import { formatWaitHours } from '../utils/waitFormat';
import { displayCounts, ExecutionBulkSheet, nothingReason } from './ExecutionBulkSheet';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

interface SurfaceExecutionViewProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  surfaceName: string;
  onClose: () => void;
  /** Opens the plan editor ("Rodzaje prac i jakość") from the empty state. */
  onOpenPlan?: () => void;
  /** Stage 13H.5B: WALL surfaces only -- enables carrying this wall's
   * progress to the room's other active walls. */
  isWall?: boolean;
  otherActiveWallCount?: number;
  /** Room surface display names by id, for the per-wall summary. */
  surfaceNames?: Record<string, string>;
}

/** Outcome line(s) shown under the bulk button after an apply or failure. */
type BulkNotice =
  | { kind: 'done'; result: BulkExecutionResultRead }
  | { kind: 'source_changed' | 'error' | 'preview_error' };

type LoadState = 'loading' | 'ready' | 'error';

interface CardMessage {
  kind: 'conflict' | 'error';
  text: string;
}

/**
 * Stage 13H.5 — "Realizacja": the execution status of every CURRENT planned
 * work of a saved surface plan. Each action is an immediate PATCH (never part
 * of the plan editor's draft) carrying the status the owner saw as
 * expected_status; the card is updated only from the server response. A 409
 * execution conflict reloads the plan and is never retried automatically.
 */
export function SurfaceExecutionView({
  projectId,
  roomId,
  surfaceId,
  surfaceName,
  onClose,
  onOpenPlan,
  isWall = false,
  otherActiveWallCount = 0,
  surfaceNames,
}: SurfaceExecutionViewProps) {
  const { t, locale } = useI18n();
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [plan, setPlan] = useState<SurfaceWorkPlanRead | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [optionsKey, setOptionsKey] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, CardMessage>>({});
  const inFlight = useRef(false);
  const loadGeneration = useRef(0);
  // Stage 13H.5B bulk flow: preview (authoritative) -> sheet -> apply.
  const [bulkPreview, setBulkPreview] = useState<BulkExecutionResultRead | null>(null);
  const [bulkBusy, setBulkBusy] = useState<'previewing' | 'applying' | null>(null);
  const [bulkSheetError, setBulkSheetError] = useState<string | null>(null);
  const [bulkNotice, setBulkNotice] = useState<BulkNotice | null>(null);
  const bulkInFlight = useRef(false);

  const load = (silent: boolean) => {
    const generation = ++loadGeneration.current;
    if (!silent) setLoadState('loading');
    return fetchSurfaceWorkPlan(projectId, roomId, surfaceId)
      .then((fresh) => {
        if (loadGeneration.current !== generation) return;
        setPlan(fresh);
        setLoadState('ready');
      })
      .catch((error: unknown) => {
        if (loadGeneration.current !== generation) return;
        if (isSurfaceWorkPlanMissing(error)) {
          setPlan(null);
          setLoadState('ready');
          return;
        }
        if (!silent) setLoadState('error');
      });
  };

  useEffect(() => {
    setMessages({});
    setOptionsKey(null);
    void load(false);
    return () => {
      loadGeneration.current += 1;
    };
  }, [loadAttempt, projectId, roomId, surfaceId]);

  const transition = async (work: SurfacePlannedWorkRead, status: WorkExecutionStatus) => {
    const expected = work.execution?.status;
    if (!expected || inFlight.current) return;
    const key = work.occurrence_key;
    inFlight.current = true;
    setPendingKey(key);
    setMessages((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    try {
      const result = await transitionWorkExecution(projectId, roomId, surfaceId, key, {
        status,
        expected_status: expected,
      });
      // Server truth only: status and timestamps come from the response.
      setPlan((prev) => prev && {
        ...prev,
        planned_works: prev.planned_works.map((w) =>
          w.occurrence_key === key
            ? {
              ...w,
              execution: {
                status: result.status,
                started_at: result.started_at,
                completed_at: result.completed_at,
                ready_after: result.ready_after,
              },
            }
            : w,
        ),
      });
      setOptionsKey(null);
    } catch (error) {
      if (isWorkExecutionConflict(error)) {
        setMessages((prev) => ({ ...prev, [key]: { kind: 'conflict', text: t.execution.conflict } }));
        setOptionsKey(null);
        await load(true); // show the current server state; never retry
      } else {
        const detail = localizeApiError(error, t);
        const text = /^Request failed(?: \(\d+\))?$/.test(detail) || !detail ? t.execution.error : detail;
        setMessages((prev) => ({ ...prev, [key]: { kind: 'error', text } }));
      }
    } finally {
      inFlight.current = false;
      setPendingKey(null);
    }
  };

  const openBulkPreview = async () => {
    if (bulkInFlight.current || pendingKey !== null) return;
    bulkInFlight.current = true;
    setBulkBusy('previewing');
    setBulkNotice(null);
    setBulkSheetError(null);
    try {
      setBulkPreview(await previewExecutionToRoomWalls(projectId, roomId, surfaceId));
    } catch {
      setBulkNotice({ kind: 'preview_error' });
    } finally {
      bulkInFlight.current = false;
      setBulkBusy(null);
    }
  };

  const confirmBulk = async () => {
    if (!bulkPreview || bulkInFlight.current) return;
    bulkInFlight.current = true;
    setBulkBusy('applying');
    setBulkSheetError(null);
    try {
      // Exactly the preview's snapshot: never rebuilt, sorted or filtered.
      const result = await applyExecutionToRoomWalls(projectId, roomId, surfaceId, bulkPreview.expected_source);
      setBulkPreview(null);
      setBulkNotice({ kind: 'done', result });
      await load(true); // the source is unchanged; re-read it from the server anyway
    } catch (error) {
      if (isWorkExecutionSourceChanged(error)) {
        // Stale confirmation: close it, show the current source, require a new preview.
        setBulkPreview(null);
        setBulkNotice({ kind: 'source_changed' });
        await load(true);
      } else {
        setBulkSheetError(t.execution.bulk.error);
      }
    } finally {
      bulkInFlight.current = false;
      setBulkBusy(null);
    }
  };

  const bulkNoticeLines = (notice: BulkNotice): { text: string; tone: 'ok' | 'info' | 'error' }[] => {
    const b = t.execution.bulk;
    if (notice.kind === 'source_changed') return [{ text: b.source_changed, tone: 'error' }];
    if (notice.kind === 'error') return [{ text: b.error, tone: 'error' }];
    if (notice.kind !== 'done') return [{ text: b.preview_error, tone: 'error' }];
    const result = notice.result;
    const lines: { text: string; tone: 'ok' | 'info' | 'error' }[] = [];
    if (result.changed > 0) {
      const walls = result.walls.filter((w) => w.changed > 0).length;
      lines.push({
        text: `${pluralCount(b.done_works, locale, result.changed)} ${pluralCount(b.done_walls, locale, walls)}`,
        tone: 'ok',
      });
    } else {
      lines.push({ text: `${b.done_none} ${b[`nothing_${nothingReason(result)}`]}`, tone: 'info' });
    }
    const counts = displayCounts(result);
    const skipped = [
      counts.unmatched > 0 ? b.skipped_unmatched.replace('{count}', String(counts.unmatched)) : null,
      counts.ambiguous > 0 ? b.skipped_ambiguous.replace('{count}', String(counts.ambiguous)) : null,
      counts.noPlanWalls > 0 ? b.skipped_no_plan.replace('{count}', String(counts.noPlanWalls)) : null,
    ].filter((line): line is string => line !== null);
    if (skipped.length > 0) lines.push({ text: skipped.join(' '), tone: 'info' });
    return lines;
  };

  const works = plan?.planned_works ?? [];
  const showBulk = isWall && otherActiveWallCount > 0;
  const btnPrimary =
    'w-full min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold text-sm disabled:opacity-60 break-words';
  const btnSecondary =
    'w-full min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] text-[var(--tg-theme-text-color)] font-semibold text-sm disabled:opacity-60 break-words';

  const emptyText = (template: string) => template.replace('{section}', t.surfaces.work_types_quality);

  return (
    <section
      aria-label={`execution-view-${surfaceId}`}
      className="w-full min-w-0 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] p-3 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h5 className="text-sm font-bold text-[var(--tg-theme-text-color)] break-words">{t.execution.title}</h5>
          <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{surfaceName}</p>
        </div>
        <button
          type="button"
          aria-label={`close-execution-${surfaceId}`}
          onClick={onClose}
          className="min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)] font-semibold"
        >
          {t.common.close}
        </button>
      </div>

      {loadState === 'loading' && (
        <p role="status" className="py-4 text-sm text-center text-[var(--tg-theme-hint-color)]">{t.execution.loading}</p>
      )}

      {loadState === 'error' && (
        <div role="alert" className="space-y-2">
          <p className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)] break-words">{t.execution.error_load}</p>
          <button
            type="button"
            aria-label={`retry-execution-${surfaceId}`}
            onClick={() => setLoadAttempt((n) => n + 1)}
            className={btnPrimary}
          >
            {t.execution.retry}
          </button>
        </div>
      )}

      {loadState === 'ready' && works.length === 0 && (
        <div aria-label={`execution-empty-${surfaceId}`} className="space-y-2">
          <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">
            {emptyText(plan === null ? t.execution.no_plan : t.execution.no_works)}
          </p>
          {onOpenPlan && (
            <button type="button" aria-label={`execution-open-plan-${surfaceId}`} onClick={onOpenPlan} className={btnSecondary}>
              {t.execution.open_plan}
            </button>
          )}
        </div>
      )}

      {loadState === 'ready' && works.length > 0 && (
        <ol aria-label={`execution-works-${surfaceId}`} className="space-y-2">
          {works.map((work, index) => {
            const key = work.occurrence_key;
            const execution = work.execution;
            const status = execution?.status;
            const pending = pendingKey === key;
            const busy = pendingKey !== null;
            const optionsOpen = optionsKey === key;
            const message = messages[key];
            const secondary: { status: WorkExecutionStatus; label: string; name: string }[] =
              status === 'NOT_STARTED' ? [{ status: 'COMPLETED', label: t.execution.complete_now, name: 'complete-now' }]
                : status === 'IN_PROGRESS' ? [{ status: 'NOT_STARTED', label: t.execution.reset, name: 'reset' }]
                  : status === 'COMPLETED' ? [{ status: 'IN_PROGRESS', label: t.execution.reopen, name: 'reopen' }]
                    : [];
            return (
              <li
                key={key}
                aria-label={`execution-card-${key}`}
                aria-busy={pending}
                className="min-w-0 rounded-lg border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-bg-color)] p-2 space-y-2"
              >
                {/* Name first at full width, status below: a badge beside a long
                    name would squeeze it into mid-word breaks at 320 px. */}
                <div className="space-y-1">
                  <p className="min-w-0 text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">
                    <span aria-hidden="true" className="text-[var(--tg-theme-hint-color)]">{index + 1}. </span>
                    {priceItemLabel(t, work.price_item, t.work_plan.unavailable_item)}
                  </p>
                  {status && <ExecutionStatusBadge status={status} ariaLabel={`execution-status-${key}`} />}
                </div>

                {work.wait_after_hours !== null && (
                  <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">
                    <span aria-hidden="true">⏸ </span>
                    {t.work_plan.wait_after_work.replace('{value}', formatWaitHours(t, locale, work.wait_after_hours))}
                  </p>
                )}
                {execution?.started_at && (
                  <p aria-label={`execution-started-${key}`} className="text-xs text-[var(--tg-theme-hint-color)] break-words">
                    {t.execution.started_recorded.replace('{value}', formatRecordedDateTime(execution.started_at, locale))}
                  </p>
                )}
                {execution?.completed_at && (
                  <p aria-label={`execution-completed-${key}`} className="text-xs text-[var(--tg-theme-hint-color)] break-words">
                    {t.execution.completed_recorded.replace('{value}', formatRecordedDateTime(execution.completed_at, locale))}
                  </p>
                )}
                {execution?.ready_after && (
                  <div aria-label={`execution-ready-${key}`} className="rounded-lg border border-[var(--tg-control-border-color)] px-2 py-1 space-y-0.5">
                    <p className="text-xs font-semibold text-[var(--tg-theme-text-color)] break-words">
                      {t.execution.ready_after.replace('{value}', formatRecordedDateTime(execution.ready_after, locale))}
                    </p>
                    <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{t.execution.ready_hint}</p>
                  </div>
                )}

                {message && (
                  <p
                    role={message.kind === 'error' ? 'alert' : 'status'}
                    aria-label={`execution-message-${key}`}
                    className={`text-xs font-semibold break-words ${message.kind === 'error' ? 'text-[var(--tg-theme-destructive-text-color)]' : 'text-[var(--tg-theme-accent-text-color)]'}`}
                  >
                    {message.text}
                  </p>
                )}
                {pending && (
                  <p role="status" className="text-xs text-[var(--tg-theme-hint-color)]">{t.execution.pending}</p>
                )}

                {status === 'NOT_STARTED' && (
                  <button type="button" aria-label={`execution-start-${key}`} disabled={busy}
                    onClick={() => void transition(work, 'IN_PROGRESS')} className={btnPrimary}>
                    {t.execution.start}
                  </button>
                )}
                {status === 'IN_PROGRESS' && (
                  <button type="button" aria-label={`execution-complete-${key}`} disabled={busy}
                    onClick={() => void transition(work, 'COMPLETED')} className={btnPrimary}>
                    {t.execution.complete}
                  </button>
                )}
                {secondary.length > 0 && (
                  <>
                    <button
                      type="button"
                      aria-label={`execution-options-${key}`}
                      aria-expanded={optionsOpen}
                      disabled={busy}
                      onClick={() => setOptionsKey(optionsOpen ? null : key)}
                      className={btnSecondary}
                    >
                      {optionsOpen ? t.execution.hide_options : t.execution.options}
                    </button>
                    {optionsOpen && secondary.map((action) => (
                      <button
                        key={action.name}
                        type="button"
                        aria-label={`execution-${action.name}-${key}`}
                        disabled={busy}
                        onClick={() => void transition(work, action.status)}
                        className={btnSecondary}
                      >
                        {action.label}
                      </button>
                    ))}
                  </>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {loadState === 'ready' && showBulk && works.length > 0 && (
        <div className="space-y-2 pt-1 border-t border-[var(--tg-control-border-color)]">
          <button
            type="button"
            aria-label={`execution-bulk-open-${surfaceId}`}
            onClick={() => void openBulkPreview()}
            disabled={bulkBusy !== null || pendingKey !== null}
            className={btnSecondary}
          >
            {bulkBusy === 'previewing' ? t.execution.bulk.previewing : t.execution.bulk.open}
          </button>
          {bulkNotice && (
            <div aria-label={`execution-bulk-result-${surfaceId}`} role={bulkNotice.kind === 'done' ? 'status' : 'alert'} className="space-y-1">
              {bulkNoticeLines(bulkNotice).map((line) => (
                <p
                  key={line.text}
                  className={`text-sm break-words ${
                    line.tone === 'error' ? 'font-semibold text-[var(--tg-theme-destructive-text-color)]'
                      : line.tone === 'ok' ? 'font-semibold text-[var(--tg-theme-text-color)]'
                        : 'text-[var(--tg-theme-hint-color)]'}`}
                >
                  {line.tone === 'ok' && <span aria-hidden="true">✓ </span>}
                  {line.text}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {bulkPreview && (
        <ExecutionBulkSheet
          preview={bulkPreview}
          surfaceNames={surfaceNames}
          applying={bulkBusy === 'applying'}
          error={bulkSheetError}
          onConfirm={() => void confirmBulk()}
          onClose={() => {
            setBulkPreview(null);
            setBulkSheetError(null);
          }}
          idSuffix={surfaceId}
        />
      )}

      {loadState === 'ready' && (
        <button
          type="button"
          aria-label={`close-execution-bottom-${surfaceId}`}
          onClick={onClose}
          className={btnSecondary}
        >
          {t.common.close}
        </button>
      )}
    </section>
  );
}
