# Suggestions

## 2026-03-15 — Expose THUMB_WIDTHS from backend API to eliminate cross-stack duplication

**Status:** PENDING

**What:** `THUMB_WIDTHS` is defined as `(400, 1200)` in `backend/app/logic/layout/media.py:15` and duplicated as `[400, 1200]` in `frontend/src/utils/media.ts:18`. Both sides must agree on which thumbnail widths exist — the backend generates them, and the frontend requests them in `srcset` attributes.

**Why:** If either constant changes without updating the other, the frontend silently requests thumbnails at widths the backend doesn't serve (falling back to full-size images — performance regression), or the backend generates thumbnails nobody requests (wasted disk/CPU).

**Proposed fix:** Add a `Literal[400, 1200]` type or enum for the `w` query parameter in the `get_media` endpoint. The openapi-ts code generator will then expose the valid values in the generated client types, and the frontend can derive its `THUMB_WIDTHS` array from the generated type instead of hardcoding it.

**What breaks:** The OpenAPI schema changes (adding an enum constraint to the `w` param). Frontend code that constructs thumb URLs must use the generated type instead of the local constant.

## 2026-03-15 — Align backend/frontend "long description" thresholds to prevent cover duplication

**Status:** PENDING

**What:** The backend (`polarsteps.py:_calculate_visual_length`, `_WIDTH=80`, threshold `1000`) and frontend (`usePageDescription.ts:visualLength`, `CHARS_PER_LINE=65`, `SHORT_THRESHOLD=1200`) independently decide whether a step description is "long." The backend uses this to decide whether the cover photo stays in the photo pages (`builder.py:158-162`). The frontend uses it to decide whether to show the cover image or full-page text on the step page (`StepMainPage.vue:34-47`).

**Why:** The thresholds disagree for descriptions between ~12.5 lines (backend "long" cutoff: 1000/80) and ~18.5 lines (frontend "short" cutoff: 1200/65). In this range, the backend keeps the cover in photo pages (thinking the step page is text-only) while the frontend shows the cover on the step page (thinking the description is short). Result: the cover photo appears twice.

**Proposed fix:** Make the backend the single source of truth. Store `is_long_description` as a boolean field on the `Step` DB model at build time, and have the frontend read it instead of re-computing. Alternatively, align the constants so both sides agree (same line width, same threshold).

**What breaks:** Frontend rendering changes for descriptions in the disagreement range (~12-18 lines). Steps that currently show a cover + short description panel may switch to full-page text layout, or vice versa.
