import { useEffect, useState } from 'react';
import { fetchPriceItems } from '../api/priceItems';
import { fetchProjects } from '../api/projects';
import { fetchRooms } from '../api/rooms';
import { useI18n } from '../hooks/useI18n';

/** What the three steps of the start look at (usability U-3). `null` = not read yet. */
export interface StartProgress {
  hasClients: boolean;
  hasProjects: boolean | null;
  hasPrices: boolean | null;
  hasRooms: boolean | null;
}

const ROOM_PROBE_LIMIT = 5;

/**
 * Reads what is already done from the existing lists (no new API): objects, prices with a value, a room in one of the first objects.
 * A list that fails to load leaves its step open: the card never blocks the screen.
 */
export function useStartProgress(hasClients: boolean): StartProgress {
  const [state, setState] = useState<Omit<StartProgress, 'hasClients'>>({ hasProjects: null, hasPrices: null, hasRooms: null });
  useEffect(() => {
    let cancelled = false;
    const done = (patch: Partial<Omit<StartProgress, 'hasClients'>>) => {
      if (!cancelled) setState((current) => ({ ...current, ...patch }));
    };
    // each list is read on its own, inside a promise chain: a failure of one (or an answer of an unexpected shape) leaves its step open
    void Promise.resolve()
      .then(() => fetchProjects(false))
      .then(async (found) => {
        done({ hasProjects: found.items.length > 0 });
        for (const project of found.items.slice(0, ROOM_PROBE_LIMIT)) {
          const rooms = await fetchRooms(project.id);
          if (rooms.items.length > 0) return done({ hasRooms: true });
        }
        done({ hasRooms: false });
      })
      .catch(() => done({ hasProjects: false, hasRooms: false }));
    void Promise.resolve()
      .then(() => fetchPriceItems())
      .then((found) => done({ hasPrices: found.items.some((item) => item.price !== null) }))
      .catch(() => done({ hasPrices: false }));
    return () => {
      cancelled = true;
    };
  }, [hasClients]);
  return { hasClients, ...state };
}

interface GettingStartedProps {
  progress: StartProgress;
  /** The main button: the form of a client (and then of his object). */
  onAddClient: () => void;
  onOpenPricebook: () => void;
  onOpenProjects: () => void;
}

/** "Od czego zacząć": the three steps of a new contractor, the finished ones ticked (usability U-3). */
export function GettingStarted({ progress, onAddClient, onOpenPricebook, onOpenProjects }: GettingStartedProps) {
  const { t } = useI18n();
  const text = t.onboarding;
  const steps = [
    { id: 'client', label: text.step_client, done: progress.hasClients && progress.hasProjects === true, action: onAddClient, icon: '👤' },
    { id: 'prices', label: text.step_prices, done: progress.hasPrices === true, action: onOpenPricebook, icon: '🏷️' },
    { id: 'room', label: text.step_room, done: progress.hasRooms === true, action: onOpenProjects, icon: '📐' },
  ];
  return (
    <section aria-label="getting-started" className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="text-base font-bold text-slate-900 break-words">{text.title}</h3>
      <p className="text-sm text-slate-600 break-words">{text.intro}</p>
      <ol className="space-y-2">
        {steps.map((step, index) => (
          <li key={step.id}>
            <button
              type="button"
              aria-label={`start-step-${step.id}`}
              data-done={step.done ? 'true' : 'false'}
              onClick={step.action}
              className={`w-full min-h-11 px-3 py-2 rounded-xl text-left text-sm font-semibold flex items-center gap-3 break-words transition ${
                index === 0 && !step.done
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'border border-slate-300 text-slate-800 hover:bg-slate-100'
              }`}
            >
              <span aria-hidden="true" className="shrink-0 w-6 text-center">{step.done ? '✅' : step.icon}</span>
              <span className="min-w-0 flex-1">{index + 1}. {step.label}</span>
              {step.done && <span className="shrink-0 text-xs font-medium text-emerald-700">{text.done}</span>}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
