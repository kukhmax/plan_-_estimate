import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from 'react';

// Back-navigation integration (contract §8, D6). `ProjectWorkspace` owns the only Telegram BackButton handler and
// provides this context; an open photo viewer registers its closer so the workspace's handler calls it FIRST.
// Without a provider (tests, plain browser) registration is a no-op and the viewer still has its own close button.

export interface PhotoBackRegistry {
  /** Register a closer; returns the unregister function. */
  register: (close: () => void) => () => void;
}

export const PhotoBackContext = createContext<PhotoBackRegistry | null>(null);

export function usePhotoBackRegistration(active: boolean, close: () => void): void {
  const registry = useContext(PhotoBackContext);
  const registryRef = useRef(registry);
  const closeRef = useRef(close);
  useEffect(() => {
    registryRef.current = registry;
    closeRef.current = close;
  }, [registry, close]);

  // Registration depends only on "active" and on whether a provider exists: a provider that hands out a fresh
  // object on every render must not make the viewer unregister and register again each time.
  const hasRegistry = registry !== null;
  useEffect(() => {
    if (!active || !hasRegistry) return;
    return registryRef.current?.register(() => closeRef.current());
  }, [active, hasRegistry]);
}

/**
 * The workspace side of the seam: a stack of registered closers. The Telegram BackButton handler calls
 * `closeTop()` FIRST; it returns true when an open photo viewer took the press (nothing else must navigate).
 * The registry object is stable for the lifetime of the workspace.
 */
export function usePhotoBackStack(): { registry: PhotoBackRegistry; closeTop: () => boolean } {
  const stack = useRef<Array<() => void>>([]);
  const registry = useMemo<PhotoBackRegistry>(
    () => ({
      register: (close) => {
        stack.current.push(close);
        return () => {
          const index = stack.current.lastIndexOf(close);
          if (index >= 0) stack.current.splice(index, 1);
        };
      },
    }),
    [],
  );
  const closeTop = useCallback(() => {
    const top = stack.current[stack.current.length - 1];
    if (!top) return false;
    top();
    return true;
  }, []);
  return { registry, closeTop };
}
