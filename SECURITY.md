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

### 2. Upload size limit

**Current state:** `nginx.conf:3` sets `client_max_body_size 2G`. There is no
application-level size limit. FastAPI's `UploadFile` reads the entire file into
a `SpooledTemporaryFile` before handing it to the endpoint.

**Problem:** A single request can push up to 2 GB to the server, consuming disk
and memory. An attacker can open multiple connections and exhaust both in
minutes. Now that uploads require Google authentication (#1), the attack surface
is smaller — but authenticated users can still abuse storage.

**Context:** Polarsteps exports can legitimately reach 3+ GB for users with
hundreds of photos and videos across many trips. The upload size limit must
accommodate real exports, not just typical ones.

**Fix:**

1. **Nginx layer** — set `client_max_body_size` to `4g` in `nginx.conf`.
   This accommodates the largest real Polarsteps exports while still capping
   runaway uploads. Nginx rejects the request immediately with 413 before any
   bytes reach the backend.
2. **Application layer** — add a streaming size check in the upload endpoint.
   Read the file in chunks and abort if total exceeds the limit, so we never hold
   the entire body in memory:
   ```python
   MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024  # 4 GB

   @router.post("/upload")
   async def upload_data(file: UploadFile, ...):
       total = 0
       buffer = io.BytesIO()
       while chunk := await file.read(65536):
           total += len(chunk)
           if total > MAX_UPLOAD_BYTES:
               raise HTTPException(413, "Upload too large")
           buffer.write(chunk)
       buffer.seek(0)
       ...
   ```
3. Add `client_body_timeout 300s` in nginx to kill slow-upload (Slowloris-style)
   connections. (300s instead of 120s to accommodate large legitimate uploads on
   slower connections.)
4. **Storage protection** is handled separately by item #13 (per-user storage
   quota) and item #3 (rate limiting) — not by the upload size limit.

---

### 3. Rate limiting: nginx + application-level

**Current state:** No rate limiting of any kind exists. Every endpoint is
unlimited. The upload endpoint (which triggers ZIP extraction, filesystem writes,
ffprobe/ffmpeg/Pillow processing, and DB operations) has no throttle.

**Problem:** An attacker can script thousands of concurrent requests to exhaust
CPU, memory, disk, or DB connections. Even legitimate multi-tab use could
overwhelm the single-instance backend.

**Fix (two layers, defense in depth):**

**Layer 1 — Nginx rate limiting (blocks floods before they hit Python):**

Add to the `http` block (or top of the server config file):

```nginx
# Per-IP rate zones
limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=uploads:10m rate=1r/m;

server {
    # Upload endpoint — strictest limit
    location = /api/v1/users/upload {
        limit_req zone=uploads burst=2 nodelay;
        limit_req_status 429;
        client_max_body_size 4g;
        proxy_pass http://backend:8000;
        # ... existing proxy headers ...
    }

    # General API
    location /api/ {
        limit_req zone=general burst=30 nodelay;
        limit_req_status 429;
        proxy_pass http://backend:8000;
        # ... existing proxy headers ...
    }

    # Static assets — no limit needed
    location /assets/ { ... }
    location / { ... }
}
```

**Layer 2 — Application rate limiting with `slowapi`:**

```python
# main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Per-endpoint decorators:
- Upload: `@limiter.limit("3/hour")` — nobody needs to upload more than 3 ZIPs/hour
- PDF generation: `@limiter.limit("5/hour")` — expensive Playwright operation
- SSE streams: `@limiter.limit("10/minute")`
- General read endpoints: `@limiter.limit("60/minute")`
- Health check: `@limiter.exempt`

**Dependencies:** `pip install slowapi`

---

## HIGH

### 4. Nginx security headers

**Current state:** `nginx.conf` has zero security response headers. No CSP, no
frame protection, no MIME sniffing protection, no referrer policy. Nginx version
is exposed via default `server_tokens`.

**Problem:** Browsers have no instructions to mitigate XSS, clickjacking, MIME
confusion, or information leakage. Automated scanners flag this immediately.

**Fix:** Add to the `server` block:

```nginx
server_tokens off;

# Security headers — in the server block so they apply to all locations.
# Note: add_header in a location block overrides the server block, so every
# location that already uses add_header must repeat these.
add_header X-Content-Type-Options  "nosniff"                             always;
add_header X-Frame-Options         "DENY"                                always;
add_header Referrer-Policy         "strict-origin-when-cross-origin"     always;
add_header Permissions-Policy      "camera=(), microphone=(), geolocation=()" always;
add_header Content-Security-Policy
    "default-src 'self'; "
    "script-src 'self' https://accounts.google.com/gsi/client; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://api.mapbox.com https://*.tiles.mapbox.com https://lh3.googleusercontent.com; "
    "font-src 'self'; "
    "connect-src 'self' https://api.mapbox.com https://events.mapbox.com https://accounts.google.com/gsi/; "
    "frame-src https://accounts.google.com/gsi/; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
    always;
```

Note: Google Sign-In (`vue3-google-login`) requires:
- `script-src` — loads `https://accounts.google.com/gsi/client`
- `frame-src` — Google One Tap renders in an iframe from `accounts.google.com/gsi/`
- `connect-src` — token verification callbacks to `accounts.google.com/gsi/`
- `img-src` — profile avatars served from `lh3.googleusercontent.com`

Because the existing `location /assets/` and `location /` blocks already use
`add_header Cache-Control`, they override the server-level headers. Either:
- Move security headers into a shared snippet and `include` it in every location, or
- Use the `headers-more-nginx-module` (`more_set_headers`), which doesn't suffer
  from this inheritance behavior, or
- Repeat the security `add_header` directives in each location block.

The cleanest approach is an `include` snippet.

---

### 5. Containers run as root

**Current state:** Neither `backend/Dockerfile` nor `frontend/Dockerfile`
contains a `USER` directive. All processes run as root inside the container.

**Problem:** If an attacker achieves code execution inside the container (e.g.,
via a crafted media file exploiting ffmpeg/Pillow), they are root. Combined with
default Docker capabilities, this significantly increases the blast radius of
any exploit.

**Fix:**

**Backend Dockerfile** — add after the final `COPY`:
```dockerfile
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && mkdir -p /app/backend/data && chown -R appuser:appuser /app/backend/data
USER appuser
```

Note: `playwright install chromium --with-deps` must run as root (it installs
system packages). So the `RUN playwright install` line stays before the `USER`
switch. The Chromium binary itself runs fine as non-root.

Reorder the Dockerfile:
```dockerfile
# ... (existing apt-get, uv sync, COPY steps) ...
RUN playwright install chromium --with-deps
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app/backend/data
USER appuser
EXPOSE 8000
CMD [...]
```

**Frontend Dockerfile** — nginx:1 runs master as root (needed for port 80) but
workers should run as the `nginx` user (default in the `nginx` image). Add:
```dockerfile
RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /run
# nginx master still runs as root for port 80; workers run as nginx user.
# This is the default nginx.conf behavior — just ensure writable dirs.
```

If we want the entire process non-root, switch to port 8080 and add `USER nginx`:
```dockerfile
USER nginx
EXPOSE 8080
```
...and update compose to map `80:8080`.

---

### 6. MIME type validation on upload

**Current state:** The upload endpoint (`users.py:upload_data`) passes the
uploaded file to `extract_and_scan()` which calls `_safe_extract()` (a custom
ZIP extractor in `upload.py` that replaced the `safezip` dependency). If the
file is not a valid ZIP, `BadZipFile` is raised. `_safe_extract` already checks
for path traversal, symlinks, decompression bomb size, and file count — but
these checks only run after `zipfile.ZipFile` successfully opens the file.

**Problem:** An attacker can upload any file type (executables, scripts, HTML with
embedded JS, polyglot files). The lack of early MIME validation means the full
payload reaches disk before rejection, and there's no defense against a valid
ZIP containing unexpected file types.

**Fix:**

1. **Validate magic bytes before extraction** using `python-magic`:
   ```python
   import magic

   ALLOWED_ZIP_MIMES = {"application/zip", "application/x-zip-compressed"}

   async def upload_data(file: UploadFile, ...):
       header = await file.read(2048)
       await file.seek(0)
       mime = magic.from_buffer(header, mime=True)
       if mime not in ALLOWED_ZIP_MIMES:
           raise HTTPException(415, "File must be a ZIP archive")
       ...
   ```

2. **Validate extracted media files** — after extraction, before processing,
   check that every file in the extracted directory is an expected type:
   ```python
   ALLOWED_CONTENT_MIMES = {
       "image/jpeg", "video/mp4", "application/json", "text/plain",
   }
   ```
   Reject or skip files that don't match.

3. Add `libmagic1` to the backend Dockerfile's `apt-get install` line.

**Dependencies:** `pip install python-magic`, system package `libmagic1`.

---

### 7. Docker Compose: security_opt, cap_drop, resource limits

**Current state:** `compose.yml` has no `security_opt`, `cap_drop`, or resource
limits on any service. Containers have all default Linux capabilities.

**Problem:**
- No `no-new-privileges` → a setuid binary inside the container can escalate to
  root.
- No `cap_drop` → containers have capabilities like `NET_RAW`, `SYS_CHROOT`,
  `CHOWN`, `SETUID`, etc., far more than a web app needs.
- No resource limits → a single container can consume all host memory/CPU (DoS).

**Fix — add to each service in `compose.yml`:**

```yaml
services:
  backend:
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    deploy:
      resources:
        limits:
          memory: 4G     # Playwright + ffmpeg can be hungry
          cpus: "2.0"

  frontend:
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    cap_add: ["NET_BIND_SERVICE"]   # port 80
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.5"

  db:
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1.0"

  prestart:
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
```

---

### 8. ~~Proxy headers for real client IP~~ PARTIALLY DONE

**Done:** Added `--proxy-headers` to the uvicorn command in both `Dockerfile`
and `compose.override.yml`. Uvicorn now reads `X-Forwarded-For` and
`X-Forwarded-Proto` from upstream proxies.

**Remaining:**

1. Add to the nginx `location /api/` block:
   ```nginx
   proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
   proxy_set_header X-Forwarded-Proto $scheme;
   ```

2. Consider adding `--forwarded-allow-ips='*'` (or the specific proxy IP) to
   trust the forwarded headers. Within Docker Compose, the nginx container's IP
   is dynamic, so `'*'` is acceptable since nginx is the only upstream.

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

### 10. Network segmentation in Docker Compose

**Current state:** All services share the default Docker Compose bridge network.
The frontend (nginx) container can directly reach the PostgreSQL container.

**Problem:** If the nginx container is compromised (e.g., via a vulnerability in
nginx itself), the attacker has direct network access to the database.

**Fix:**

```yaml
services:
  db:
    networks: [backend]

  prestart:
    networks: [backend]

  backend:
    networks: [backend, frontend]

  frontend:
    networks: [frontend]

networks:
  backend:
    internal: true   # no external access at all
  frontend:
```

The `internal: true` flag on the backend network means even if a container on
that network is compromised, it cannot make outbound connections to the internet
(except through the backend, which has access to both networks).

---

### 11. Bind development ports to localhost

**Current state:** `compose.override.yml` exposes ports as `"5432:5432"`,
`"8000:8000"`, `"5173:80"` — bound to `0.0.0.0` (all interfaces).

**Problem:** On a machine connected to any network (coffee shop, hotel, shared
WiFi), the database, backend, and frontend are accessible to anyone on the same
network. Docker port mappings bypass host firewalls (UFW, iptables).

**Fix:** Prefix all dev ports with `127.0.0.1:`:

```yaml
services:
  db:
    ports: ["127.0.0.1:5432:5432"]
  backend:
    ports: ["127.0.0.1:8000:8000"]
  frontend:
    ports: ["127.0.0.1:5173:80"]
```

---

### 12. Read-only container filesystems

**Current state:** All containers have read-write root filesystems.

**Problem:** If an attacker gains code execution inside a container, they can
modify any file (binaries, configs, scripts). A read-only filesystem means
malware or backdoors cannot be persisted inside the container.

**Fix:**

```yaml
services:
  backend:
    read_only: true
    tmpfs:
      - /tmp:size=500M
      - /run:size=10M
    volumes:
      - app-data:/app/backend/data   # already exists — the only writable path

  frontend:
    read_only: true
    tmpfs:
      - /tmp:size=50M
      - /var/cache/nginx:size=200M
      - /run:size=10M

  db:
    read_only: true
    tmpfs:
      - /tmp:size=100M
      - /var/run/postgresql:size=10M
    volumes:
      - db-data:/var/lib/postgresql/data/pgdata   # already exists
```

Note: Playwright needs write access for its browser profile. The backend's
`/tmp` tmpfs handles this since Playwright uses temp directories. Test
thoroughly after enabling.

---

### 13. Per-user storage quota

**Current state:** Each upload extracts a full Polarsteps export to
`data/users/<uid>/`. There is no tracking of disk usage per user and no limit
on total storage consumed. Temp directory cleanup on extraction failure IS
implemented (`extract_and_scan` wraps extraction in try/except with
`shutil.rmtree`; `upload_data` also cleans up the temp folder if the DB
commit or folder rename fails).

**Problem:** A single user (or attacker) can upload repeatedly, each time
consuming hundreds of MB.

**Fix:**

1. **Track user storage** — add a computed or cached field:
   ```python
   def disk_usage(self) -> int:
       """Total bytes used by this user's data directory."""
       return sum(f.stat().st_size for f in self.folder.rglob("*") if f.is_file())
   ```

2. **Enforce a quota** before accepting new uploads:
   ```python
   MAX_USER_STORAGE = 500 * 1024 * 1024  # 500 MB
   ```

3. ~~**Clean up temp directories**~~ — DONE. Both `extract_and_scan()` in
   `upload.py` and `upload_data()` in `users.py` clean up temp directories
   on failure.

4. **Global storage limit** — check total disk usage of `USERS_FOLDER` and reject
   uploads when the server is running low (e.g., < 1 GB free).

---

### 14. Validate extracted file types after ZIP extraction

**Current state:** After `_safe_extract()` (in `upload.py`), the code reads
`user.json` and iterates trip directories, trusting that the ZIP contains only
expected file types (JSON, JPEG, MP4). `_safe_extract` already rejects symlinks
during extraction (via `external_attr` check) and blocks path traversal, but
does not validate individual file types.

**Problem:** A crafted ZIP could contain executable files, HTML files with
embedded scripts, or other unexpected content. These files are then served by
the `get_media` endpoint or processed by ffmpeg/Pillow.

**Fix:**

After extraction, walk the directory and:
1. Verify every file is one of the expected types (`.json`, `.jpg`, `.mp4`)
   using both extension AND magic bytes.
2. Delete or reject any unexpected files.
3. ~~Verify no symlinks exist in the extracted tree~~ — DONE. Symlinks are
   rejected during extraction by `_safe_extract()` in `upload.py`.

```python
import magic

ALLOWED_EXTENSIONS = {".json", ".jpg", ".jpeg", ".mp4"}

def _validate_extracted_files(folder: Path) -> None:
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symlink not allowed: {path.name}")
        if path.is_file() and path.suffix.lower() not in ALLOWED_EXTENSIONS:
            path.unlink()
            logger.warning("Removed unexpected file: %s", path.name)
```

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

### 18. PDF temp files not cleaned up on server restart

**Current state:** `pdf.py:62` stores download tokens in an in-memory dict
`_tokens`. Tokens have a 5-minute TTL via `call_later`. When the server
restarts, all pending tokens are lost — but the temp files on disk remain
forever.

**Problem:** Over time, orphaned PDF temp files accumulate in `/tmp`, consuming
disk.

**Fix:**

1. Write PDF temp files to a dedicated directory (e.g., `data/pdf-tmp/`) instead
   of the system `/tmp`.
2. On startup (in the `lifespan` function), delete all files in that directory
   older than `_TOKEN_TTL` seconds.
3. Add a periodic cleanup task (or just clean on every new PDF generation).

```python
PDF_TMP_DIR = settings.DATA_FOLDER / "pdf-tmp"

@asynccontextmanager
async def lifespan(app: FastAPI):
    PDF_TMP_DIR.mkdir(exist_ok=True)
    # Clean stale PDFs from previous runs
    for f in PDF_TMP_DIR.iterdir():
        if f.is_file():
            f.unlink()
    ...
```

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

### 28. Playwright Chromium sandboxing

**Current state:** `main.py:33` launches Chromium with `args=["--use-gl=angle"]`.
No explicit sandbox flags. Playwright's default behavior in a Docker container
depends on the kernel capabilities available.

**Problem:** If the container runs as non-root (item #5) and has `cap_drop: ALL`
(item #7), Chromium's sandbox may fail to initialize because it needs `clone()`
with `CLONE_NEWUSER`. This would cause PDF generation to fail.

**Fix:**

After implementing items #5 and #7, test PDF generation. If Chromium's sandbox
fails, add `--no-sandbox` to the launch args:

```python
browser = await pw.chromium.launch(args=["--use-gl=angle", "--no-sandbox"])
```

This is safe because the container itself IS the sandbox (non-root, capability-
dropped, read-only filesystem, resource-limited). The Chromium sandbox is
defense-in-depth within the container, but the container-level isolation is the
primary boundary.

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
3. **#2** Upload size limit (nginx + application)
4. **#3** Rate limiting (nginx + slowapi)
5. **#4** Security headers
6. ~~**#8** Proxy headers~~ — PARTIALLY DONE (uvicorn flag added, nginx headers remaining)
7. **#5** Non-root containers
8. **#7** Docker security_opt + cap_drop + resource limits
9. **#6** MIME validation
10. **#10** Network segmentation
11. **#11** Localhost-bind dev ports
12. **#12** Read-only filesystems
13. **#13** Storage quotas
14. **#14** Validate extracted files
15. **#15** Strong DB password
16. **#16** CORS lockdown
17. **#17** Cookie path scope (low priority — cookie is small, no PII)
18. **#18** PDF temp cleanup
19. **#24** Timestamp validation
20. **#25** Error response handler
21. **#19** HTTPS termination
22. **#20** Ruff CI enforcement
23. **#21** Dependency scanning
24. **#22** Semgrep
25. **#23** Trivy
26. **#26** Mapbox token scoping
27. ~~**#27** Session invalidation on user deletion~~ — DONE
28. **#28** Test Playwright sandboxing
29. **#29** Processing concurrency limit
30. **#30** v-html audit
