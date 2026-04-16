import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.api.v1.router import router

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

API_V1_STR = "/api/v1"
_DEFAULT_OUT = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def custom_generate_unique_id(route: APIRoute) -> str:
    return route.name


app = FastAPI(
    title="Wanderbound",
    openapi_url=f"{API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)
app.include_router(router, prefix=API_V1_STR)

spec = json.dumps(app.openapi(), indent=2) + "\n"
out = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUT
out.write_text(spec)
print(f"Wrote {out}")
