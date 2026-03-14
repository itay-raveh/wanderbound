# Suggestions

## 2026-03-15 — Expose THUMB_WIDTHS from backend API to eliminate cross-stack duplication

**Status:** PENDING

**What:** `THUMB_WIDTHS` is defined as `(400, 1200)` in `backend/app/logic/layout/media.py:15` and duplicated as `[400, 1200]` in `frontend/src/utils/media.ts:18`. Both sides must agree on which thumbnail widths exist — the backend generates them, and the frontend requests them in `srcset` attributes.

**Why:** If either constant changes without updating the other, the frontend silently requests thumbnails at widths the backend doesn't serve (falling back to full-size images — performance regression), or the backend generates thumbnails nobody requests (wasted disk/CPU).

**Proposed fix:** Add a `Literal[400, 1200]` type or enum for the `w` query parameter in the `get_media` endpoint. The openapi-ts code generator will then expose the valid values in the generated client types, and the frontend can derive its `THUMB_WIDTHS` array from the generated type instead of hardcoding it.

**What breaks:** The OpenAPI schema changes (adding an enum constraint to the `w` param). Frontend code that constructs thumb URLs must use the generated type instead of the local constant.
