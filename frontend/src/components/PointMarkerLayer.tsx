import { useI18n } from '../hooks/useI18n';
import { PhotoAnnotationRead } from '../types/photo';

// Point markers drawn over a photo (Stage 14G). The layer fills the box of the picture (its parent is positioned exactly
// over the image), and every marker sits at its stored fraction of that box, so it stays on the same spot whatever the
// screen size, the thumbnail or the zoom. A marker looks like a 24 px numbered dot but its button is 44 px, and while the
// picture is zoomed the dot is scaled back (`inverseScale`) so it does not grow with the photo.

interface PointMarkerLayerProps {
  /** In display order; the number shown on a marker is its place in this list. */
  markers: readonly PhotoAnnotationRead[];
  selectedId?: string | null;
  onSelect: (marker: PhotoAnnotationRead) => void;
  /** 1 / current zoom of the picture the layer is drawn on. */
  inverseScale?: number;
}

export function PointMarkerLayer({ markers, selectedId = null, onSelect, inverseScale = 1 }: PointMarkerLayerProps) {
  const { t } = useI18n();
  return (
    <div data-testid="marker-layer" className="pointer-events-none absolute inset-0">
      {markers.map((marker, index) => {
        const number = String(index + 1);
        const name = marker.label
          ? t.photos.markers.marker_aria_labeled.replace('{number}', number).replace('{label}', marker.label)
          : t.photos.markers.marker_aria.replace('{number}', number);
        const selected = marker.id === selectedId;
        return (
          <button
            key={marker.id}
            type="button"
            aria-label={name}
            data-testid="photo-marker"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              onSelect(marker);
            }}
            className="pointer-events-auto absolute flex h-11 w-11 items-center justify-center"
            style={{
              left: `${marker.x * 100}%`,
              top: `${marker.y * 100}%`,
              transform: `translate(-50%, -50%) scale(${inverseScale})`,
            }}
          >
            <span
              aria-hidden="true"
              className={`flex h-6 w-6 items-center justify-center rounded-full border-2 border-white text-xs font-bold leading-none shadow ${
                selected ? 'bg-[var(--tg-theme-link-color)] text-white ring-2 ring-white' : 'bg-red-600 text-white'
              }`}
            >
              {number}
            </span>
          </button>
        );
      })}
    </div>
  );
}
