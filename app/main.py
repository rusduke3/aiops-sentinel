"""Основной модуль AIOps Sentinel.

Запускает цикл опроса целей мониторинга и отправляет алерты в Telegram.
Поддерживает режим --test-alert для проверки связи с Telegram.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Any, Dict, List

from .checkers.base import BaseChecker, CheckResult
from .checkers.docker_checker import DockerChecker
from .checkers.http_checker import HttpChecker
from .checkers.kafka_dlq_checker import KafkaDlqChecker
from .config import AppConfig, load_config
from .notifiers.telegram import TelegramNotifier

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("aiops-sentinel")


# ---------------------------------------------------------------------------
# Фабрика чекеров
# ---------------------------------------------------------------------------

def _build_checker(target: Dict[str, Any]) -> BaseChecker:
    """Создаёт чекер по типу цели из targets.yaml."""
    target_type = target.get("type", "")

    if target_type == "http":
        return HttpChecker(
            name=target["name"],
            url=target["url"],
            timeout_sec=target.get("timeout_sec", 10),
            expect_status=target.get("expect_status", 200),
        )

    if target_type == "docker":
        return DockerChecker(
            name=target["name"],
            container=target["container"],
            expect_state=target.get("expect_state", "running"),
        )

    if target_type == "kafka_dlq":
        return KafkaDlqChecker(
            name=target["name"],
            bootstrap_servers=target["bootstrap_servers"],
            topic=target["topic"],
            max_lag=target.get("max_lag", 100),
            max_messages=target.get("max_messages", 50),
        )

    raise ValueError(f"Неизвестный тип цели: {target_type}")


def _build_checkers(config: AppConfig) -> List[BaseChecker]:
    """Создаёт список чекеров из конфигурации."""
    checkers: List[BaseChecker] = []
    for target in config.targets:
        try:
            checker = _build_checker(target)
            checkers.append(checker)
            logger.info("Зарегистрирована цель: %s (%s)", checker.name, checker.target_type)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка создания чекера для цели %s: %s", target.get("name"), exc)
    return checkers


# ---------------------------------------------------------------------------
# Основной цикл
# ---------------------------------------------------------------------------

def run_scheduler(config: AppConfig, notifier: TelegramNotifier) -> None:
    """Основной цикл опроса целей мониторинга."""
    checkers = _build_checkers(config)
    if not checkers:
        logger.error("Не зарегистрировано ни одной цели мониторинга. Завершение.")
        sys.exit(1)

    interval = config.check_interval_sec
    logger.info("AIOps Sentinel запущен. Интервал опроса: %sс. Целей: %s", interval, len(checkers))

    while True:
        cycle_start = time.monotonic()
        logger.info("--- Начало цикла опроса ---")

        for checker in checkers:
            try:
                result = checker.check()
                logger.info(
                    "Проверка %s: %s — %s",
                    result.name,
                    result.status,
                    result.message,
                )
                notifier.send(result)
            except Exception as exc:  # noqa: BLE001
                logger.error("Ошибка выполнения проверки %s: %s", checker.name, exc)

        elapsed = time.monotonic() - cycle_start
        logger.info("--- Цикл завершён за %.2fс ---", elapsed)

        sleep_sec = max(0, interval - elapsed)
        time.sleep(sleep_sec)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main() -> None:
    """Точка входа приложения."""
    parser = argparse.ArgumentParser(
        description="AIOps Sentinel — мониторинг AI-инфраструктуры",
    )
    parser.add_argument(
        "--test-alert",
        action="store_true",
        help="Тестовый режим: отправить тестовое сообщение в Telegram и выйти",
    )
    args = parser.parse_args()

    try:
        config = load_config()
    except Exception as exc:  # noqa: BLE001
        logger.error("Ошибка загрузки конфигурации: %s", exc)
        sys.exit(1)

    notifier = TelegramNotifier(
        bot_token=config.settings.telegram_bot_token,
        chat_id=config.settings.telegram_chat_id,
        proxy_url=config.settings.telegram_proxy_url,
    )

    if args.test_alert:
        logger.info("Тестовый режим: отправка тестового сообщения в Telegram...")
        success = notifier.send_test()
        if success:
            logger.info("Тестовое сообщение успешно отправлено.")
            sys.exit(0)
        else:
            logger.error("Не удалось отправить тестовое сообщение.")
            sys.exit(1)

    run_scheduler(config, notifier)


if __name__ == "__main__":
    main()