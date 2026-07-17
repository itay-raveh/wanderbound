import json
import os
import sys
from pathlib import Path

# Settings are env-driven; the OpenAPI spec isn't affected by these values.
os.environ.setdefault("SECRET_KEY", "codegen")
os.environ.setdefault(
    "SQLALCHEMY_DATABASE_URI", "postgresql+psycopg://codegen:codegen@localhost/codegen"
)
os.environ.setdefault("UPLOAD_S3_BUCKET", "codegen")
os.environ.setdefault("UPLOAD_S3_REGION", "codegen")
os.environ.setdefault("UPLOAD_S3_INTERNAL_ENDPOINT_URL", "http://localhost:3900")
os.environ.setdefault("UPLOAD_S3_PUBLIC_ENDPOINT_URL", "http://localhost:3900")
os.environ.setdefault("UPLOAD_S3_ADDRESSING_STYLE", "path")
os.environ.setdefault("UPLOAD_S3_ACCESS_KEY_ID", "codegen")
os.environ.setdefault("UPLOAD_S3_SECRET_ACCESS_KEY", "codegen")
os.environ.setdefault("VITE_MAPBOX_TOKEN", "codegen")
os.environ.setdefault("VITE_FRONTEND_URL", "http://localhost")

from app.main import app  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "backend" / "openapi.json"

out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"Wrote {out}", file=sys.stderr)
