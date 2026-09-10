import { useCallback, useState } from 'react';

export interface OpeningDimensions {
  width: number;
  height: number;
}

export type OpeningDefaults = Partial<Record<'DOOR' | 'WINDOW', OpeningDimensions>>;

export type DefaultableOpeningType = 'DOOR' | 'WINDOW';

const STORAGE_PREFIX = 'plan-estimate:opening-defaults:';

function loadDefaults(projectId: string): OpeningDefaults {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + projectId);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') return parsed as OpeningDefaults;
  } catch {
    // Corrupt or unavailable storage: fall back to no defaults.
  }
  return {};
}

function persistDefaults(projectId: string, defaults: OpeningDefaults): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + projectId, JSON.stringify(defaults));
  } catch {
    // Storage unavailable (private mode): defaults stay ephemeral for the session.
  }
}

export function useOpeningDefaults(projectId: string) {
  const [defaults, setDefaults] = useState<OpeningDefaults>(() => loadDefaults(projectId));

  const setTypeDefault = useCallback(
    (type: DefaultableOpeningType, dimensions: OpeningDimensions) => {
      setDefaults((current) => {
        const next = { ...current, [type]: dimensions };
        persistDefaults(projectId, next);
        return next;
      });
    },
    [projectId],
  );

  return { defaults, setTypeDefault };
}