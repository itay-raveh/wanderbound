from fastapi import APIRouter, Response

from app.core.config import PublicSettings, get_settings

router = APIRouter(tags=["config"])


@router.get("/config")
def public_config(response: Response) -> PublicSettings:
    response.headers["Cache-Control"] = "no-store"
    return PublicSettings.model_validate(
        get_settings().model_dump(include=set(PublicSettings.model_fields))
    )
