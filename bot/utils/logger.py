import logging
import sys
from config import settings


def setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stdout)
    for lib in ("aiogram", "httpx", "openai", "sqlalchemy.engine"):
        logging.getLogger(lib).setLevel(logging.WARNING)
