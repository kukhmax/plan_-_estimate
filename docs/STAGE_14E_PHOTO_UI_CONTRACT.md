# Stage 14E — reusable mobile photo UI: interface contract (14E.1)

> **Status: ACCEPTED by the owner on 2026-10-06 "по рекомендациям" with three clarifications (C-1 corner button, C-2 photo caption line, C-3 project-level list — §3a); open: D10 (backup cadence); D11 = A (capture source stored, migration `0033`) decided 2026-10-06.** Documentation only: no code, dependency, migration, infrastructure or
> production change. Production photo uploads stay **OFF** (`PHOTO_UPLOADS_ENABLED=false`). Parent stage: canonical
> Stage 14 (photo fixation); this is sub-stage 14E of `docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md` §19. Inputs (not reopened):
> architecture §4/§8/§9/§11/§12/§17, `docs/STAGE_14C_MEDIA_API_CONTRACT.md` (C1–C16, §21 route set), the 14D gate
> (`docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` §17.1, owner-signed 2026-10-06), `CLAUDE.md` (mobile-first rules, field-usage principle).

## 1. Scope

**In 14E:** a reusable photo section (`Zdjęcia (n)`) with picker, upload queue, thumbnail grid, full-screen viewer with metadata
edit and archive; wired into the four supported contexts **PROJECT / ROOM / SURFACE / OPENING**; one small additive backend
endpoint (`GET …/photos/counts`, deferred from 14C as C14); PL/RU texts; tests; deployment with uploads OFF; then the owner's
**first controlled enablement** and device checks.

**Not in 14E (explicit):** inspection / finding evidence (14F), point annotations (14G), WORK execution photos (14H), report
read model (14I), HEIC acceptance (14B.H, owner approval + device evidence first), original download, delete, offline draft
persistence (see D2), any new dependency, any desktop-specific layout.

## 2. Baseline (verified in the repository, 2026-10-06)

| Fact | Consequence for 14E |
|---|---|
| Backend 14C is complete: upload, list, detail, attach, PATCH, archive / restore (attachment and asset), `GET /api/photo-storage`; errors `{"detail": {"code", "message"}}`; **no** `/photos/counts` | one backend addition (§9) |
| Frontend: React 18 + TypeScript strict + Vite + Tailwind + Vitest/RTL (jsdom). **No router, no state library, no icon library, no Playwright**; navigation is component state in `ProjectWorkspace` | no new dependency; icons are inline SVG / text; mobile checks = class assertions in jsdom + owner device checks |
| `apiRequest` (`src/api/http.ts`): `fetch`, JSON, `Authorization: Bearer` from `localStorage['access_token']`, throws `ApiError(status, code, detail)`; it **sets `Content-Type: application/json` whenever a body exists** | uploads need a separate transport (§5); multipart must **not** carry a manual `Content-Type` |
| i18n: `useI18n()` returns the typed dictionary `t` from `locales/pl.json` / `ru.json`; a parity test enforces identical keys | new namespace `photos` in both files, parity kept |
| Theme: Telegram `themeParams` mapped to CSS variables, `data-color-scheme` light/dark; cards use Tailwind utility classes | components use the existing tokens / dark-theme conventions (`darkThemeControls.test.tsx`) |
| Cards (`RoomList`, `SurfaceList`, `OpeningList`) use progressive disclosure: an **Opcje** button reveals an action grid (`aria-label="options-toggle-<id>"`, `min-h-11`) | photo entry points live inside the existing options grids |
| Telegram BackButton: one global hook `useTelegramBackButton(visible, onBack)`; `ProjectWorkspace` owns a priority chain of "what back closes" | the viewer must join that chain (§8, D6); two independent hook instances would both fire |
| No CSP in Caddy / nginx; presigned URLs point to the R2 EU endpoint (cross-origin images) | no `img-src` change today; images get `referrerPolicy="no-referrer"` |

## 3. UX model (mobile first: 320–480 px, acceptance at 390 and 412)

**One reusable `PhotoSection`**, collapsed by default, header `Zdjęcia (n)` / `Фото (n)` (n from counts, §9), expanded **inline** inside
its card (no new screen, no navigation change):

```
┌ Zdjęcia (3)                     ▾ ┐   ← header button, min-h 44 px, full width
│ [ 📷 Zrób zdjęcie ] [ 🖼 Z galerii ]│   ← two full-width-ish buttons (stack at 320 px)
│ ▒▒▒ ▒▒▒ ▒▒▒      (3 per row;       │   ← thumbnail grid (2 per row at ≤ 340 px)
│ ▒▒▒ ▒▒▒          2 at 320 px)     │
│ [ Pokaż więcej ]                   │   ← only when next_cursor
│ Opcje ▾ → Pokaż archiwum           │
└────────────────────────────────────┘
```

**Entry button (owner clarification C-1).** Every card that can hold photos gets a compact **photo button in its upper-right corner** (a camera glyph + the count, e.g. `📷 3`, label `Zdjęcia`), always visible — **not** hidden behind `Opcje`. Geometry: `min-h-11` (≥ 44 px) pill, right-aligned in the card header; where the header already has a right-hand control (surface walls: *Otwory i opcje*; surface ceilings: the total) the photo button goes on the **line directly under it, right-aligned** (as in the owner's mock-up), and at 320 px it wraps below the title instead of squeezing it. Tapping it expands the photo section inline directly under the header (a second tap collapses it). Entry points (never a new top-level screen):

| Context | Where | Target id sent |
|---|---|---|
| PROJECT | `ProjectWorkspace`, object card area (below the summary, above Rooms) — one section "Zdjęcia obiektu" with the corner button; this section lists **all** photos of the object (C-3) | none (context only) |
| ROOM | room card, upper-right corner button | `room_id` |
| SURFACE | surface card (walls and ceiling/floor alike), upper-right corner button | `surface_id` |
| OPENING | opening row, upper-right corner button | `opening_id` |

**Field-usage rules (CLAUDE.md):** capture in **two taps** (open section → `Zrób zdjęcie`); defaults everywhere (category `GENERAL`,
`include_in_report=false`, no caption asked at upload); metadata is edited **after** upload in the viewer; secondary actions
(archive view) hide behind `Opcje`; no modal for the happy path; the queue never blocks the screen (uploads continue while the
user keeps working in the same view).

**Uploads disabled / media unavailable** (`GET /api/photo-storage`, §6): `uploads_enabled=false` → upload buttons hidden, a neutral one-line
note (`Dodawanie zdjęć jest wyłączone`), existing photos stay viewable; `media_available=false` → the section shows the note only. In the
production OFF phase (14E.7 before enablement) the section therefore renders, harmlessly, with no buttons (D5).

### 3a. Photo caption line, project-wide list, evidence data (owner clarifications C-2, C-3)

**C-2 — every photo shows a caption line under its tile** (and in the viewer header): `location → date (time) · source`, e.g.
`Salon → Ściana 1 → 23.06.2026 (10:15) · zrobione w aplikacji`.

| Part | Source | Rules |
|---|---|---|
| **Location path** | built **in the frontend** by the host card from the names it already has: room name (user text) → surface display name (`getSurfaceDisplayName`, the numbering such as "Ściana 1" exists only in the frontend) → opening label. Passed to `PhotoSection` as a `locationLabel`; the project-wide list resolves each attachment's `room_id` / `surface_id` / `opening_id` through the lists already loaded by the workspace | project-level photo: `Obiekt`; a name that cannot be resolved (target archived / not loaded): `—`. **No backend change** (names are not stored with the photo and survive renames) |
| **Date and time** | `asset.captured_at` (EXIF `DateTimeOriginal`, camera-local time, **no timezone** — shown as is) when present, otherwise `asset.uploaded_at` (UTC → converted to the device's local time, marked as *dodano*) | format `DD.MM.YYYY (HH:mm)` in both locales; the viewer shows **both** *Zrobiono* (captured) and *Dodano* (uploaded); if they differ by more than one day the viewer adds a quiet hint "zdjęcie starsze niż data dodania" |
| **Source** | `asset.capture_source` — `CAMERA` ("zrobione w aplikacji") or `GALLERY` ("dodane z galerii"); absent for photos uploaded before the field exists → part omitted | **declared by the client, informational, not proof** (the server cannot verify it; the camera button may fall back to the gallery on some phones) — needs a new nullable column, see **D11** |

**C-3 — the PROJECT-level section lists every photo of the object** (all contexts, `GET …/photos` without `context`), each with its location path, so the
owner can scan the whole object chronologically; room / surface / opening sections list only their own photos. The project-wide list offers the category chips
filter (§7) and groups by day (a sticky date line) when it has more than ~12 items.

**Further recommendations (accepted as proposals, each optional):** a small category badge on the tile (e.g. *Wada*) and a "w raporcie" mark when
`include_in_report` is true (not interactive, so no touch-target issue); category filter chips under `Opcje` using the existing `category` query parameter;
the viewer's two-timestamp view above (evidence integrity); a follow-up sub-stage **14E.8 — offline queue** (IndexedDB drafts, rule E) to be decided after the first
real use on sites with weak signal (basements, reinforced concrete); capture source recorded only as a hint (never as proof).

## 4. Components, hooks and files (14E.3–14E.5)

| File | Responsibility |
|---|---|
| `src/types/photo.ts` | TS mirrors of `PhotoAssetRead`, `PhotoAttachmentRead`, `PhotoListItem/Response`, `PhotoDetailResponse`, `PhotoUploadResponse`, `PhotoStorageStatus`, `PhotoCounts`, enums `PhotoCategory` (8), `PhotoContext` (`PROJECT`\|`ROOM`\|`SURFACE`\|`OPENING` only) |
| `src/api/photos.ts` | `fetchPhotos`, `fetchPhoto`, `fetchPhotoCounts`, `fetchPhotoStorage`, `patchPhotoAttachment`, `archive/restore` (attachment, asset), `attachPhoto`; `uploadPhoto` (XHR, §5). JSON calls go through `apiRequest` |
| `src/utils/photoUploadQueue.ts` | **pure, UI-free** queue state machine (§5) — fully unit-testable |
| `src/hooks/usePhotoStorage.ts` | one shared fetch of `GET /api/photo-storage` per workspace session (+ refetch after an upload batch); exposes `uploadsEnabled`, `mediaAvailable`, `state` (OK/WARNING/FULL) |
| `src/hooks/usePhotoCounts.ts` | counts for the open project (§9), optimistic updates after upload / archive |
| `src/components/PhotoSection.tsx` | header, picker buttons, queue list, grid, archive toggle; props `{projectId, context, targetId?}` |
| `src/components/PhotoPicker.tsx` | the two hidden `<input type="file">` + buttons; validates the selection (§5) |
| `src/components/PhotoUploadQueue.tsx` | per-file row: local preview, progress, state, retry / cancel |
| `src/components/PhotoThumbGrid.tsx` | grid + cursor pagination |
| `src/components/PhotoViewer.tsx` | full-screen sheet (§7) |
| `src/utils/photoCaption.ts` | pure helpers: location path, `DD.MM.YYYY (HH:mm)` formatting (captured vs uploaded), source label — unit-tested in both locales |
| `src/locales/{pl,ru}.json` | namespace `photos` |

Wiring (14E.5) touches `ProjectWorkspace.tsx`, `RoomList.tsx`, `SurfaceList.tsx`, `OpeningList.tsx` minimally (one `<PhotoSection …/>` each + the
back-button context, D6); no behavioural change to existing flows (their test suites must stay green).

## 5. Picker and upload transport

**Picker.** Two buttons, each with a hidden input: *Zrób zdjęcie* — `accept="image/jpeg,image/png,image/webp" capture="environment"`; *Z galerii* —
same `accept`, `multiple`. Per selection at most **10 files** (more → ignore the rest with a note); each file checked locally and *advisorily*:
`size ≤ 25 000 000` (else row `failed: too_large`, no request), MIME in the accepted list (else `failed: unsupported`, no request). **HEIC is not
accepted client-side**: an unsupported MIME shows the unsupported message (the server stays the authority — it decodes, never trusts the MIME). No
client-side resizing or re-encoding in v1: the original bytes are the evidence (D4).

**Identity.** Each queued file gets a stable `upload_id` = `crypto.randomUUID()` (fallback: a v4 built from `crypto.getRandomValues`), generated **once**
at enqueue and reused for every retry of that file (backend idempotency, C9/§12).

**Transport (`uploadPhoto`).** `XMLHttpRequest` (the only way to get upload progress in the Telegram WebView), `multipart/form-data` built with `FormData`
(fields: `upload_id`, `context`, exactly one of `room_id`/`surface_id`/`opening_id`, optional `category`, `caption`, `include_in_report`; **no manual
`Content-Type`**), header `Authorization: Bearer …` from the same token store as `apiRequest`; `xhr.upload.onprogress` drives the bar; response mapped to
the **same `ApiError`** (status, `code`, `detail`) so the UI error table is uniform. `abort()` on cancel. **Idle watchdog:** no progress event for 60 s →
abort (mirrors the server's 60 s idle receive timeout) and run the retry protocol; there is no total timeout (a 25 MB file on a slow link may legitimately
take minutes).

**Queue engine** (`photoUploadQueue.ts`, pure): states `queued → uploading(progress) → processing → done | failed(code, retryable) | canceled`.
**Concurrency 1** (the server processes images one at a time and admits two uploads; one lane per device keeps the phone responsive and the queue
predictable). `processing` = bytes sent, response pending (the server decodes, builds derivatives and stores three objects; allow up to ~60 s). Rules:

1. **Retry protocol (contract §9):** after a network error / timeout / watchdog abort, first `GET /projects/{p}/photos/{upload_id}`; **200** → mark `done`
   (use the returned detail); **404** → re-POST with the same `upload_id` and the same `File`.
2. **App returns to foreground** (`visibilitychange` → visible) or the page regains network (`online`): reconcile every `uploading|processing` item with
   the same GET-first protocol (a WebView may have suspended JS mid-upload).
3. `PHOTO_PROCESSING_BUSY` (503 + `Retry-After`) → auto-retry once after `Retry-After` (cap 30 s), then leave `failed(retryable)`.
4. `PHOTO_UPLOAD_ID_CONFLICT` / `PHOTO_UPLOAD_RESUME_MISMATCH` → generate a **new** `upload_id` only on the user's explicit "retry as new" (never silently).
5. Never drop a failed item silently: it stays in the queue with a message until dismissed or retried; `done` rows collapse into the grid after the list refetch.
6. Local previews use `URL.createObjectURL` (revoked when the item is `done` or dismissed); nothing is persisted in v1 (D2).

**Implementation notes (14E.3, 2026-10-06; refine the rules above, none contradicts them):**

- The error table lives in `src/utils/photoErrors.ts` and the queue engine in `src/utils/photoUploadQueue.ts`; one session-wide queue is exposed by `usePhotoUploadQueue` (extra hook, not in the §4 table).
- *Processing wait:* the idle watchdog covers the sending phase only; after all bytes are sent the transport waits up to **120 s** for the answer (the server needs up to ~60 s), then treats it as a transport failure and
  the GET-first protocol decides. An unreadable 2xx body is also a transport failure.
- *Automatic retries:* after a transport failure whose GET-first check answers 404 the queue re-POSTs the same `upload_id` at most **2** times (2 s, then 4 s); a failed check (offline) is not retried silently. A manual
  *Ponów* resets this budget and keeps the `upload_id`.
- *Foreground reconcile* only ends an in-flight item whose asset already exists on the server (and aborts the dead request); when the server has nothing yet it does nothing — the transport watchdog stays the single
  authority, so there is never a second concurrent POST for one file.
- *Local checks:* an empty `File.type` (some WebViews omit it for camera files) is **not** rejected locally; the server decodes the bytes and never trusts the MIME.
- *Busy:* a `PHOTO_PROCESSING_BUSY` item is re-queued after `Retry-After` (cap 30 s, default 3 s) and does not hold the lane.
- *Unknown availability:* until `GET /photo-storage` answers (or when it fails) uploads are treated as unavailable, so no upload button is shown by mistake.

## 6. Backend errors → UI (single table; PL / RU text keys under `photos.errors.*`)

| Status / `code` | Meaning | UI behaviour | Retry |
|---|---|---|---|
| 401 | session expired | existing auth handling | — |
| 503 `PHOTO_UPLOADS_DISABLED` | gate off | hide upload controls, show the neutral note; queue items → `failed` (not retryable) | no |
| 409 `PHOTO_STORAGE_QUOTA_EXCEEDED` | soft cap | banner "limit miejsca", stop the queue (remaining → `failed` with the same reason) | no (owner action) |
| 413 `PHOTO_TOO_LARGE` (also a Caddy 413) | > 25 MB / request cap | row error with the 25 MB limit | no |
| 415 `PHOTO_UNSUPPORTED_FORMAT` | not JPEG/PNG/WebP (HEIC…) | row error "użyj JPEG, PNG lub WebP" | no |
| 422 `PHOTO_INVALID_IMAGE` / `PHOTO_TOO_MANY_PIXELS` / `PHOTO_ANIMATED_NOT_SUPPORTED` | unusable image | row error | no |
| 422 `PHOTO_UPLOAD_MALFORMED` / `PHOTO_ATTACHMENT_INVALID` | client bug | generic error + log-safe code | no |
| 422 `PHOTO_CONTEXT_NOT_SUPPORTED` | context not allowed | generic error (cannot happen from the UI) | no |
| 404 `PROJECT/ROOM/SURFACE/OPENING_NOT_FOUND` | target gone / not yours | row error "obiekt nie istnieje"; refetch the parent list | no |
| 409 `PHOTO_UPLOAD_ID_CONFLICT`, `PHOTO_UPLOAD_RESUME_MISMATCH`, `PHOTO_OBJECT_CONFLICT` | identity / storage conflict | row error + explicit "retry as new" | on request |
| 503 `PHOTO_PROCESSING_BUSY` | server busy | automatic single retry after `Retry-After` | auto, then manual |
| 503 `PHOTO_STORAGE_UNAVAILABLE`, 500 `PHOTO_STORAGE_ERROR` | storage trouble | row error "spróbuj ponownie później" | manual |
| network error / abort / watchdog | link lost | retry protocol (§5.1) | auto then manual |
| `PHOTO_CURSOR_INVALID` (list) | stale cursor | refetch the first page | auto |
| `PHOTO_ATTACHMENT_NOT_FOUND`, `PHOTO_NOT_FOUND` (viewer) | removed meanwhile | close the viewer, refetch | no |

Messages never echo server text (the backend's English `message` is for logs); the UI maps **codes** to localized strings.

## 7. Grid, viewer, refresh of signed links

**Grid.** `GET /projects/{p}/photos?context=&<target>=&archived=false&limit=30` on first expand (lazy — nothing is fetched while collapsed); cursor
pagination via a *Pokaż więcej* button (no infinite scroll in v1: predictable on a phone). Order is the server's `(position, uploaded_at, id)`.
Thumbnails: `<img loading="lazy" decoding="async" referrerPolicy="no-referrer" alt="…">` in a square `aspect-square` cell, `object-cover`, fixed
size boxes so nothing jumps while loading. Archive view toggle under `Opcje` (`archived=true`), where each tile offers *Przywróć* (`POST …/restore`; a 409 `PHOTO_ATTACHMENT_DUPLICATE` is shown as "już istnieje aktywne zdjęcie").

**Viewer** (full-screen sheet, opened by tapping a tile): loads `GET …/photos/{asset_id}` for the **display** URL (lists carry thumbnails only); shows
the display image (`object-contain`), `captured_at` when present, caption (textarea ≤ 1000, saved on blur / explicit button via PATCH), category
selector (8 values, chips or native `<select>`), toggle **"Uwzględnij w raporcie"** (default off), **Archiwizuj** (confirm; `POST /photo-attachments/{id}/archive` — archives the photo **in this context** only; idempotent; the asset-wide archive is not exposed in 14E),
prev / next between the loaded tiles (buttons ≥ 44 px; swipe is optional polish). **No download, no share, no delete, no original.** Closing: BackButton
and a visible close button; Telegram haptic feedback on success / error where available.

**Signed URLs expire (default 300 s).** The list/detail responses carry `urls_expire_at`. Rules: (a) an `<img>` `onError` → refetch the list page or
the detail **once** and re-render; (b) when the section is expanded and `Date.now()` > `urls_expire_at` on `visibilitychange`/focus → refetch; (c) the
viewer refetches the detail when its URLs are older than `urls_expire_at − 30 s` before showing the next photo. URLs are never written to
`localStorage`, never logged, never put in the query string of app routes.

**Implementation notes (14E.4, 2026-10-06; refine the rules above, none contradicts them):**

- *Files:* `PhotoUploadQueue.tsx` is `PhotoUploadQueueList.tsx` (the name `PhotoUploadQueue` is the engine class); the corner button is its own component `PhotoEntryButton.tsx`; `PhotoSection` renders only the **expanded content** — the host owns the
  expanded flag, shows `PhotoEntryButton` in the card header and mounts `PhotoSection` only while expanded (so nothing is fetched while collapsed).
- *Theme:* every photo component uses the Telegram theme tokens (`var(--tg-theme-…)` / `var(--tg-control-…)`) and no fixed light colours. 14E.5 must check how a section looks inside a host card that has a fixed `bg-white`, in the dark scheme.
- *Counts — one owner:* `PhotoSection` reports only archive / restore corrections (`onCountAdjust`). **An upload completion is counted once by the host** (14E.5: a small hook in the workspace that listens to `subscribePhotoUploadDone` and calls
  `usePhotoCounts().adjust`), because the upload goes on after its section is collapsed and several sections can be open at once.
- *Done rows:* a finished upload row stays until the grid refetch has put the photo into the list, then it disappears; a refetch failure leaves the row with a Dismiss button.
- *Back chain:* the viewer registers through `usePhotoBackRegistration`; the workspace must provide a **stable** registry (memoized) — registration is, in any case, independent of the provider's object identity. A pending caption is saved before the viewer
  closes on Back; a failed save keeps it open.
- *Capture source:* the gallery button declares `GALLERY`; the camera button declares `CAMERA` **only when the picked JPEG carries an EXIF capture time (DateTimeOriginal → DateTimeDigitized → DateTime, read as device-local time) within 5 minutes of now** (a photo taken a moment ago), otherwise `GALLERY` — screenshots, downloads and stripped files have no EXIF and are `GALLERY` (informational, never proof). Reason (14E.7, real phone): Telegram on Android ignores `capture`, opens its gallery picker and hands over a COPY of the file, so neither the button nor the file's modification time says where the photo came from (`readExifCaptureTime` in `utils/jpegExif.ts`, `isFreshCapture` in `PhotoPicker.tsx`; the first attempt, by file modification time, still labelled a month-old picture `CAMERA`). A real in-app camera (`getUserMedia`) is a separate follow-up (spike first).

## 8. Back navigation (Telegram BackButton)

`ProjectWorkspace` owns the only registered BackButton handler and its priority chain. The viewer (and its unsaved-caption guard) must be the **first**
branch of that chain. **Recommended (D6):** a small React context provided by `ProjectWorkspace`, `PhotoBackContext { register(close: () => void): () => void }`;
`PhotoViewer` registers its `close` while open; the workspace's handler calls the registered closer first. This adds one branch and does not refactor the
existing hook or chain. (Rejected: a second `useTelegramBackButton` instance — both click handlers would fire; a global stack hook — a refactor of a working
module not needed for 14E.)

**Implementation notes (14E.5, 2026-10-06; refine the rules above, none contradicts them):**

- *Wiring pattern:* `ProjectWorkspace` mounts one `ProjectPhotosProvider`; a card adds `PhotoCardButton` (header) and `PhotoCardPanel` (under the header). Outside the provider both render nothing, so the existing suites needed no change.
- *Back chain:* the workspace's Telegram Back handler first calls `closeTop()` of the viewer registry; only when no viewer is open does the previous chain run unchanged. An open viewer with an unsaved caption saves it, then closes.
- *Object card:* a separate "Zdjęcia obiektu" card (fixed white like `project-detail`) between the estimates entry and the rooms; its button shows the **total** of every photo of the object, matching the project-wide list (C-3).
- *Names for paths:* a photo stores only its leaf target and the wall numbering exists only in the frontend, so the project-wide list loads the structure names lazily when it opens (rooms; surfaces of all rooms if any surface or opening has photos;
  openings of walls only if any opening has photos; ≤ 6 parallel requests). A name that cannot be loaded or resolved shows a dash. Leaf cards (room, surface, opening) build the path from the names they already hold.
- *Counts:* the provider counts finished uploads once; the section reports only archive / restore corrections; counts are refetched whenever a section expands and when an upload finds its target gone.

**Implementation notes (14E.6, 2026-10-06; found in a real Chromium at 320 / 390 / 412 px; they refine §3 and §7):**

- *Grid:* **2 columns up to 479 px, 3 from 480 px** (earlier text: "3 per row, 2 at ≤ 340 px"). The grid sits inside a padded card and a padded section, so 3 columns left ~85 px per tile — too narrow for the caption line and the badge.
- *Viewer placement:* the viewer is rendered through a **portal into `document.body`** so that it covers the whole screen regardless of the host card's spacing, stacking context or clipping.
- *Check on an unreachable server:* the GET-first check of the queue keeps the original transport failure ("no connection", retryable) when it gets no HTTP answer at all.

**Model change after the owner's first browser check (14E.6, 2026-10-06) — this SUPERSEDES the entry-point table of §3, C-1 and the D9 placement where they differ:**

- Photos are **added only on surfaces**: wall cards (*Ściana 1…N*), the **floor** card and the **ceiling** card (a floor / ceiling photo goes to the canonical plane surface, `SURFACE` context). The object card, the room cards, the room view and the opening rows have **no picker**.
  Opening rows have **no photo button at all** (photos of a door / window are taken on its wall; path in the caption shows the wall). The backend still accepts all four contexts; the UI offers only `SURFACE`.
- The **object card** ("Zdjęcia obiektu") and **each room** (the room card on the object tab and a new "Zdjęcia pomieszczenia" card in the room view) are **aggregated lists for viewing and editing only** (caption, category, report flag, archive / restore, archive view, category chips, day grouping):
  the object lists every photo of the object, a room lists every photo of the room — its own, those of its surfaces and of their openings — each with its full path (`room → surface → opening → date (time) · source`).
  Photos attached earlier directly to an object, a room or an opening (before this change) stay visible and editable there.
- The number on a room button is the room's **total** (`room_totals`), so the card on the object tab and the room view always agree; a surface button shows the surface's own photos; the object button shows every photo.
- Backend (additive, no migration): `counts.room_totals` and the `in_room_id` list filter (see `STAGE_14C_MEDIA_API_CONTRACT.md` §21).
- After an upload finishes or a photo is archived / restored, the badges are corrected at once and then **confirmed by a refetch of the counts** (a room's total spans surfaces and openings, which the client cannot always attribute).

## 9. Backend addition — `GET /api/projects/{project_id}/photos/counts` (14E.2)

Additive, read-only (the endpoint itself needs no migration; the separate capture-source column of D11 = A is migration `0033`), owner-scoped (foreign / missing project → 404 `PROJECT_NOT_FOUND`), available with uploads disabled (C11).

```json
{ "project": 4, "rooms": {"<room_id>": 2}, "surfaces": {"<surface_id>": 1}, "openings": {"<opening_id>": 1} }
```

Counts **active attachments** whose asset is READY and not archived, in this project, grouped by target; targets with zero photos are omitted (response
size is bounded by the number of photographed targets). One request per workspace load; the UI adjusts counts optimistically after upload / archive /
restore and refetches on section expand. Tests: ownership (cross-user 404), READY only (PENDING / FAILED never counted), archived attachment / asset not
counted, grouping per context, empty project → zeros, uploads-disabled still 200, query count constant (one aggregate per context group).

## 10. i18n (PL default, RU secondary) and layout rules

Namespace `photos` in `pl.json` and `ru.json` (parity test must pass). Key groups: `section.*` (title, count, empty, options, show_archive, show_more),
`picker.*` (take_photo, from_gallery, too_many_selected), `queue.*` (waiting, uploading, processing, done, retry, retry_as_new, cancel, dismiss),
`viewer.*` (caption, category, include_in_report, archive, restore, close, previous, next, saved), `category.*` (8), `errors.*` (§6), `storage.*`
(disabled note, warning, full). Draft category labels — GENERAL *Ogólne / Общее*, BEFORE *Przed / До*, DEFECT *Wada / Дефект*, PREPARATION *Przygotowanie /
Подготовка*, IN_PROGRESS *W trakcie / В процессе*, HIDDEN_WORK *Roboty zanikające / Скрытые работы*, AFTER *Po / После*, DAMAGE *Uszkodzenie / Повреждение*.
No prices, legal text or hardcoded user-facing strings in components (rules A–C). Russian strings are longer: every button / chip must wrap or stack
(`break-words`, `min-w-0`, flex-wrap; icon-only controls only for close / prev / next with `aria-label`).

## 11. Mobile acceptance matrix (every UI sub-stage)

| Check | How |
|---|---|
| 320 / 390 / 412 px, **no horizontal scroll**, nothing clipped | owner manual (390, 412) + jsdom class assertions (no fixed widths, `min-w-0`, wrapping, `grid-cols-2`→`3`) |
| Touch targets ≥ 44 px for primary controls (picker buttons, header, viewer actions, prev / next, close) | class assertion `min-h-11` / `min-w-11` + owner |
| PL and RU, long labels / long captions / long error strings wrap safely | tests render both locales; owner checks RU |
| Light and dark (Telegram `data-color-scheme`) | tests with `data-color-scheme="dark"`; owner checks both |
| Buttons never collide with long names; vertical stacking preferred | owner |
| BackButton closes the viewer first, then the previous layer | test of the back chain + owner in Telegram |
| Existing suites unchanged (rooms, surfaces, openings, workspace, estimates, inspections) | full vitest + `tsc --noEmit` + `vite build` |

## 12. Device checks (owner-run, recorded in 14E.7 — these cannot be proved in jsdom)

(1) camera and gallery pickers in Telegram on **iOS and Android** (does `capture` open the camera; multi-select from the gallery); (2) **what format arrives**
(JPEG vs HEIC) — decides whether HEIC work (14B.H) is reopened; (3) presigned thumbnail / display images render inside the Telegram WebView (R2 EU
endpoint, cross-origin, no CSP); (4) a 5–12 MB photo over mobile data **through Cloudflare** (body limit / time-out; progress bar behaviour); (5) the
Mini App sent to the background during an upload, then restored (reconcile protocol §5.2); (6) memory / scroll smoothness with ~30 thumbnails; (7) the BackButton
behaviour with the viewer open; (8) PL and RU on a real phone, light and dark.

## 13. Sub-stages, tests and PASS

| Sub-stage | Deliverable | Tests / PASS |
|---|---|---|
| **14E.1** (this document) | contract | owner approval (decisions D1–D10) |
| **14E.2** | backend `GET …/photos/counts` (§9); **if D11 = A:** additive nullable column `photo_assets.capture_source` (migration `0033`, reversible, CHECK in (`CAMERA`,`GALLERY`)), optional multipart field `source` (field cap 6 → 7), returned in `PhotoAssetRead`, ignored on replay (C16), + schema + service + tests | focused pytest, full backend, ruff, mypy, Alembic upgrade / downgrade on scratch PostgreSQL 16; **no migration if D11 = C** |
| **14E.3** | `types/photo.ts`, `api/photos.ts` (incl. XHR upload), `photoUploadQueue.ts`, hooks, `photos` locale keys | vitest unit (queue state machine incl. GET-first retry, watchdog, foreground reconcile, error mapping, FormData shape without `Content-Type`), parity test, `tsc` |
| **14E.4** | `PhotoPicker`, `PhotoUploadQueue`, `PhotoThumbGrid`, `PhotoViewer`, `PhotoSection` | RTL tests per component (states, both locales, dark, 320-px class assertions, touch-target classes, a11y labels), `tsc`, build |
| **14E.5** | wiring into Project / Room / Surface / Opening + back context + counts | existing suites unchanged; new integration tests (entry present per context, counts update after upload, uploads-off rendering, back chain) |
| **14E.6** | full verification, owner browser check at 390 / 412 (D-DEV), owner acceptance, one commit | full vitest, `tsc`, `vite build`, full backend; mobile matrix §11 |
| **14E.7** | deployment **with uploads OFF** (backend with counts, frontend build; no migration); then, only on the owner's explicit approval, the controlled enablement | §14 |

Each sub-stage follows the normal workflow (verification → owner acceptance → commit → push / deploy only on explicit approval) and includes mobile regression.

## 14. First controlled enablement (14E.7, owner-run; nothing here happens before the owner says yes)

Preconditions: 14D.7 signed ✓ (2026-10-06); the owner's decision on backup cadence / RPO (**D10**); a **fresh backup run** immediately before; the OFF-phase
deployment verified. Steps: (1) set `PHOTO_UPLOADS_ENABLED=true` in `.env.production`, recreate **only** the backend container; (2) from a real phone: one upload
per context (project, room, surface, opening), check list / viewer / archive / restore; (3) R2 inventory shows 3 objects per photo, `GET /api/photo-storage` shows
`uploads_enabled=true`; (4) run the **integrity check** and a **second backup run** — this is the first backup with `ready_count > 0`, i.e. the first proof of the media
path on production data (the drill proved it on synthetic data); verify and restore-compare as in 14D.6; (5) device checks §12. **Rollback:** set the flag back to
`false` and recreate the backend (photos stay stored and viewable; nothing is deleted). Record results in `docs/development-progress.md`.

## 15. Decisions for the owner (recommended defaults first)

| # | Question | Recommendation |
|---|---|---|
| D1 | Counts endpoint shape (§9) | one aggregate response per project (as specified) |
| D2 | Upload queue persistence | **in-memory only in v1** (survives navigation inside the Mini App, not a WebView restart); IndexedDB drafts (rule E) stay a follow-up with the queue interface already isolated in `photoUploadQueue.ts` |
| D3 | Picker | two buttons (camera, gallery) — fewest taps on site |
| D4 | Client-side resize / re-encode | **none** (originals are evidence; server derives display / thumbnail) |
| D5 | Behaviour while uploads are OFF | section renders without buttons plus a neutral note; existing photos viewable |
| D6 | Back-button integration | `PhotoBackContext` (§8), viewer first in the chain |
| D7 | Category / caption at upload | not asked at upload; edited in the viewer; default `GENERAL` |
| D8 | Max files per selection | 10 |
| D9 | Where the project-level section sits | object card, below the summary, above Rooms |
| **D-DEV** (accepted: option 1) | How the owner checks the UI before production (the repo forbids local Docker and `MEDIA_STORAGE_BACKEND` has no local-file mode; the in-memory fake produces URLs a browser cannot load) | **(1) a separate dev R2 bucket + its own scoped token** created by the owner, local backend with `MEDIA_STORAGE_BACKEND=s3`, `PHOTO_UPLOADS_ENABLED=true` in a local-only env file (no code, no production contact); alternatives: (2) skip dev E2E and rely on the controlled production enablement; (3) a dev-only local-filesystem adapter (new backend code) |
| **D10** | Backup cadence / RPO before enablement | decide before 14E.7: manual before each work session, a nightly timer with N copies, or manual first and a timer later — **OPEN** |
| **D11** (**DECIDED 2026-10-06: A**) | Capture source ("zrobione w aplikacji" / "dodane z galerii") — C-2 | **A (recommended): store it** as an informational column `photo_assets.capture_source` (adds Alembic migration `0033`; the production backup / restore tooling is unaffected — it resolves the head from the repository); **C: do not store it** — omit the source part, the line shows location + date/time only (no migration, 14E stays migration-free as in architecture §19); **B (rejected): derive it from EXIF presence** — a gallery photo taken yesterday also has EXIF, so the label would mislead — **DECIDED: A** (implemented in 14E.2) |
| D12 | Project-level list shows all photos of the object with path labels (C-3) | accepted |

## 16. Risks

Telegram WebView quirks with `capture` / multi-select / suspended JS during uploads (mitigated by the reconcile protocol; verified in §12); Cloudflare body
limit or time-outs on mobile networks (device check 4; Caddy cap is 27 MB, server idle timeout 60 s); HEIC arriving from iPhones (server rejects with 415 → clear
message; a decision point, not a defect); signed-URL expiry while a screen stays open (§7 rules); memory with many thumbnails (lazy loading, pagination 30); the
single-lane queue is slower than parallel (accepted: predictable, protects the 1-OCPU server); BackButton interplay (§8).

## 17. Owner approval record

**Accepted by the owner on 2026-10-06** ("принимаю 14E.1 по рекомендациям, но есть уточнения": corner button C-1, caption line C-2, project-wide list C-3 — §3a). Decisions D1–D9 and D12 accepted as recommended; D-DEV = option 1 (a separate dev R2 bucket and token created by the owner); **D11 = A decided 2026-10-06; open: D10**. Approving 14E.1 meant: the scope (§1), the UX model (§3), the transport / queue rules (§5), the error mapping (§6), the counts endpoint (§9) and
the decisions D1–D10 (with the recommended defaults unless the owner changes them). Next sub-stage: **14E.2** (backend: counts endpoint and, per D11, the capture-source column) — started after the owner answered D11 = A (implemented 2026-10-06, see `docs/development-progress.md`).

**14E.6 accepted by the owner on 2026-10-06** ("принимаю 14E.6") after the browser check, with the model change recorded above the §9 notes (photos are added only on surfaces; the object and the rooms are view / edit lists). Next: **14E.7** — only on the owner's explicit go-ahead and after D10.
