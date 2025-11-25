"""Template rendering utilities for HTML generation."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .logger import get_logger

logger = get_logger(__name__)

__all__ = ["create_template_environment", "render_album_template"]


def create_template_environment() -> Environment:
    """Create and configure Jinja2 template environment.

    Returns:
        Configured Jinja2 Environment instance.
    """
    template_dir = Path(__file__).parent / "templates"
    return Environment(loader=FileSystemLoader(str(template_dir)))


def render_album_template(
    template: Any, step_data_list: list[dict[str, Any]], light_mode: bool = False
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
