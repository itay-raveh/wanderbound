from pathlib import Path
from sys import path

ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402

TS_OUTPUT = ROOT / "frontend" / "src" / "generated" / "uploadConfig.ts"
NGINX_OUTPUT = ROOT / "frontend" / "nginx" / "generated-upload-limits.conf"


def main() -> None:
    maximum = Settings.model_fields["MAX_UPLOAD_SIZE_BYTES"].default
    part_size = Settings.model_fields["UPLOAD_PART_SIZE_BYTES"].default
    TS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUTPUT.write_text(
        f"export const MAX_UPLOAD_SIZE_BYTES = {maximum};\n"
        f"export const UPLOAD_PART_SIZE_BYTES = {part_size};\n"
    )
    NGINX_OUTPUT.write_text(f"client_max_body_size {maximum};\n")


if __name__ == "__main__":
    main()
