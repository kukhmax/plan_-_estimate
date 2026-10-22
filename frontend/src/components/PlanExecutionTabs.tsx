import { ExecutionPhotoBadge } from './ExecutionPhotoBadge';
import { Ico } from './Ico';
import { useI18n } from '../hooks/useI18n';

interface PlanExecutionTabsProps {
  surfaceId: string;
  planOpen: boolean;
  executionOpen: boolean;
  onPlan: () => void;
  onExecution: () => void;
}

/**
 * "Rodzaje prac i jakość" as two segments, Plan | Realizacja (usability U-5): the plan is for planning only; the progress of the works is
 * the other segment. Tapping a segment opens its view under the control; tapping it again closes it. One row instead of two buttons.
 */
export function PlanExecutionTabs({ surfaceId, planOpen, executionOpen, onPlan, onExecution }: PlanExecutionTabsProps) {
  const { t } = useI18n();
  const base = 'min-h-11 min-w-0 px-2 py-1 text-sm font-semibold rounded-lg transition flex flex-wrap items-center justify-center gap-1.5 break-words';
  const on = 'bg-blue-600 text-white shadow-sm';
  const off = 'text-slate-700 hover:bg-slate-200';
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-slate-500 break-words">{t.surfaces.work_types_quality}</p>
      <div role="group" aria-label={`plan-tabs-${surfaceId}`} className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
        <button
          type="button"
          aria-label={`work-plan-${surfaceId}`}
          aria-expanded={planOpen}
          aria-controls={`work-plan-editor-${surfaceId}`}
          onClick={onPlan}
          className={`${base} ${planOpen ? on : off}`}
        >
          <span className="min-w-0"><Ico>🛠️</Ico>{t.work_plan.tab_plan}</span>
        </button>
        <button
          type="button"
          aria-label={`execution-${surfaceId}`}
          aria-expanded={executionOpen}
          onClick={onExecution}
          className={`${base} ${executionOpen ? on : off}`}
        >
          <span className="min-w-0"><Ico>🏗️</Ico>{t.execution.open}</span>
          <ExecutionPhotoBadge surfaceId={surfaceId} />
        </button>
      </div>
    </div>
  );
}
