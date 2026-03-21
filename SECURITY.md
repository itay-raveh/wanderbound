# Security Overhaul Plan

Comprehensive, severity-ordered plan for hardening the Polarsteps Album Generator
for public deployment on a cloud VM. Every item is numbered. Items are grouped by
severity and ordered within each group by blast radius and ease of exploitation.

Goal: withstand automated scanners, bots, and casual attackers ("script kiddies")
without needing enterprise infrastructure.

---

## CRITICAL

### 1. ~~Authentication: signed, expiring session cookie~~ DONE

**Implemented:** Replaced the raw-integer cookie with Google OAuth2 +
Starlette `SessionMiddleware`. The session cookie is now:

- **Signed** via `itsdangerous.TimestampSigner` (Starlette's SessionMiddleware
  uses `SECRET_KEY` to sign the cookie payload).
- **Expires** after 30 days (`max_age=30 * 86400`).
- **httponly, SameSite=lax** — set by SessionMiddleware.
- **Secure** in non-local environments (`https_only=settings.ENVIRONMENT != "local"`).
- **Generic name** (`"session"`) — does not leak implementation details.
- **No PII stored** — only `{"uid": <int>}` in the signed cookie payload.

Authentication flow:
1. User signs in with Google (client-side Google Identity Services).
2. Backend verifies the Google JWT via `pyjwt` + Google's JWKS endpoint.
3. Existing user: sets `request.session["uid"]` → signed cookie returned.
4. New user: returns `null`, frontend holds credential in `sessionStorage`.
5. Upload: re-verifies JWT at upload time, creates user atomically.

Session fixation prevention: `request.session.clear()` is called before
setting `uid` in both `auth.py` and `users.py`.

**Files:** `main.py` (SessionMiddleware), `deps.py` (reads `request.session`),
`auth.py` (Google JWT verification + session creation), `users.py` (upload +
session creation for new users).

---

### 2. ~~Upload size limit~~ DONE

**Implemented:** Upload size limit enforced at three layers, configurable via
`VITE_MAX_UPLOAD_GB` env var (default: 4). Single source of truth in `.env`.

1. **Frontend** — Quasar `q-uploader` rejects files exceeding the limit before
   upload starts (`max-file-size` prop). User sees a localized "file too large"
   toast with the configured limit.
2. **Nginx** — `client_max_body_size 4g` rejects oversized requests with 413
   before any bytes reach the backend. `client_body_timeout 300s` kills
   slow-upload (Slowloris-style) connections.
3. **Backend** — `_check_upload_size()` in `users.py` verifies actual file
   size via seek before extraction begins (defense-in-depth).

**Files:** `.env` (`VITE_MAX_UPLOAD_GB`), `config.py` (Settings field),
`upload.py` (`MAX_UPLOAD_BYTES` derived from settings), `users.py` (size check),
`ZipUploader.vue` (frontend limit), `nginx.conf` (network limit),
`Dockerfile` + `compose.yml` (build arg passthrough).

Storage protection is handled separately by item #13 (per-user storage quota)
and item #3 (rate limiting) — not by the upload size limit.

---

### 3. ~~Rate limiting: nginx~~ DONE

**Implemented:** Nginx rate limiting with two per-IP zones:

- **`uploads` zone** (1 req/min, burst 2) — applied to
  `location = /api/v1/users/upload`. Prevents upload abuse (ZIP extraction,
  disk writes, ffprobe/ffmpeg/Pillow processing are expensive).
- **`general` zone** (10 req/s, burst 30) — applied to `location /api/`.
  Blocks automated floods before they reach Python.

Both zones return **429** when the limit is exceeded. Static assets
(`/assets/`, `/`) have no rate limit.

Also added `X-Forwarded-For` and `X-Forwarded-Proto` proxy headers
(completes the nginx side of item #8).

**Files:** `frontend/nginx/nginx.conf`

---

## HIGH

### 4. ~~Nginx security headers~~ DONE

**Implemented:** All security headers in a shared `security-headers.conf`
snippet, included at server level (inherited by API locations) and explicitly
in `/assets/` and `/` locations (which have their own `add_header`, overriding
nginx's inheritance).

Headers:
- `server_tokens off` — hides nginx version
- `X-Content-Type-Options: nosniff` — prevents MIME sniffing
- `X-Frame-Options: DENY` — prevents clickjacking
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy` — disables camera, microphone, geolocation
- `Content-Security-Policy` — whitelists only required external resources:
  Google Sign-In (script, frame, connect, img), Mapbox (tiles, API, workers,
  RTL text plugin), flagcdn (country flag images)

**Files:** `frontend/nginx/security-headers.conf`, `frontend/nginx/nginx.conf`,
`frontend/Dockerfile`

---

### 5. ~~Containers run as root~~ DONE

**Implemented:**

**Backend** — `appuser` (non-root) created after Playwright install (which
needs root for system packages). `PLAYWRIGHT_BROWSERS_PATH=/app/browsers`
ensures the browser binary is accessible to the non-root user. Data directory
(`/app/backend/data`) owned by `appuser`. Chromium launched with `--no-sandbox`
since the container itself is the sandbox (item #28).

**Frontend** — Entire nginx process runs as the `nginx` user (non-root).
Switched from port 80 to 8080 (non-root can't bind privileged ports).
Writable directories (`/var/cache/nginx`, `/var/log/nginx`, `/run`) owned
by `nginx`.

Note: If upgrading from a previous deployment, the `app-data` Docker volume
may still be owned by root. Fix with:
`docker compose exec backend chown -R appuser:appuser /app/backend/data`

**Files:** `backend/Dockerfile`, `frontend/Dockerfile`,
`frontend/nginx/nginx.conf` (port 8080), `compose.override.yml` (dev port),
`backend/app/main.py` (`--no-sandbox`)

---

### 6. ~~MIME type validation on upload~~ DONE

**Implemented:** Two-layer magic byte validation using `puremagic` (pure Python,
no system dependencies):

1. **Before extraction** — first 2048 bytes checked against
   `{"application/zip", "application/x-zip-compressed"}`. Rejects non-ZIP
   uploads before any disk I/O.
2. **After extraction** — every extracted file checked against
   `{"image/jpeg", "video/mp4", "application/json", "text/plain"}`. Rejects
   ZIPs containing executables, scripts, HTML, or other unexpected types.

Used `puremagic` instead of `python-magic` — zero system dependencies (no
`libmagic1` needed), pure Python, actively maintained.

**File:** `backend/app/logic/upload.py`

---

### 7. ~~Docker Compose: security_opt, cap_drop, resource limits~~ DONE

**Implemented:** All four services hardened in `compose.yml`:

- **`no-new-privileges:true`** on all services — blocks setuid-based privilege
  escalation.
- **`cap_drop: [ALL]`** on all services — zero default Linux capabilities.
  Only `db` gets `cap_add: [CHOWN, FOWNER, SETGID, SETUID]` (needed by
  postgres entrypoint for `chown`/`gosu`). Backend, frontend, and prestart
  need zero capabilities.
- **`read_only: true`** on all services — immutable root filesystem. Writable
  paths via `tmpfs` (`/tmp`, `/var/run/postgresql`, `/var/cache/nginx`) and
  existing named volumes (`app-data`, `db-data`).
- **Resource limits** — memory and CPU per service via `deploy.resources.limits`.
- **`pids_limit`** — fork bomb protection per service.
- **`shm_size: 256m`** on backend — Chromium needs shared memory for rendering
  (Docker default 64MB is too small).
- **`init: true`** on backend — proper zombie process reaping for ffmpeg and
  Chromium subprocesses.
- **nginx tmpfs** uses `uid=101,gid=101` so the non-root `nginx` user can write
  to cache/run directories.

**File:** `compose.yml`

---

### 8. ~~Proxy headers for real client IP~~ DONE

**Implemented:**

- Uvicorn: `--proxy-headers` flag in both `Dockerfile` and `compose.override.yml`.
- Nginx: `X-Forwarded-For` (`$proxy_add_x_forwarded_for`) and `X-Forwarded-Proto`
  (`$scheme`) headers in both API location blocks (added as part of item #3).

**Remaining consideration:** `--forwarded-allow-ips='*'` on uvicorn (or the
specific proxy IP) to trust the forwarded headers. Within Docker Compose, the
nginx container's IP is dynamic, so `'*'` is acceptable since nginx is the
only upstream. Without this, uvicorn ignores the forwarded headers.

---

### 9. ~~SECRET_KEY with environment validation~~ PARTIALLY DONE

**Done:** `SECRET_KEY: str` is a required field in `config.py` (no default —
startup fails if missing). Used by Starlette `SessionMiddleware` to sign
session cookies. `.env.example` documents the field with a generation command.

**Remaining:** Add a `model_validator` to `Settings` that rejects weak values
in production:

```python
@model_validator(mode="after")
def _validate_secrets(self) -> Self:
    if self.ENVIRONMENT == "production":
        weak = {"changethis", "secret", "password", ""}
        if self.SECRET_KEY in weak or len(self.SECRET_KEY) < 32:
            raise ValueError(
                "SECRET_KEY must be a random string of at least 32 characters "
                "in production. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if self.POSTGRES_PASSWORD in weak:
            raise ValueError("POSTGRES_PASSWORD is too weak for production")
    return self
```

---

## MEDIUM

### 10. ~~Network segmentation in Docker Compose~~ DONE

**Implemented:** Two custom networks replace the default shared bridge:

- **`backend`** (`internal: true`) — db, prestart, backend. No outbound internet
  access from this network. Isolates the database from the frontend.
- **`frontend`** — backend, frontend. Provides outbound internet access (needed
  by backend for Google JWKS, Open-Meteo API, cover photo downloads).

The backend bridges both networks: it can reach the database on the `backend`
network and serve requests from nginx on the `frontend` network. The frontend
cannot reach the database directly.

**File:** `compose.yml`

---

### 11. ~~Bind development ports to localhost~~ DONE

**Implemented:** All dev ports in `compose.override.yml` prefixed with
`127.0.0.1:` — `5432`, `8000`, `5173` are only accessible from localhost.
Docker port mappings bypass host firewalls, so this prevents exposure on
shared networks.

**File:** `compose.override.yml`

---

### 12. ~~Read-only container filesystems~~ DONE

**Implemented** as part of item #7. All services have `read_only: true` with
tmpfs mounts for writable paths (`/tmp`, `/var/run/postgresql`,
`/var/cache/nginx`, `/var/run`) and named volumes for persistent data
(`app-data`, `db-data`).

**File:** `compose.yml`

---

### 13. ~~Per-user storage quota~~ NOT NEEDED

**Analysis:** Each upload replaces the user's entire data folder
(`shutil.rmtree` + `rename` in `upload_data`). Storage cannot accumulate
per-user — a user's disk usage is bounded by a single Polarsteps export.
Temp directories are cleaned up on failure. Per-user quotas add complexity
with no security benefit given this design.

---

### 14. ~~Validate extracted file types after ZIP extraction~~ DONE

Implemented as part of item #6. `_safe_extract()` now checks MIME types of
every file inside the ZIP against an allowlist (`image/jpeg`, `video/mp4`,
`application/json`, `text/plain`) using `puremagic` magic bytes during a
single-pass validate-and-extract. Symlinks are also rejected during extraction.

**File:** `backend/app/logic/upload.py`

---

### 15. Weak default database password

**Current state:** `.env.example:30` has `POSTGRES_PASSWORD=postgres`. The actual
`.env` (not in git, but on disk) also uses `POSTGRES_PASSWORD=postgres`.

**Problem:** While the DB is not exposed to the internet in production compose
(no port mapping), this is still a weak credential. If network segmentation is
incomplete, or if the compose config is accidentally modified, the DB is wide
open.

**Fix:**

1. Change `.env.example` to:
   ```
   POSTGRES_PASSWORD=changethis
   ```
2. Add validation in `Settings._validate_secrets` (item #9) that rejects weak
   DB passwords in production.
3. In the actual `.env`, generate a random password:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(24))"
   ```

---

### 16. CORS methods and headers too broad

**Current state:** `main.py:54-55` sets `allow_methods=["*"]` and
`allow_headers=["*"]`.

**Problem:** While this is common in single-frontend setups, it allows methods
like `CONNECT`, `TRACE`, `OPTIONS` to non-preflight requests from the listed
origins. Automated scanners flag this.

**Fix:**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
```

---

### 17. Cookie `path` scope too broad

**Current state:** Starlette `SessionMiddleware` sets the `session` cookie
with no `path` parameter, defaulting to `/` — sent on every request including
static asset requests to nginx.

**Fix:** Starlette's `SessionMiddleware` does not support a `path` parameter
natively. Options:
1. Accept the `/` default — the cookie is small (signed JSON with only `uid`)
   and the overhead is negligible.
2. Subclass `SessionMiddleware` to add `path="/api"` — adds complexity for
   minimal gain.

Given the cookie contains no PII and is small, this is low priority.

---

### 18. ~~PDF temp files not cleaned up on server restart~~ DONE

PDF temp files are now written to a dedicated `/tmp/polarsteps-pdf/` directory,
cleaned up on server startup via `cleanup_pdf_tmp()`. Individual files are
deleted after download (via `BackgroundTasks`) or after 60s TTL expiry.
The PDF pipeline never holds the full merged PDF in Python memory — chunks are
rendered directly to disk by Playwright, then merged by `qpdf` (C++) on disk.
`pypdf` dependency removed.

---

## LOW

### 19. HTTPS termination

**Current state:** Nginx listens on port 80 only. No TLS. No redirect from
HTTP to HTTPS.

**Problem:** All traffic (including the session cookie, user data, uploaded
files) is transmitted in plaintext. The `secure` cookie flag (item #1) won't
work without HTTPS. Cloud VMs are often on shared networks where traffic
sniffing is possible.

**Fix (choose one):**

- **Option A: Cloud load balancer** — if deploying to AWS/GCP/Azure, use their
  managed load balancer with a free TLS certificate. Nginx stays on port 80
  internally. The load balancer handles TLS and forwards to nginx.
- **Option B: Certbot + nginx** — install certbot, obtain a Let's Encrypt
  certificate, configure nginx to serve on 443 with the cert and redirect 80→443.
- **Option C: Traefik** — replace nginx with Traefik as the reverse proxy.
  Traefik auto-provisions Let's Encrypt certificates. This is what the FastAPI
  full-stack template uses.

Add `Strict-Transport-Security` header (already in item #4) only after HTTPS
is working.

---

### 20. Ruff security rules (flake8-bandit)

**Current state:** `pyproject.toml` already selects `ALL` rules for Ruff, which
includes the `S` (flake8-bandit) prefix. These rules ARE already active. However,
there is no CI enforcement or pre-commit hook ensuring they stay passing.

**Fix:**

1. Verify current compliance — run `ruff check --select S backend/app/` and fix
   any findings.
2. Add `ruff check` to CI (GitHub Actions) so security regressions block merges.
3. Consider adding a pre-commit hook:
   ```yaml
   # .pre-commit-config.yaml
   - repo: https://github.com/astral-sh/ruff-pre-commit
     rev: v0.11.0
     hooks:
       - id: ruff
         args: [--fix]
       - id: ruff-format
   ```

---

### 21. Dependency vulnerability scanning

**Current state:** No automated scanning for known CVEs in Python or JavaScript
dependencies. `dependabot.yml` may exist in `.github/` but no CI job runs
`pip-audit` or `npm audit`.

**Problem:** Vulnerable dependencies (especially `python-multipart`, `Pillow`,
`playwright`, `uvicorn`) could have known exploits that are trivially scriptable.

**Fix:**

1. **Python** — add `pip-audit` to dev dependencies and CI:
   ```bash
   uv run pip-audit
   ```

2. **JavaScript** — add to CI:
   ```bash
   cd frontend && bun audit
   ```
   (Or `npx audit-ci --critical` for a CI-friendly wrapper.)

3. **Docker images** — add Trivy scanning to CI:
   ```bash
   trivy image --severity HIGH,CRITICAL --exit-code 1 backend:latest
   trivy image --severity HIGH,CRITICAL --exit-code 1 frontend:latest
   ```

4. **GitHub Dependabot** — ensure `.github/dependabot.yml` covers both `pip`
   (uv) and `npm` (bun) ecosystems.

---

### 22. Semgrep static analysis

**Current state:** No SAST tool beyond Ruff's S rules.

**Fix:** Add Semgrep to CI for deeper, framework-aware analysis:

```yaml
# .github/workflows/security.yml
- name: Semgrep SAST
  uses: semgrep/semgrep-action@v1
  with:
    config: >
      p/python
      p/owasp-top-ten
```

Semgrep understands FastAPI's dependency injection, Pydantic model validation,
and SQLAlchemy query patterns — it catches things Ruff/Bandit miss.

---

### 23. Docker image scanning with Trivy

**Current state:** No container image scanning.

**Fix:** Add to CI:

```yaml
- name: Build backend image
  run: docker build -t backend:${{ github.sha }} -f backend/Dockerfile .

- name: Trivy scan backend
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: backend:${{ github.sha }}
    severity: CRITICAL,HIGH
    exit-code: 1

- name: Trivy scan Dockerfiles
  uses: aquasecurity/trivy-action@master
  with:
    scan-type: config
    scan-ref: .
    severity: CRITICAL,HIGH
```

Also run locally during development:
```bash
trivy config backend/Dockerfile
trivy config frontend/Dockerfile
trivy config compose.yml
```

---

### 24. Timestamp validation on ffmpeg extract_frame

**Current state:** `media.py:132` accepts `timestamp: float` from the user via
query parameter and passes it to ffmpeg as `-ss str(timestamp)`. While
`create_subprocess_exec` prevents shell injection, there's no validation of the
float value.

**Problem:** `NaN`, `inf`, `-inf`, or very large negative values could cause
ffmpeg to hang or behave unexpectedly.

**Fix:**

```python
@router.patch("/{aid}/media/{name}")
async def update_video_frame(
    aid: str, name: MediaName, user: UserDep,
    timestamp: Annotated[float, Query(ge=0, le=86400)],
) -> None:
    ...
```

This uses FastAPI's built-in validation to reject values outside 0–86400 seconds
(24 hours — no video is longer than that in a Polarsteps export).

---

### 25. Error response information leakage

**Current state:** The `NoResultFound` exception handler in `main.py:73` returns
a generic "Not Found". However, unhandled exceptions produce FastAPI's default
500 response which includes the exception type and message.

**Fix:** Add a catch-all exception handler for production:

```python
if settings.ENVIRONMENT == "production":
    @app.exception_handler(Exception)
    async def _generic_error(_request: Request, exc: Exception) -> PlainTextResponse:
        logger.exception("Unhandled exception")
        return PlainTextResponse("Internal Server Error", status_code=500)
```

This ensures stack traces and internal details never leak to clients in
production, while preserving them in development.

---

### 26. Mapbox token scope verification

**Current state:** `VITE_MAPBOX_TOKEN` in `.env` is a public token (`pk.` prefix)
baked into the frontend at build time.

**Problem:** Public Mapbox tokens are designed to be visible in browsers, but
without URL restrictions on the Mapbox dashboard, anyone can copy the token and
use it on their own site, consuming the account's quota.

**Fix:**

1. Log into Mapbox Studio → Account → Access tokens.
2. Edit the token and add URL restrictions to only allow requests from your
   production domain.
3. Consider creating separate tokens for development (unrestricted, low quota)
   and production (URL-restricted).

This is a Mapbox dashboard change, not a code change.

---

### 27. ~~Session invalidation on user deletion~~ DONE

**Implemented:** `users.py:delete_user` deletes the user from the DB and calls
`request.session.clear()`, which removes the signed session cookie. The
`auth.py:logout` endpoint also calls `request.session.clear()`.

The frontend also invalidates all Pinia Colada query caches on sign-out and
user deletion (`UserMenu.vue` calls `cache.invalidateQueries()`), preventing
stale user data from being shown after re-login with a different account.

Other sessions (other browsers) will get 401 on next request because
`deps.py:_get_user` does a DB lookup — the user no longer exists. The session
cookie payload (`{"uid": N}`) is harmless since the uid resolves to nothing.

---

### 28. ~~Playwright Chromium sandboxing~~ DONE

**Implemented:** Added `--no-sandbox` to Chromium launch args as part of
item #5 (non-root containers). The container itself is the sandbox — Chromium's
internal sandbox is redundant when the process is already non-root and
capability-restricted.

**File:** `backend/app/main.py`

---

### 29. Concurrent upload / processing abuse

**Current state:** The `process_user` SSE endpoint (`users.py:115`) and PDF
generation (`pdf.py`) are long-running operations. The PDF endpoint has a
semaphore (`_pdf_semaphore = asyncio.Semaphore(1)`) limiting concurrency to 1,
but `process_user` has no such limit.

**Problem:** An attacker can open many SSE connections to `/api/v1/users/process`,
each triggering ffprobe/ffmpeg/Pillow processing. This exhausts CPU and memory.

**Fix:**

1. Add a semaphore to `process_user` (or limit via slowapi).
2. Check if the user already has an active processing stream before starting a
   new one.
3. The nginx rate limiting from item #3 provides the first line of defense.

---

### 30. Frontend: audit v-html usage

**Current state:** Vue 3 auto-escapes `{{ }}` interpolations, but `v-html`
renders raw HTML. If any component uses `v-html` with user-supplied data
(trip descriptions, step names, etc.), it's an XSS vector.

**Fix:**

1. Search the frontend for all `v-html` usage:
   ```bash
   grep -r "v-html" frontend/src/
   ```
2. For each usage, verify the source is either:
   - Static/trusted content, OR
   - Sanitized through DOMPurify before rendering.
3. If any `v-html` uses user-supplied data, either replace with `{{ }}` (text
   interpolation) or add DOMPurify:
   ```typescript
   import DOMPurify from "dompurify"
   const clean = computed(() => DOMPurify.sanitize(rawHtml.value))
   ```

---

---

## Summary: implementation order

The items are numbered by severity, but the recommended implementation order
accounts for dependencies between items. Items marked ~~struck~~ are done.

1. ~~**#9** SECRET_KEY setting (dependency for #1)~~ — DONE (field added, no production validator yet)
2. ~~**#1** Signed cookie (depends on #9)~~ — DONE (Google OAuth2 + SessionMiddleware)
3. ~~**#2** Upload size limit~~ — DONE (3-layer: frontend `max-file-size`, nginx `client_max_body_size`, backend seek check; `VITE_MAX_UPLOAD_GB` env var)
4. ~~**#3** Rate limiting (nginx)~~ — DONE (two per-IP zones: `uploads` 1r/m, `general` 10r/s; 429 on excess)
5. ~~**#4** Security headers~~ — DONE (CSP, X-Frame-Options, MIME sniff, referrer, permissions; shared snippet)
6. ~~**#8** Proxy headers~~ — DONE (uvicorn `--proxy-headers` + nginx `X-Forwarded-For`/`X-Forwarded-Proto`)
7. ~~**#5** Non-root containers~~ — DONE (backend: `appuser`, frontend: `nginx` on port 8080)
8. ~~**#7** Docker security_opt + cap_drop + resource limits~~ — DONE (no-new-privileges, cap_drop ALL, read_only, resource limits, pids_limit, shm_size, init)
9. ~~**#6** MIME validation~~ — DONE (puremagic: ZIP magic bytes pre-extraction + inner file type check post-extraction)
10. ~~**#10** Network segmentation~~ — DONE (backend internal network isolates db; frontend network for nginx + backend outbound)
11. ~~**#11** Localhost-bind dev ports~~ — DONE (all dev ports prefixed with `127.0.0.1:`)
12. ~~**#12** Read-only filesystems~~ — DONE (implemented with item #7)
13. ~~**#13** Storage quotas~~ — NOT NEEDED (each upload replaces the previous; no accumulation)
14. ~~**#14** Validate extracted files~~ — DONE (implemented with item #6)
15. **#15** Strong DB password
16. **#16** CORS lockdown
17. **#17** Cookie path scope (low priority — cookie is small, no PII)
18. ~~**#18** PDF temp cleanup~~ DONE
19. **#24** Timestamp validation
20. **#25** Error response handler
21. **#19** HTTPS termination
22. **#20** Ruff CI enforcement
23. **#21** Dependency scanning
24. **#22** Semgrep
25. **#23** Trivy
26. **#26** Mapbox token scoping
27. ~~**#27** Session invalidation on user deletion~~ — DONE
28. ~~**#28** Playwright sandboxing~~ — DONE (`--no-sandbox`, handled with item #5)
29. **#29** Processing concurrency limit
30. **#30** v-html audit
