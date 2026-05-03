from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class I18nService:
    def __init__(self, locales_dir: str | Path = "locales", default_language: str = "en") -> None:
        self.default_language = default_language
        self.locales_dir = Path(locales_dir)
        self._catalogs = self._load_catalogs()

    def _load_catalogs(self) -> dict[str, dict[str, str]]:
        catalogs: dict[str, dict[str, str]] = {}
        for path in self.locales_dir.glob("*.json"):
            with path.open("r", encoding="utf-8") as file:
                catalogs[path.stem] = json.load(file)
        if self.default_language not in catalogs:
            raise RuntimeError(f"Default locale '{self.default_language}' not found in {self.locales_dir}")
        return catalogs

    def resolve_language(self, subject: Any) -> str:
        if isinstance(subject, str) and subject in self._catalogs:
            return subject
        language = getattr(subject, "language_code", None) or getattr(subject, "language", None)
        if isinstance(language, str):
            normalized = language.lower()
            if normalized in self._catalogs:
                return normalized
            prefix = normalized.split("-", maxsplit=1)[0]
            if prefix in self._catalogs:
                return prefix
        return self.default_language

    def translate(self, subject: Any, key: str, **kwargs: Any) -> str:
        language = self.resolve_language(subject)
        catalog = self._catalogs.get(language, {})
        template = catalog.get(key) or self._catalogs[self.default_language].get(key) or key
        return template.format(**kwargs)


_i18n: I18nService | None = None


def configure_i18n(service: I18nService) -> None:
    global _i18n
    _i18n = service


def get_i18n() -> I18nService:
    global _i18n
    if _i18n is None:
        _i18n = I18nService()
    return _i18n


def get_text(user: Any, key: str, **kwargs: Any) -> str:
    return get_i18n().translate(user, key, **kwargs)
