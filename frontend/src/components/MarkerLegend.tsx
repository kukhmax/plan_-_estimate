import { useI18n } from '../hooks/useI18n';
import { PhotoAnnotationRead } from '../types/photo';
import { cmText, hasUtility, isPhotoUtility, markerColor } from '../utils/photoUtilities';

// V2-12a: the legend of the hidden utilities of a photo: for each marker its number in the colour of its type, what it is, where it
// lies. It is shown only when at least one marker names a utility (a photo of ordinary markers stays as it was).

export function MarkerLegend({ markers }: { markers: readonly PhotoAnnotationRead[] }) {
  const { t } = useI18n();
  if (!hasUtility(markers)) return null;
  const words = t.photos.markers;
  return (
    <div data-testid="marker-legend" className="space-y-1">
      <p className="text-xs font-semibold text-[var(--tg-theme-hint-color)]">{words.legend_title}</p>
      <ul className="space-y-1">
        {markers.map((marker, index) => {
          const parts: string[] = [];
          if (isPhotoUtility(marker.utility)) parts.push(words.utility[marker.utility]);
          if (marker.label) parts.push(marker.label);
          if (marker.from_floor_cm !== null && marker.from_floor_cm !== undefined) parts.push(words.legend_floor.replace('{v}', cmText(marker.from_floor_cm)));
          if (marker.from_corner_cm !== null && marker.from_corner_cm !== undefined) parts.push(words.legend_corner.replace('{v}', cmText(marker.from_corner_cm)));
          if (marker.depth_cm !== null && marker.depth_cm !== undefined) parts.push(words.legend_depth.replace('{v}', cmText(marker.depth_cm)));
          return (
            <li key={marker.id} className="flex items-start gap-2 text-sm">
              <span
                aria-hidden="true"
                className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold leading-none text-white"
                style={{ backgroundColor: markerColor(marker) }}
              >
                {index + 1}
              </span>
              <span className="min-w-0 break-words">{parts.length > 0 ? parts.join(' · ') : words.popup_no_label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
