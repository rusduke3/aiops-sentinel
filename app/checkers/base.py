"""Базовый интерфейс и формат результата для чекеров AIOps Sentinel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class CheckStatus:
    """Статусы результата проверки."""

    OK = "OK"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


@dataclass
class CheckResult:
    """Единый формат результата проверки.

    Все чекеры возвращают этот dataclass.
    """

    name: str
    status: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    target_type: Optional[str] = None

    def is_ok(self) -> bool:
        return self.status == CheckStatus.OK

    def is_warn(self) -> bool:
        return self.status == CheckStatus.WARN

    def is_critical(self) -> bool:
        return self.status == CheckStatus.CRITICAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "target_type": self.target_type,
        }


class BaseChecker:
    """Базовый класс для всех чекеров.

    Каждый чекер должен реализовать метод check() и возвращать CheckResult.
    """

    def __init__(self, name: str, target_type: str) -> None:
        self.name = name
        self.target_type = target_type

    def check(self) -> CheckResult:
        """Выполняет проверку и возвращает CheckResult."""
        raise NotImplementedError("Метод check() должен быть реализован в подклассе")