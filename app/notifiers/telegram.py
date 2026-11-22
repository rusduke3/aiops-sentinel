"""Telegram-нотификатор AIOps Sentinel.

Поддерживает отправку через HTTP-прокси с авторизацией и
антиспам-дедупликацию (cooldown по целям), чтобы не заспамить чат
при падении сервиса.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

from ..checkers.base import CheckResult, CheckStatus

logger = logging.getLogger(__name__)

# Эмодзи для статусов
_STATUS_EMOJI = {
    CheckStatus.OK: "✅",
    CheckStatus.WARN: "⚠️",
    CheckStatus.CRITICAL: "🔴",
}


class TelegramNotifier:
    """Клиент отправки алертов в Telegram Bot API.

    - Поддержка HTTP-прокси с авторизацией через TELEGRAM_PROXY_URL.
    - Антиспам-дедупликация: повторный алерт по той же цели и статусу
      отправляется не чаще, чем раз в cooldown_sec.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        proxy_url: Optional[str] = None,
        cooldown_sec: int = 300,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.proxy_url = proxy_url
        self.cooldown_sec = cooldown_sec

        # Кэш последних отправок: ключ -> timestamp
        self._last_sent: Dict[str, float] = {}

        self._api_base = f"https://api.telegram.org/bot{bot_token}"

        # Настройка прокси
        self._proxies: Optional[Dict[str, str]] = None
        if proxy_url:
            self._proxies = {"http": proxy_url, "https": proxy_url}

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def send(self, result: CheckResult) -> bool:
        """Отправляет алерт по результату проверки с учётом дедупликации.

        Возвращает True, если сообщение было отправлено (или не требовалось).
        """
        # OK-статусы не отправляем (только алерты)
        if result.is_ok():
            return True

        dedup_key = f"{result.name}:{result.status}"

        if self._is_in_cooldown(dedup_key):
            logger.debug(
                "Алерт %s подавлен (cooldown %sс)", dedup_key, self.cooldown_sec
            )
            return True

        text = self._format_message(result)
        sent = self._send_message(text)

        if sent:
            self._last_sent[dedup_key] = time.monotonic()

        return sent

    def send_test(self) -> bool:
        """Отправляет тестовое сообщение для проверки связи."""
        text = (
            "🧪 <b>AIOps Sentinel — тест связи</b>\n\n"
            "Если вы видите это сообщение, нотификатор настроен корректно."
        )
        return self._send_message(text)

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _is_in_cooldown(self, key: str) -> bool:
        """Проверяет, не истёк ли cooldown для данного ключа."""
        last = self._last_sent.get(key)
        if last is None:
            return False
        return (time.monotonic() - last) < self.cooldown_sec

    def _format_message(self, result: CheckResult) -> str:
        """Форматирует CheckResult в HTML-сообщение Telegram."""
        emoji = _STATUS_EMOJI.get(result.status, "ℹ️")
        lines = [
            f"{emoji} <b>{result.status}</b> — <code>{result.name}</code>",
            "",
            f"<b>Сообщение:</b> {result.message}",
        ]

        if result.target_type:
            lines.append(f"<b>Тип:</b> {result.target_type}")

        if result.details:
            lines.append("")
            lines.append("<b>Детали:</b>")
            for key, value in result.details.items():
                lines.append(f"• <code>{key}</code>: {value}")

        lines.append("")
        lines.append(f"🕒 {result.timestamp}")
        return "\n".join(lines)

    def _send_message(self, text: str) -> bool:
        """Отправляет сообщение в Telegram Bot API."""
        if not self.bot_token or not self.chat_id:
            logger.error("Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID")
            return False

        url = f"{self._api_base}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                proxies=self._proxies,
                timeout=15,
            )
            if response.status_code == 200:
                logger.info("Алерт успешно отправлен в Telegram")
                return True

            logger.error(
                "Ошибка отправки в Telegram: HTTP %s — %s",
                response.status_code,
                response.text,
            )
            return False

        except requests.exceptions.RequestException as exc:
            logger.error("Ошибка соединения с Telegram API: %s", exc)
            return False

    @staticmethod
    def _mask_proxy(proxy_url: Optional[str]) -> str:
        """Маскирует учётные данные прокси для логов."""
        if not proxy_url:
            return "не используется"
        parsed = urlparse(proxy_url)
        if parsed.username:
            return f"{parsed.scheme}://***:***@{parsed.hostname}:{parsed.port}"
        return proxy_url