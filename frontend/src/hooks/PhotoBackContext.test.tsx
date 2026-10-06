import { renderHook } from '@testing-library/react';
import { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { PhotoBackContext, usePhotoBackRegistration } from './PhotoBackContext';

function wrapper(register: (close: () => void) => () => void) {
  return ({ children }: { children: ReactNode }) => (
    <PhotoBackContext.Provider value={{ register }}>{children}</PhotoBackContext.Provider>
  );
}

describe('usePhotoBackRegistration', () => {
  it('is a harmless no-op without a provider', () => {
    expect(() => renderHook(() => usePhotoBackRegistration(true, vi.fn()))).not.toThrow();
  });

  it('registers while active and unregisters when it stops or unmounts', () => {
    const unregister = vi.fn();
    const register = vi.fn(() => unregister);
    const { rerender, unmount } = renderHook(({ active }) => usePhotoBackRegistration(active, vi.fn()), {
      wrapper: wrapper(register),
      initialProps: { active: true },
    });
    expect(register).toHaveBeenCalledTimes(1);
    rerender({ active: false });
    expect(unregister).toHaveBeenCalledTimes(1);
    rerender({ active: true });
    expect(register).toHaveBeenCalledTimes(2);
    unmount();
    expect(unregister).toHaveBeenCalledTimes(2);
  });

  it('keeps one registration but always calls the latest closer', () => {
    let registered: (() => void) | undefined;
    const register = vi.fn((close: () => void) => {
      registered = close;
      return () => undefined;
    });
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ close }) => usePhotoBackRegistration(true, close), {
      wrapper: wrapper(register),
      initialProps: { close: first },
    });
    rerender({ close: second });
    expect(register).toHaveBeenCalledTimes(1);
    registered?.();
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});

describe('usePhotoBackStack', () => {
  it('has a stable registry and closes the most recently registered viewer first', async () => {
    const { usePhotoBackStack } = await import('./PhotoBackContext');
    const { result, rerender } = renderHook(() => usePhotoBackStack());
    const registry = result.current.registry;
    rerender();
    expect(result.current.registry).toBe(registry);

    expect(result.current.closeTop()).toBe(false); // nothing open: Back belongs to the workspace
    const first = vi.fn();
    const second = vi.fn();
    const offFirst = registry.register(first);
    const offSecond = registry.register(second);
    expect(result.current.closeTop()).toBe(true);
    expect(second).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();

    offSecond();
    expect(result.current.closeTop()).toBe(true);
    expect(first).toHaveBeenCalledTimes(1);
    offFirst();
    expect(result.current.closeTop()).toBe(false);
  });

  it('ignores a second unregister', async () => {
    const { usePhotoBackStack } = await import('./PhotoBackContext');
    const { result } = renderHook(() => usePhotoBackStack());
    const close = vi.fn();
    const off = result.current.registry.register(close);
    off();
    off();
    expect(result.current.closeTop()).toBe(false);
  });
});
