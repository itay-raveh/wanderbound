"""Template rendering utilities for HTML generation."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape

from src.core.logger import get_logger
from src.core.types import StepData

logger = get_logger(__name__)

__all__ = ["create_template_environment", "render_album_template"]


def create_template_environment() -> Environment:
    """Create and configure Jinja2 template environment.

    Returns:
        Configured Jinja2 Environment instance.
    """
    # Template is in static/ folder at project root
    # From src/template_renderer.py: parent=src/, parent.parent=project root
    template_dir = Path(__file__).parent.parent.parent / "static"
    return Environment(
        loader=FileSystemLoader(str(template_dir)), autoescape=select_autoescape(["html", "xml"])
    )


def render_album_template(
    template: Template, step_data_list: list[StepData], *, light_mode: bool = False
) -> str:
    """Render the album HTML template with step data.

    Args:
        template: Jinja2 template object.
        step_data_list: List of step data dictionaries for rendering.
        light_mode: If True, render in light mode; otherwise, dark mode.

    Returns:
        Rendered HTML string.
    """
    result = template.render(steps=step_data_list, light_mode=light_mode)
    return str(result)
