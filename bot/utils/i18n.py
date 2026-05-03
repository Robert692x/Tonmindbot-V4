from bot.services.i18n import get_text


def t(subject: object, key: str, **kwargs: object) -> str:
    """Shorthand for get_text — use inside formatter functions."""
    return get_text(subject, key, **kwargs)
