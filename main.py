import logging
import os
import sys

from bot.utils.logging import configure_logging
from bot.utils.single_instance import SingleInstance
from config import get_settings


def check_onedrive():
    path = os.getcwd().lower()
    if "onedrive" in path:
        print("WARNING: Project is inside OneDrive. This may cause file lock issues.")


check_onedrive()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    logger = logging.getLogger(__name__)

    instance = SingleInstance()

    if not instance.acquire():
        print("Bot already running. Exit.")
        return 1

    try:
        from bot.bootstrap import start_bot
        start_bot()
        return 0
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        return 0
    except Exception as exc:
        logger.exception("Fatal error during bot startup: %s", exc)
        return 1
    finally:
        instance.release()


if __name__ == "__main__":
    sys.exit(main())
