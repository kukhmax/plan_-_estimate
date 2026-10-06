import { useI18n } from '../hooks/useI18n';
import { CameraIcon } from './PhotoIcons';

interface PhotoEntryButtonProps {
  /** Visible photos of the target (from the counts endpoint). */
  count: number;
  expanded: boolean;
  onToggle: () => void;
}

/**
 * The compact photo button of a card (owner clarification C-1): camera glyph + count.
 * The visible pill is small (28 px) so it costs almost no card height; the tap target stays 44 px — the button box is
 * 44 px and its vertical margin is pulled in (`-my-2`) so that the extra tap area overlaps the card padding only.
 */
export function PhotoEntryButton({ count, expanded, onToggle }: PhotoEntryButtonProps) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      aria-label={t.photos.section.entry_aria.replace('{count}', String(count))}
      className="-my-2 inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center"
    >
      <span
        className={`inline-flex h-7 items-center justify-center gap-1 rounded-full border px-2 text-xs font-semibold transition ${
          expanded
            ? 'border-transparent bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]'
            : 'border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]'
        }`}
      >
        <CameraIcon size={16} />
        <span>{count}</span>
      </span>
    </button>
  );
}
