"""Проверка состояния Docker-контейнеров для AIOps Sentinel."""

from __future__ import annotations

from typing import Any, Dict

import docker

from .base import BaseChecker, CheckResult, CheckStatus


class DockerChecker(BaseChecker):
    """Проверка состояния Docker-контейнера."""

    def __init__(self, name: str, container: str, expect_state: str = "running") -> None:
        super().__init__(name, target_type="docker")
        self.container = container
        self.expect_state = expect_state
        self._client = docker.from_env()

    def check(self) -> CheckResult:
        """Проверяет состояние контейнера и возвращает CheckResult."""
        details: Dict[str, Any] = {
            "container": self.container,
            "expect_state": self.expect_state,
        }

        try:
            container = self._client.containers.get(self.container)
            actual_state = container.status
            details["actual_state"] = actual_state
            details["container_id"] = container.id[:12]

            if actual_state == self.expect_state:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.OK,
                    message=f"Контейнер {self.container} в состоянии {actual_state}",
                    details=details,
                    target_type=self.target_type,
                )

            return CheckResult(
                name=self.name,
                status=CheckStatus.WARN,
                message=f"Контейнер {self.container} в состоянии {actual_state}, ожидался {self.expect_state}",
                details=details,
                target_type=self.target_type,
            )

        except docker.errors.NotFound:
            return CheckResult(
                name=self.name,
                status=CheckStatus.CRITICAL,
                message=f"Контейнер {self.container} не найден",
                details={**details, "error": "not_found"},
                target_type=self.target_type,
            )

        except docker.errors.APIError as exc:
            return CheckResult(
                name=self.name,
                status=CheckStatus.CRITICAL,
                message=f"Ошибка Docker API: {exc}",
                details={**details, "error": str(exc)},
                target_type=self.target_type,
            )