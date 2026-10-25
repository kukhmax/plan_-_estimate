import { useState } from 'react';
import { addPointsToEstimate } from '../api/roomPoints';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';
import { Ico } from './Ico';

export interface PointsMessage {
  kind: 'ok' | 'error';
  text: string;
}

interface EstimatePointsActionProps {
  projectId: string;
  estimateId: string;
  /** The answer to show; it lives in the estimate screen because reading the estimate again replaces the screen for a moment. */
  message: PointsMessage | null;
  onMessage: (message: PointsMessage | null) => void;
  /** The lines changed: the estimate is read again. */
  onAdded: () => void;
}

/** V2-10 — one button on a draft estimate: the points and routes of the rooms become its lines (a snapshot; nothing is added twice). Online only. */
export function EstimatePointsAction({ projectId, estimateId, message, onMessage, onAdded }: EstimatePointsActionProps) {
  const { t } = useI18n();
  const text = t.roomPoints;
  const { offline } = useConnection();
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (busy) return;
    setBusy(true);
    onMessage(null);
    try {
      const result = await addPointsToEstimate(projectId, estimateId);
      if (result.added === 0 && result.already === 0 && result.skipped.length === 0) {
        onMessage({ kind: 'ok', text: text.estimate_nothing });
      } else {
        const parts = [text.estimate_added.replace('{added}', String(result.added)).replace('{already}', String(result.already))];
        if (result.skipped.length > 0) parts.push(text.estimate_skipped.replace('{skipped}', String(result.skipped.length)));
        onMessage({ kind: 'ok', text: parts.join(' ') });
      }
      if (result.added > 0) onAdded();
    } catch (err) {
      onMessage({ kind: 'error', text: err instanceof ApiError && err.code === 'ESTIMATE_NOT_DRAFT' ? text.estimate_not_draft : text.estimate_error });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div aria-label="estimate-points" className="col-span-2 space-y-2">
      <button
        type="button"
        aria-label="estimate-add-points-action"
        disabled={busy || offline}
        onClick={() => void add()}
        className="w-full min-h-[44px] px-3 py-1 text-sm font-semibold text-slate-800 pe-surface border border-slate-300 rounded-xl hover:bg-slate-100 transition break-words disabled:opacity-50"
      >
        <Ico>{busy ? '⏳' : '🔌'}</Ico>{text.estimate_button}
      </button>
      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-xs break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>
          {message.text}
        </p>
      )}
    </div>
  );
}
