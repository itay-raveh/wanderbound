import logging
import sys

_NOISY = ("sqlalchemy.engine", "httpx", "httpcore", "hishel", "PIL", "playwright")


def setup_logging(*, use_rich: bool) -> None:
    if use_rich:
        from rich.logging import RichHandler  # noqa: PLC0415

        handler = RichHandler(
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
            show_path=True,
        )
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )

    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    logging.getLogger("app").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
