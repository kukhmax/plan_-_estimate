import {
  PhotoAssetRead,
  PhotoAttachmentRead,
  PhotoDetailResponse,
  PhotoListItem,
  PhotoListResponse,
  PhotoStorageStatus,
} from '../types/photo';

export const PROJECT_ID = '11111111-1111-4111-8111-111111111111';
export const ROOM_ID = '22222222-2222-4222-8222-222222222222';
export const SURFACE_ID = '33333333-3333-4333-8333-333333333333';

let seq = 0;

export function makeItem(over: {
  asset?: Partial<PhotoAssetRead>;
  attachment?: Partial<PhotoAttachmentRead>;
  thumbnail_url?: string | null;
} = {}): PhotoListItem {
  seq += 1;
  const assetId = `a0000000-0000-4000-8000-${String(seq).padStart(12, '0')}`;
  const asset: PhotoAssetRead = {
    id: assetId,
    project_id: PROJECT_ID,
    status: 'READY',
    content_type: 'image/jpeg',
    byte_size: 1000,
    width: 100,
    height: 100,
    original_filename: `IMG_${seq}.jpg`,
    captured_at: '2026-06-23T10:15:00',
    capture_source: 'CAMERA',
    uploaded_at: '2026-06-23T08:20:00Z',
    archived_at: null,
    ...over.asset,
  };
  const attachment: PhotoAttachmentRead = {
    id: `b0000000-0000-4000-8000-${String(seq).padStart(12, '0')}`,
    asset_id: asset.id,
    project_id: PROJECT_ID,
    context: 'ROOM',
    room_id: ROOM_ID,
    surface_id: null,
    opening_id: null,
    category: 'GENERAL',
    caption: null,
    include_in_report: false,
    position: seq,
    archived_at: null,
    created_at: '2026-06-23T08:20:00Z',
    updated_at: '2026-06-23T08:20:00Z',
    ...over.attachment,
  };
  return {
    attachment,
    asset,
    thumbnail_url: over.thumbnail_url === undefined ? `https://r2.example/t/${asset.id}.jpg` : over.thumbnail_url,
  };
}

export function listPage(items: PhotoListItem[], next_cursor: string | null = null, urls_expire_at: string | null = '2099-01-01T00:00:00Z'): PhotoListResponse {
  return { items, next_cursor, urls_expire_at };
}

export function detailFor(item: PhotoListItem, over: Partial<PhotoDetailResponse> = {}): PhotoDetailResponse {
  return {
    asset: item.asset,
    attachments: [item.attachment],
    thumbnail_url: item.thumbnail_url,
    display_url: `https://r2.example/d/${item.asset.id}.jpg`,
    urls_expire_at: '2099-01-01T00:00:00Z',
    ...over,
  };
}

export function storageStatus(over: Partial<PhotoStorageStatus> = {}): PhotoStorageStatus {
  return {
    uploads_enabled: true,
    media_available: true,
    used_bytes: 0,
    warning_bytes: 8_000_000_000,
    soft_cap_bytes: 10_000_000_000,
    state: 'OK',
    ...over,
  };
}
