# Google Photos Original Quality Upgrade

Replace compressed Polarsteps photos with originals from Google Photos for print-quality albums.

## Problem

Polarsteps data exports return compressed photos (960px wide, all EXIF stripped). For a print-ready A4 landscape photo album, these produce low DPI output - often below the 100 DPI caution threshold and sometimes below the 75 DPI warning threshold. The originals likely still exist in the user's Google Photos library.

## Solution

Use the Google Photos Picker API to let users select their trip photos, then automatically match them to the compressed Polarsteps versions using perceptual hashing and replace them with the originals.

## Constraints

- The `photoslibrary.readonly` scope was removed by Google on March 31, 2025. Programmatic library search is impossible. The Picker API (`photospicker.mediaitems.readonly`) is the only path - it requires user-driven selection.
- Polarsteps strips all useful EXIF from exported photos (no timestamps, no GPS, no camera info - verified against fixture data). Matching cannot rely on photo metadata.
- Picker API returns `createTime`, `cameraMake`, `cameraModel`, `filename`, and `baseUrl` per selected item. No GPS. `baseUrl` expires in ~60 minutes.
- Google-authed users only. Microsoft-authed users cannot connect Google Photos.

## User Flow

1. User is in the album editor. An "Upgrade Photos" button appears in the toolbar (next to Export PDF). Only visible for Google-authed users.
2. **First time only:** An onboarding dialog sequence explains what's happening - why photos are compressed, what Google Photos connection does, what the user needs to do in the Picker (search trip dates, select photos), and that originals will replace the compressed versions. Persisted via localStorage so it only shows once. Exact copy and visual design are determined during implementation, but the structure is: a multi-step dismissable dialog shown before the first OAuth consent.
3. User proceeds. If not yet authorized for Google Photos, an OAuth2 consent screen appears for the `photospicker.mediaitems.readonly` scope.
4. Backend creates a Picker session, returns `pickerUri`. Frontend opens it in a new tab with `/autoclose`.
5. User searches their trip dates/location in Google Photos, shift-click selects their trip photos, hits Done. Tab auto-closes.
6. Frontend polls backend, which polls the Picker session. Once `mediaItemsSet` is true, backend retrieves selected media items.
7. Backend runs the matching algorithm. Returns a summary: "Matched 142 of 156 photos. 14 unmatched."
8. User sees the summary in a confirmation dialog. Confirms to proceed.
9. Backend downloads originals, replaces compressed files on disk, regenerates thumbnails, updates Media dimensions in DB. Streams progress via SSE.
10. Frontend refreshes the album view. Quality warnings drop.

## Backend Architecture

### New dependency

- `authlib` - handles OAuth2 authorization code flow with PKCE, state/CSRF, token exchange. The project currently does Google Sign-In via raw OIDC JWT verification, but the Photos Picker needs a full OAuth2 dance (authorize, exchange, refresh) that Authlib handles well.
- `imagehash` - perceptual hashing for photo matching. Pillow is already a dependency.

### New module: `backend/app/services/google_photos.py`

All Google Photos API interaction:
- OAuth2 flow via Authlib (authorize URL generation, code exchange, token refresh)
- Create Picker session, poll session status
- Retrieve selected media items with metadata
- Download media bytes from `baseUrl`

### New module: `backend/app/logic/photo_upgrade.py`

Matching and replacement logic:
- Build time windows from step timestamps
- Compute perceptual hashes of existing Polarsteps photos
- Download thumbnails from Google Photos candidates for hash comparison
- Run bipartite matching algorithm
- Download originals, replace files, update DB

### New routes: `backend/app/api/v1/routes/google_photos.py`

- `GET /google-photos/authorize` - returns the OAuth2 authorization URL (Authlib generates it with PKCE + state)
- `GET /google-photos/callback` - OAuth2 callback, exchanges code for tokens, stores refresh token
- `POST /google-photos/sessions` - creates a Picker session, returns `pickerUri`
- `GET /google-photos/sessions/{id}` - polls session status, returns selected items when ready
- `POST /google-photos/upgrade/{aid}` - SSE endpoint: runs matching, streams progress, downloads and replaces originals
- `DELETE /google-photos/connection` - disconnects Google Photos (nullifies refresh token)

### New config

- `GOOGLE_PHOTOS_CLIENT_SECRET` env var - required for the OAuth2 authorization code flow (separate from the Google Sign-In client ID which is public)

## Frontend Architecture

### New composable: `useGooglePhotos.ts`

- Connection state management (disconnected / connecting / connected)
- Initiates OAuth flow (redirect to backend authorize URL)
- Handles callback (receives authorization code)
- Creates Picker sessions, opens `pickerUri` in new tab
- Polls backend for session completion

### New composable: `usePhotoUpgrade.ts`

- Orchestrates the full upgrade flow: onboarding -> auth -> picker -> matching -> replacement
- Tracks upgrade state and progress via SSE stream
- Exposes match summary for the confirmation dialog

### New components

- `UpgradePhotosButton.vue` - toolbar button, only visible for Google-authed users
- `UpgradeOnboardingDialog.vue` - first-time instructional walkthrough
- `UpgradeMatchSummary.vue` - shows match results with confirm/cancel
- `UpgradeProgress.vue` - SSE-driven progress bar during download and replacement

### Placement

Button lives in `AlbumToolbar.vue`, next to the existing Export PDF button. Uses the same SSE progress pattern as `PdfExportButton.vue`.

## Data Model Changes

### User model - two new nullable columns

- `google_photos_refresh_token: str | None` - Fernet-encrypted refresh token for the Picker API OAuth grant
- `google_photos_connected_at: datetime | None` - when they first connected

The existing `google_sub` field links the user to their Google identity. The refresh token is a separate concern granting Photos Picker access specifically. User can disconnect (nullify token) without affecting login.

### Album model - one new nullable column

- `upgraded_photos: dict[str, str] | None` - maps `media_name -> google_photos_media_id` for replaced photos. Prevents re-downloading on subsequent upgrades and serves as a record of what was changed.

### Migration

One Alembic migration adding the three nullable columns. No data migration needed.

## Matching Algorithm

### Why perceptual hashing

Polarsteps strips all EXIF metadata from exported photos. No timestamps, no GPS, no camera info survive (verified against fixture data - 27 photos checked, zero had DateTimeOriginal, GPS, or camera make/model). Matching must be based on visual content.

### Input

- Album's existing photos on disk (compressed, no EXIF)
- Per-step `start_time` from the DB
- Google Photos selected items with `createTime` and `baseUrl`

### Step 1 - Build time windows

For each step, define a window from its `start_time` to the next step's `start_time` (or +24h for the last step). Assign each Google Photos item to the window(s) its `createTime` falls in. Items near boundaries get assigned to both adjacent windows (30-minute overlap margin for timing imprecision).

### Step 2 - Hash Polarsteps photos

Compute pHash (64-bit perceptual hash via `imagehash`) for each photo in the album. Cache these - they don't change. Stored as `dict[media_name, ImageHash]`.

### Step 3 - Match within time windows

For each step's photos, compare against Google Photos candidates in that step's time window:
- Download a thumbnail from Google Photos (`baseUrl` supports `=w400` size parameter)
- Compute pHash of the thumbnail
- Find the closest Polarsteps photo by Hamming distance
- Accept if distance < 12 bits (out of 64)

### Step 4 - Greedy bipartite matching

Within each step, sort all candidate pairs by Hamming distance ascending. Greedily assign the best unmatched pairs. Prevents one Google Photos item from matching multiple Polarsteps photos.

### Step 5 - Cross-step fallback

Unmatched Polarsteps photos get a second pass against all remaining unmatched Google Photos items (ignoring time windows). Catches photos assigned to a different step than their actual capture time.

### Step 6 - Report

Return: total photos, matched count, unmatched count, per-photo confidence (Hamming distance).

### Performance estimate

Typical trip: ~200 Polarsteps photos, ~300 Google Photos selected. 200 local pHash computations (~50ms each) + ~300 thumbnail downloads (parallelized, ~100ms each). Total: ~30 seconds, streamed via SSE with progress.

## Upgrade Execution (Post-Confirmation)

SSE stream from `POST /google-photos/upgrade/{aid}`:

### Phase: downloading

For each matched pair, download the original from `baseUrl` (full resolution). Bounded concurrency (5 parallel downloads). Progress: `"Downloading 12 of 142"`.

### Phase: replacing

For each downloaded original:
- Verify valid image/video (MIME check)
- Overwrite the compressed file on disk
- Delete stale thumbnails (`.thumbs/` entries)
- Update `Media` entry in album's `media` JSON column with new `width`/`height`
- Progress: `"Replacing 12 of 142"`

### Phase: done

Return final summary. Frontend refreshes album view.

## Error Handling

- **Expired baseUrl:** If >60 min since Picker session, batch fails with clear message. User re-opens Picker. `upgraded_photos` dict tracks what already succeeded - retries skip completed replacements.
- **Individual download failures:** Logged and skipped. Summary reports "3 photos failed to download."
- **Original smaller than compressed:** Skip replacement, report in summary.
- **OAuth token expired:** Auto-refresh via stored refresh token. If refresh fails (user revoked access), prompt re-authorization.

## Security

- **Refresh token encryption:** Fernet symmetric encryption using `SECRET_KEY` as key derivation seed. Encrypted before DB storage, decrypted on read.
- **OAuth state/PKCE:** Handled by Authlib out of the box. State stored in session middleware.
- **Client secret:** `GOOGLE_PHOTOS_CLIENT_SECRET` env var. Never reaches frontend.
- **Scope minimization:** Only `photospicker.mediaitems.readonly` - narrowest possible scope.
- **baseUrl isolation:** Google Photos URLs never exposed to frontend. Backend fetches bytes and writes to disk.

## Idempotency

The `upgraded_photos` dict on the album prevents re-downloading. Running upgrade again after adding more trip photos to Google Photos only processes new matches.
