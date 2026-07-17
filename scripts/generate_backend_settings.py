from pathlib import Path
from sys import path

ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402

TS_OUTPUT = ROOT / "frontend" / "src" / "generated" / "backendSettings.ts"
NGINX_OUTPUT = ROOT / "frontend" / "nginx" / "generated-upload-limits.conf"


def main() -> None:
    fields = Settings.model_fields
    environment = fields["ENVIRONMENT"].default
    maximum = fields["MAX_UPLOAD_SIZE_BYTES"].default
    part_size = fields["UPLOAD_PART_SIZE_BYTES"].default
    TS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUTPUT.write_text(
        f'export const DEFAULT_ENVIRONMENT = "{environment}";\n'
        f"export const MAX_UPLOAD_SIZE_BYTES = {maximum};\n"
        f"export const UPLOAD_PART_SIZE_BYTES = {part_size};\n"
    )
    NGINX_OUTPUT.write_text(f"client_max_body_size {maximum};\n")


if __name__ == "__main__":
    main()
