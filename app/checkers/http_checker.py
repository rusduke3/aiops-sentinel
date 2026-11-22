"""HTTP healthcheck для целей мониторинга AIOps Sentinel."""

from __future__ import annotations

from typing import Any, Dict

import requests

from .base import BaseChecker, CheckResult, CheckStatus


class HttpChecker(BaseChecker):
    """Проверка доступности HTTP-эндпоинта."""

    def __init__(self, name: str, url: str, timeout_sec: int = 10, expect_status: int = 200) -> None:
        super().__init__(name, target_type="http")
        self.url = url
        self.timeout_sec = timeout_sec
        self.expect_status = expect_status

    def check(self) -> CheckResult:
        """Выполняет HTTP GET и возвращает CheckResult."""
        details: Dict[str, Any] = {
            "url": self.url,
            "expect_status": self.expect_status,
        }

        try:
            response = requests.get(self.url, timeout=self.timeout_sec)
            details["status_code"] = response.status_code
            details["response_time_ms"] = round(response.elapsed.total_seconds() * 1000, 2)

            if response.status_code == self.expect_status:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.OK,
                    message=f"HTTP {response.status_code} OK",
                    details=details,
                    target_type=self.target_type,
                )

            return CheckResult(
                name=self.name,
                status=CheckStatus.WARN,
                message=f"HTTP {response.status_code}, ожидался {self.expect_status}",
                details=details,
                target_type=self.target_type,
            )

        except requests.exceptions.Timeout as exc:
            return CheckResult(
                name=self.name,
                status=CheckStatus.CRITICAL,
                message=f"Таймаут HTTP-запроса ({self.timeout_sec}с)",
                details={**details, "error": str(exc)},
                target_type=self.target_type,
            )

        except requests.exceptions.ConnectionError as exc:
            return CheckResult(
                name=self.name,
                status=CheckStatus.CRITICAL,
                message="Ошибка соединения с HTTP-эндпоинтом",
                details={**details, "error": str(exc)},
                target_type=self.target_type,
            )

        except requests.exceptions.RequestException as exc:
            return CheckResult(
                name=self.name,
                status=CheckStatus.CRITICAL,
                message=f"Ошибка HTTP-запроса: {exc}",
                details={**details, "error": str(exc)},
                target_type=self.target_type,
            )