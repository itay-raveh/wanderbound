"""Template rendering utilities for HTML generation."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape

from src.core.logger import get_logger
from src.data.models import AlbumGenerationConfig, StepData, TripSummary

logger = get_logger(__name__)


def create_template_environment() -> Environment:
    # Template is in static/ folder at project root
    # From src/template_renderer.py: parent=src/, parent.parent=project root
    template_dir = Path(__file__).parent.parent.parent / "static"
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_album_template(
    template: Template,
    step_data_list: list[StepData],
    config: AlbumGenerationConfig,
    *,
    light_mode: bool,
    summary: TripSummary | None = None,
) -> str:
    result = template.render(
        steps=step_data_list,
        light_mode=light_mode,
        editor_mode=config.editor_mode,
        summary=summary,
        trip=config.trip_display_data,
    )
    return str(result)
