import { useEffect, useRef } from 'react';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';

export interface AppMenuItem {
  /** Technical name, also the accessible name of the button (`show-projects`, …). */
  id: string;
  label: string;
  active: boolean;
  onSelect: () => void;
}

interface AppMenuProps {
  open: boolean;
  title: string;
  accountLabel: string;
  items: AppMenuItem[];
  onClose: () => void;
  onOpenAccount: () => void;
}

/**
 * The main menu: a panel that slides in from the left. It is the only way to move between the top-level sections, so
 * it closes on a choice, on a tap outside, on Escape and on the Telegram BackButton.
 */
export function AppMenu({ open, title, accountLabel, items, onClose, onOpenAccount }: AppMenuProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useTelegramBackButton(open, onClose);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40" data-testid="app-menu">
      <button
        type="button"
        aria-label="close-menu-backdrop"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 w-full h-full cursor-default touch-none"
        style={{ backgroundColor: 'rgba(0, 0, 0, 0.45)' }}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="main-menu"
        className="app-menu-panel absolute inset-y-0 left-0 w-[85%] max-w-xs flex flex-col shadow-xl overflow-y-auto overscroll-contain"
        style={{ backgroundColor: 'var(--tg-theme-bg-color)', color: 'var(--tg-theme-text-color)' }}
      >
        <div className="flex items-center justify-between gap-2 px-4 py-2 min-h-14">
          <span className="text-lg font-bold tracking-tight truncate">{title}</span>
          <button
            ref={closeRef}
            type="button"
            aria-label="close-menu"
            onClick={onClose}
            className="min-h-11 min-w-11 shrink-0 flex items-center justify-center rounded-xl text-xl leading-none"
            style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-hint-color)' }}
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>

        <nav aria-label="main-navigation" className="flex flex-col gap-2 px-4 py-2">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-label={item.id}
              aria-current={item.active ? 'page' : undefined}
              onClick={item.onSelect}
              className="min-h-12 w-full px-4 py-2 text-left text-base font-semibold rounded-xl break-words transition"
              style={
                item.active
                  ? { backgroundColor: 'var(--tg-theme-button-color)', color: 'var(--tg-theme-button-text-color)' }
                  : { backgroundColor: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }
              }
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="mt-auto px-4 py-4">
          <button
            type="button"
            aria-label="open-account"
            onClick={onOpenAccount}
            className="min-h-12 w-full px-4 py-2 text-left text-base font-semibold rounded-xl transition"
            style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-link-color)' }}
          >
            {accountLabel}
          </button>
        </div>
      </aside>
    </div>
  );
}
