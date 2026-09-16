"""Конфигурация GigaChat без чтения и записи секретов в коде."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


DEFAULT_BASE_URL = "https://api.giga.chat/v1"
DEFAULT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_MODEL = "GigaChat-2-Pro"
_MODEL = re.compile(r"^[A-Za-z0-9_.:-]{2,80}$")


@dataclass(frozen=True)
class GigaChatSettings:
    """Минимальная конфигурация SDK для исследовательского контура."""

    credentials: str
    scope: str = DEFAULT_SCOPE
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 60.0
    verify_ssl_certs: bool = True

    @classmethod
    def from_environment(cls) -> "GigaChatSettings":
        """Создать настройки из процесса, не выводя значение ключа."""
        credentials = os.environ.get("GIGACHAT_CREDENTIALS", "").strip()
        if not credentials:
            raise ValueError(
                "GIGACHAT_CREDENTIALS is required; provide it only through the local environment."
            )

        verify_value = os.environ.get("GIGACHAT_VERIFY_SSL_CERTS", "true").strip().lower()
        if verify_value not in {"true", "1", "yes"}:
            raise ValueError("TLS verification must remain enabled for this integration.")

        base_url = os.environ.get("GIGACHAT_BASE_URL", DEFAULT_BASE_URL).strip()
        if base_url != DEFAULT_BASE_URL:
            raise ValueError(f"Only the approved base URL is allowed: {DEFAULT_BASE_URL}")
        model = os.environ.get("GIGACHAT_MODEL", DEFAULT_MODEL).strip()
        if not _MODEL.fullmatch(model):
            raise ValueError("GigaChat model identifier is malformed")

        return cls(
            credentials=credentials,
            scope=os.environ.get("GIGACHAT_SCOPE", DEFAULT_SCOPE).strip() or DEFAULT_SCOPE,
            model=model,
            base_url=base_url,
            timeout=float(os.environ.get("GIGACHAT_TIMEOUT", "60")),
            verify_ssl_certs=True,
        )
