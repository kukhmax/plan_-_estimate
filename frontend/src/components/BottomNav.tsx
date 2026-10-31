import { useI18n } from '../hooks/useI18n';
import { useKeyboardOpen } from '../hooks/useKeyboardOpen';

export type BottomNavSection = 'projects' | 'clients' | 'pricebook';

interface BottomNavProps {
  active: string;
  /** An overlay (the menu, the account window, the sync screen) is open: the bar steps aside. */
  hidden?: boolean;
  onSelect: (section: BottomNavSection) => void;
  onMore: () => void;
}

/**
 * The bottom bar of the application (usability U-11): the three places a contractor goes to all day -- Obiekty, Klienci, Cennik -- and
 * "Więcej" (the whole menu). 56 px plus the safe area of the phone; it hides while the keyboard is open.
 */
export function BottomNav({ active, hidden = false, onSelect, onMore }: BottomNavProps) {
  const { t } = useI18n();
  const keyboardOpen = useKeyboardOpen();
  if (hidden || keyboardOpen) return null;
  const item = (id: BottomNavSection, label: string, icon: string) => (
    <button
      key={id}
      type="button"
      aria-label={`bottom-nav-${id}`}
      aria-labelledby={`pe-name-bottom-nav-${id}`}
      aria-current={active === id ? 'page' : undefined}
      onClick={() => onSelect(id)}
      className={`min-h-14 min-w-0 flex flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-semibold break-words text-center ${
        active === id ? 'text-[var(--tg-theme-link-color)]' : 'text-[var(--tg-theme-hint-color)]'
      }`}
    >
      <span aria-hidden="true" className="text-lg leading-none select-none">{icon}</span>
      <span id={`pe-name-bottom-nav-${id}`} className="min-w-0 leading-tight">{label}</span>
    </button>
  );
  return (
    <nav
      aria-label="bottom-nav"
      className="fixed inset-x-0 bottom-0 z-30 border-t pb-[env(safe-area-inset-bottom)]"
      style={{ backgroundColor: 'var(--tg-theme-bg-color)', borderColor: 'var(--tg-theme-secondary-bg-color)' }}
    >
      <div className="mx-auto grid w-full max-w-lg grid-cols-4">
        {item('projects', t.navigation.projects, '🏗️')}
        {item('clients', t.navigation.clients, '👤')}
        {item('pricebook', t.navigation.pricebook, '🏷️')}
        <button
          type="button"
          aria-label="bottom-nav-more"
          aria-labelledby="pe-name-bottom-nav-more"
          onClick={onMore}
          className="min-h-14 min-w-0 flex flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-semibold text-center text-[var(--tg-theme-hint-color)]"
        >
          <span aria-hidden="true" className="text-lg leading-none">☰</span>
          <span id="pe-name-bottom-nav-more" className="min-w-0 leading-tight">{t.navigation.more}</span>
        </button>
      </div>
    </nav>
  );
}
