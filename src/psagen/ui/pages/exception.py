from __future__ import annotations

from psagen.core.logger import get_logger
from psagen.ui.dialog import create_log_dialog

logger = get_logger(__name__)


def handle_exception(e: Exception) -> None:
    logger.exception("Unexpected error", exc_info=e)

    # Use the shared dialog component with error styling
    _, log = create_log_dialog("An unexpected error occurred", "error", color="negative")
    log.push(str(e))
