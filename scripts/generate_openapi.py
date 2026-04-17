import json
import os
import sys
from pathlib import Path

# Settings are env-driven; the OpenAPI spec isn't affected by these values.
for key in (
    "SECRET_KEY",
    "POSTGRES_SERVER",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
):
    os.environ.setdefault(key, "codegen")

from app.main import app  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "backend" / "openapi.json"

out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"Wrote {out}", file=sys.stderr)
