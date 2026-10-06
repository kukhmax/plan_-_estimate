import { useI18n } from '../hooks/useI18n';
import { CameraIcon } from './PhotoIcons';

interface PhotoEntryButtonProps {
  /** Visible photos of the target (from the counts endpoint). */
  count: number;
  expanded: boolean;
  onToggle: () => void;
}

/** The compact photo button in the upper-right corner of a card (owner clarification C-1): camera glyph + count. */
export function PhotoEntryButton({ count, expanded, onToggle }: PhotoEntryButtonProps) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      aria-label={t.photos.section.entry_aria.replace('{count}', String(count))}
      className={`inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 rounded-full border px-3 text-sm font-semibold transition ${
        expanded
          ? 'border-transparent bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]'
          : 'border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]'
      }`}
    >
      <CameraIcon />
      <span>{count}</span>
    </button>
  );
}
