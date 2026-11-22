"""Загрузка и валидация конфигурации AIOps Sentinel.

Читает переменные окружения из .env через pydantic-settings,
парсит app/targets.yaml и подставляет ${VAR} из окружения.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Модели pydantic для .env
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """Настройки из .env с типизацией и валидацией."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(default="", description="Токен Telegram-бота")
    telegram_chat_id: str = Field(default="", description="ID чата Telegram")
    telegram_proxy_url: Optional[str] = Field(
        default=None, description="HTTP-прокси для Telegram API (с авторизацией)"
    )

    # Планировщик
    check_interval_sec: int = Field(default=60, ge=5, le=3600)

    # Ollama
    ollama_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3")

    # Kafka
    kafka_bootstrap_servers: str = Field(default="localhost:9092")
    kafka_dlq_topic: str = Field(default="aiops-dlq")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# Модели pydantic для targets.yaml
# ---------------------------------------------------------------------------

class ResourceThresholds(BaseModel):
    """Пороги системных ресурсов (в процентах)."""

    cpu_threshold: int = Field(default=85, ge=1, le=100)
    ram_threshold: int = Field(default=85, ge=1, le=100)
    gpu_threshold: int = Field(default=90, ge=1, le=100)


class TargetDefaults(BaseModel):
    """Настройки по умолчанию для целей мониторинга."""

    interval_sec: int = Field(default=60, ge=5, le=3600)
    timeout_sec: int = Field(default=10, ge=1, le=300)
    retries: int = Field(default=2, ge=0, le=10)


class HttpTarget(BaseModel):
    """HTTP-цель мониторинга."""

    name: str
    type: str = Field(default="http")
    url: str
    timeout_sec: int = Field(default=10, ge=1, le=300)
    expect_status: int = Field(default=200, ge=100, le=599)


class DockerTarget(BaseModel):
    """Docker-цель мониторинга."""

    name: str
    type: str = Field(default="docker")
    container: str
    expect_state: str = Field(default="running", pattern="^(running|stopped|restarting)$")


class KafkaDlqTarget(BaseModel):
    """Kafka DLQ-цель мониторинга."""

    name: str
    type: str = Field(default="kafka_dlq")
    bootstrap_servers: str
    topic: str
    max_lag: int = Field(default=100, ge=0)
    max_messages: int = Field(default=50, ge=0)


class TargetsConfig(BaseModel):
    """Корневая конфигурация целей мониторинга."""

    defaults: TargetDefaults = Field(default_factory=TargetDefaults)
    resources: ResourceThresholds = Field(default_factory=ResourceThresholds)
    targets: List[Any] = Field(default_factory=list)

    @field_validator("targets", mode="before")
    @classmethod
    def validate_targets(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Валидация списка целей: каждая цель должна иметь name и type."""
        if not isinstance(v, list):
            raise ValueError("targets должен быть списком")
        for item in v:
            if not isinstance(item, dict):
                raise ValueError("Каждая цель должна быть словарём")
            if "name" not in item:
                raise ValueError("Каждая цель должна содержать поле 'name'")
            if "type" not in item:
                raise ValueError("Каждая цель должна содержать поле 'type'")
        return v


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: str) -> str:
    """Подставляет ${VAR} из переменных окружения."""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))
    return _ENV_VAR_PATTERN.sub(_replace, value)


def _resolve_env_vars_recursive(obj: Any) -> Any:
    """Рекурсивно подставляет ${VAR} во всех строковых значениях."""
    if isinstance(obj, str):
        return _resolve_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_vars_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars_recursive(item) for item in obj]
    return obj


@dataclass
class AppConfig:
    """Итоговая конфигурация приложения: настройки + цели."""

    settings: Settings
    targets_config: TargetsConfig

    @property
    def check_interval_sec(self) -> int:
        return self.settings.check_interval_sec

    @property
    def targets(self) -> List[Any]:
        return self.targets_config.targets


def load_config(targets_path: Optional[Path] = None) -> AppConfig:
    """Загружает .env и targets.yaml, возвращает валидированную конфигурацию."""
    settings = Settings()

    if targets_path is None:
        targets_path = Path(__file__).parent / "targets.yaml"

    with open(targets_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Подстановка ${VAR} из окружения
    raw = _resolve_env_vars_recursive(raw)

    targets_config = TargetsConfig(**raw)

    return AppConfig(settings=settings, targets_config=targets_config)