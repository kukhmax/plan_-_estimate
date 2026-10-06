import { Fragment } from 'react';
import { useI18n } from '../hooks/useI18n';
import { PhotoListItem } from '../types/photo';
import { photoDayLabel } from '../utils/photoCaption';

// Thumbnail grid with the caption line under every tile (owner clarification C-2). 2 columns at ≤ 340 px, 3 above;
// fixed square cells so nothing jumps while images load; the order is the server's order (cursor pagination).

/** Beyond this many items the project-wide list is grouped by day (C-3). */
export const GROUP_BY_DAY_THRESHOLD = 12;

interface PhotoThumbGridProps {
  items: readonly PhotoListItem[];
  captionFor: (item: PhotoListItem) => string;
  onOpen: (index: number) => void;
  onImageError: () => void;
  hasMore: boolean;
  loadingMore: boolean;
  onShowMore: () => void;
  groupByDay?: boolean;
}

interface Group {
  label: string | null;
  entries: Array<{ item: PhotoListItem; index: number }>;
}

function groupItems(items: readonly PhotoListItem[], byDay: boolean): Group[] {
  if (!byDay) return [{ label: null, entries: items.map((item, index) => ({ item, index })) }];
  const groups: Group[] = [];
  items.forEach((item, index) => {
    const label = photoDayLabel(item.asset);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.entries.push({ item, index });
    else groups.push({ label, entries: [{ item, index }] });
  });
  return groups;
}

export function PhotoThumbGrid({
  items,
  captionFor,
  onOpen,
  onImageError,
  hasMore,
  loadingMore,
  onShowMore,
  groupByDay = false,
}: PhotoThumbGridProps) {
  const { t } = useI18n();
  const groups = groupItems(items, groupByDay && items.length > GROUP_BY_DAY_THRESHOLD);

  return (
    <div className="space-y-3">
      {groups.map((group, groupIndex) => (
        <Fragment key={`${group.label ?? 'all'}-${groupIndex}`}>
          {group.label && (
            <h4
              data-testid="photo-day-header"
              className="sticky top-0 z-10 bg-[var(--tg-theme-secondary-bg-color)] py-1 text-xs font-semibold text-[var(--tg-theme-hint-color)]"
            >
              {group.label}
            </h4>
          )}
          <ul className="grid grid-cols-2 gap-2 min-[341px]:grid-cols-3">
            {group.entries.map(({ item, index }) => {
              const caption = captionFor(item);
              const category = item.attachment.category;
              return (
                <li key={item.attachment.id} className="min-w-0">
                  <button
                    type="button"
                    onClick={() => onOpen(index)}
                    aria-label={caption}
                    className="relative block aspect-square w-full overflow-hidden rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)]"
                  >
                    {item.thumbnail_url ? (
                      <img
                        src={item.thumbnail_url}
                        alt={item.attachment.caption || t.photos.viewer.photo_alt}
                        loading="lazy"
                        decoding="async"
                        referrerPolicy="no-referrer"
                        onError={onImageError}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <span className="flex h-full w-full items-center justify-center p-1 text-center text-[11px] text-[var(--tg-theme-hint-color)]">
                        {t.photos.section.thumb_unavailable}
                      </span>
                    )}
                    {(category !== 'GENERAL' || item.attachment.include_in_report) && (
                      <span className="absolute inset-x-1 bottom-1 flex flex-wrap gap-1">
                        {category !== 'GENERAL' && (
                          <span className="max-w-full break-words rounded bg-black/65 px-1.5 py-0.5 text-[10px] font-medium leading-tight text-white">
                            {t.photos.category[category]}
                          </span>
                        )}
                        {item.attachment.include_in_report && (
                          <span className="max-w-full break-words rounded bg-black/65 px-1.5 py-0.5 text-[10px] font-medium leading-tight text-white">
                            {t.photos.section.in_report}
                          </span>
                        )}
                      </span>
                    )}
                  </button>
                  <p className="mt-1 break-words text-[11px] leading-snug text-[var(--tg-theme-hint-color)]">{caption}</p>
                </li>
              );
            })}
          </ul>
        </Fragment>
      ))}
      {hasMore && (
        <button
          type="button"
          onClick={onShowMore}
          disabled={loadingMore}
          className="min-h-11 w-full rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-text-color)] disabled:opacity-50"
        >
          {loadingMore ? t.photos.section.loading : t.photos.section.show_more}
        </button>
      )}
    </div>
  );
}
