"""Тонкий адаптер, изолирующий официальный SDK от остального приложения."""

from __future__ import annotations

from typing import Any, Callable

from .config import GigaChatSettings


class GigaChatConfigurationError(RuntimeError):
    """SDK недоступен или передана недопустимая конфигурация."""


class GigaChatClientFactory:
    """Создаёт официальный клиент только после проверки настроек."""

    def __init__(self, constructor: Callable[..., Any] | None = None) -> None:
        self._constructor = constructor

    def create(self, settings: GigaChatSettings) -> Any:
        """Вернуть SDK-клиент; секрет намеренно не логируется."""
        constructor = self._constructor or self._load_sdk_constructor()
        return constructor(
            credentials=settings.credentials,
            scope=settings.scope,
            model=settings.model,
            base_url=settings.base_url,
            timeout=settings.timeout,
            verify_ssl_certs=settings.verify_ssl_certs,
        )

    @staticmethod
    def _load_sdk_constructor() -> Callable[..., Any]:
        try:
            from gigachat import GigaChat
        except ImportError as exc:
            raise GigaChatConfigurationError(
                "The gigachat package is not installed. Install project dependencies first."
            ) from exc
        return GigaChat
