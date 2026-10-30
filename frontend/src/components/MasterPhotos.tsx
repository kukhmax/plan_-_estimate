import { useEffect, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import type { PortalMarker, PortalPhoto } from '../types/tradeLink';
import { cmText, isPhotoUtility, markerColor } from '../utils/photoUtilities';
import { getPlaceDisplayName } from '../utils/surfaceDisplayName';

interface MasterPhotosProps {
  photos: PortalPhoto[];
  routeMap: PortalPhoto[];
  roomName: string;
}

/** The text of a marker as the craftsman reads it: what it is, its caption, where it lies. */
function markerText(marker: PortalMarker, words: ReturnType<typeof useWords>): string {
  const parts: string[] = [];
  if (isPhotoUtility(marker.utility)) parts.push(words.utility[marker.utility]);
  if (marker.label) parts.push(marker.label);
  if (marker.from_floor_cm !== null) parts.push(words.legend_floor.replace('{v}', cmText(marker.from_floor_cm)));
  if (marker.from_corner_cm !== null) parts.push(words.legend_corner.replace('{v}', cmText(marker.from_corner_cm)));
  if (marker.depth_cm !== null) parts.push(words.legend_depth.replace('{v}', cmText(marker.depth_cm)));
  return parts.join(' · ');
}

function useWords() {
  return useI18n().t.photos.markers;
}

/** The numbered dots of the markers on a picture (a wrapper that is exactly as big as the picture). */
function Dots({ markers }: { markers: PortalMarker[] }) {
  return (
    <>
      {markers.map((marker, index) => (
        <span
          key={index}
          aria-hidden="true"
          className="absolute flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-white text-xs font-bold leading-none text-white shadow"
          style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%`, backgroundColor: markerColor(marker) }}
        >
          {index + 1}
        </span>
      ))}
    </>
  );
}

function Legend({ markers }: { markers: PortalMarker[] }) {
  const words = useWords();
  if (markers.length === 0) return null;
  return (
    <ul className="space-y-1">
      {markers.map((marker, index) => (
        <li key={index} className="flex items-start gap-2 text-sm">
          <span
            aria-hidden="true"
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold leading-none text-white"
            style={{ backgroundColor: markerColor(marker) }}
          >
            {index + 1}
          </span>
          <span className="min-w-0 break-words">{markerText(marker, words) || words.popup_no_label}</span>
        </li>
      ))}
    </ul>
  );
}

/** The full picture over the page: the photo as big as the screen allows, its markers and what they say. A link that has run out is told so (the page is read again to renew it). */
function Lightbox({ photo, onClose, onExpired }: { photo: PortalPhoto; onClose: () => void; onExpired: () => void }) {
  const { t } = useI18n();
  const text = t.master_page;
  const [broken, setBroken] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label="master-photo-viewer" className="fixed inset-0 z-50 flex flex-col text-white" style={{ backgroundColor: 'rgba(0, 0, 0, 0.96)' }}>
      <div className="flex items-center justify-between gap-3 px-4 py-2">
        <p className="min-w-0 text-sm break-words">{getPlaceDisplayName(photo.place, { wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling })}</p>
        <button type="button" aria-label="master-photo-close" onClick={onClose} className="shrink-0 min-h-12 min-w-12 rounded-xl border border-white/40 text-xl">
          <span aria-hidden="true">✕</span>
          <span className="sr-only">{text.photo_close}</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 pb-6 space-y-3">
        {broken ? (
          <div className="space-y-2 py-6 text-center">
            <p className="text-sm">{text.photo_expired}</p>
            <button type="button" aria-label="master-photo-reload" onClick={() => { onExpired(); onClose(); }} className="min-h-12 px-4 rounded-xl border-2 border-white font-semibold" style={{ color: '#ffffff' }}>
              {text.photo_reload}
            </button>
          </div>
        ) : (
          <div className="relative mx-auto w-fit max-w-full">
            <img src={photo.url} alt="" width={photo.width} height={photo.height} onError={() => setBroken(true)} className="block max-h-[70vh] max-w-full h-auto w-auto" />
            <Dots markers={photo.markers} />
          </div>
        )}
        <Legend markers={photo.markers} />
      </div>
    </div>
  );
}

/**
 * V2-14b — what a craftsman sees of the photos of a room: the photos of the room itself and the route map of his trade (the photos with the markers of the hidden utilities he works on,
 * in the colours of their types, with where each one lies). A picture opens full screen. The links are signed for a short time; one that has run out asks for the page again.
 */
export function MasterPhotos({ photos, routeMap, roomName, onExpired }: MasterPhotosProps & { onExpired: () => void }) {
  const { t } = useI18n();
  const text = t.master_page;
  const [open, setOpen] = useState<PortalPhoto | null>(null);
  if (photos.length === 0 && routeMap.length === 0) return null;
  return (
    <div className="space-y-3">
      {routeMap.length > 0 && (
        <div aria-label={`master-route-map-${roomName}`} className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-700 break-words">{text.route_map_title.replace('{count}', String(routeMap.length))}</h3>
          <p className="text-xs text-slate-500 break-words">{text.route_map_hint}</p>
          <ul className="space-y-3">
            {routeMap.map((photo) => (
              <li key={photo.id} className="space-y-2">
                {photo.place && <p className="text-xs font-semibold text-slate-500 break-words">{getPlaceDisplayName(photo.place, { wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling })}</p>}
                <button type="button" aria-label={`master-map-photo-${photo.id}`} onClick={() => setOpen(photo)} className="relative block w-full rounded-xl overflow-hidden border border-slate-200">
                  <span className="relative block w-full">
                    <img src={photo.thumb_url} alt="" loading="lazy" className="block w-full h-auto" />
                    <Dots markers={photo.markers} />
                  </span>
                </button>
                <Legend markers={photo.markers} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {photos.length > 0 && (
        <div aria-label={`master-room-photos-${roomName}`} className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-700 break-words">{text.photos_title.replace('{count}', String(photos.length))}</h3>
          <ul className="grid grid-cols-2 gap-2">
            {photos.map((photo) => (
              <li key={photo.id}>
                <button type="button" aria-label={`master-photo-${photo.id}`} onClick={() => setOpen(photo)} className="block w-full min-h-11 rounded-xl overflow-hidden border border-slate-200">
                  <img src={photo.thumb_url} alt="" loading="lazy" className="block w-full h-auto" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {open && <Lightbox photo={open} onClose={() => setOpen(null)} onExpired={onExpired} />}
    </div>
  );
}
