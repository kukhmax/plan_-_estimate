import { useI18n } from '../hooks/useI18n';
import { PhotoAnnotationRead } from '../types/photo';
import { OutlinePoint, polylinePoints } from '../utils/outline';

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
  /** The stroke being drawn right now (contour drawing), shown live. */
  draft?: readonly OutlinePoint[];
  /** False while drawing: a finger that starts on a marker must draw, not press it. */
  interactive?: boolean;
}

// Contour line: a white under-line and a thin red line over it, so it reads on light and dark walls alike. The width is
// in screen pixels (non-scaling stroke) and does not grow with the zoom (owner: fixed colour, the thinnest line).
const OUTLINE_UNDER_WIDTH = 3.5;
const OUTLINE_WIDTH = 1.5;

function Line({ points, inverseScale }: { points: readonly OutlinePoint[]; inverseScale: number }) {
  const common = {
    points: polylinePoints(points),
    fill: 'none',
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    vectorEffect: 'non-scaling-stroke' as const,
  };
  return (
    <>
      <polyline {...common} stroke="#ffffff" strokeWidth={OUTLINE_UNDER_WIDTH * inverseScale} />
      <polyline {...common} stroke="#dc2626" strokeWidth={OUTLINE_WIDTH * inverseScale} />
    </>
  );
}

export function PointMarkerLayer({
  markers,
  selectedId = null,
  onSelect,
  inverseScale = 1,
  draft = [],
  interactive = true,
}: PointMarkerLayerProps) {
  const { t } = useI18n();
  return (
    <div data-testid="marker-layer" className="pointer-events-none absolute inset-0">
      <svg
        data-testid="outline-layer"
        aria-hidden="true"
        viewBox="0 0 1 1"
        preserveAspectRatio="none"
        className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
      >
        {markers.map((marker) =>
          marker.outline && marker.outline.length > 1 ? (
            <g key={marker.id} data-testid="marker-outline">
              <Line points={marker.outline} inverseScale={inverseScale} />
            </g>
          ) : null,
        )}
        {draft.length > 1 && (
          <g data-testid="outline-draft">
            <Line points={draft} inverseScale={inverseScale} />
          </g>
        )}
      </svg>
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
            className={`${interactive ? 'pointer-events-auto' : 'pointer-events-none'} absolute flex h-11 w-11 items-center justify-center`}
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
