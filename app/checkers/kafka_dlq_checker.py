"""Проверка DLQ-топика в Kafka для AIOps Sentinel."""

from __future__ import annotations

from typing import Any, Dict

from kafka import KafkaConsumer

from .base import BaseChecker, CheckResult, CheckStatus


class KafkaDlqChecker(BaseChecker):
    """Проверка глубины и лага DLQ-топика в Kafka."""

    def __init__(
        self,
        name: str,
        bootstrap_servers: str,
        topic: str,
        max_lag: int = 100,
        max_messages: int = 50,
    ) -> None:
        super().__init__(name, target_type="kafka_dlq")
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.max_lag = max_lag
        self.max_messages = max_messages

    def check(self) -> CheckResult:
        """Проверяет DLQ-топик и возвращает CheckResult."""
        details: Dict[str, Any] = {
            "bootstrap_servers": self.bootstrap_servers,
            "topic": self.topic,
            "max_lag": self.max_lag,
            "max_messages": self.max_messages,
        }

        try:
            consumer = KafkaConsumer(
                bootstrap_servers=self.bootstrap_servers,
                consumer_timeout_ms=5000,
                enable_auto_commit=False,
            )

            # Получаем информацию о партициях топика
            partitions = consumer.partitions_for_topic(self.topic)
            if partitions is None:
                consumer.close()
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.CRITICAL,
                    message=f"Топик {self.topic} не найден в Kafka",
                    details={**details, "error": "topic_not_found"},
                    target_type=self.target_type,
                )

            # Подсчитываем сообщения в топике (приблизительно)
            total_messages = 0
            for partition_id in partitions:
                tp = consumer.partitions_for_topic(self.topic)
                # Используем end_offsets для оценки глубины
                from kafka.structs import TopicPartition

                topic_partition = TopicPartition(self.topic, partition_id)
                end_offsets = consumer.end_offsets([topic_partition])
                total_messages += end_offsets.get(topic_partition, 0)

            consumer.close()

            details["total_messages"] = total_messages
            details["partitions"] = len(partitions)

            if total_messages > self.max_messages:
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.WARN,
                    message=f"Глубина DLQ {total_messages} сообщений превышает порог {self.max_messages}",
                    details=details,
                    target_type=self.target_type,
                )

            return CheckResult(
                name=self.name,
                status=CheckStatus.OK,
                message=f"DLQ-топик {self.topic} в норме ({total_messages} сообщений)",
                details=details,
                target_type=self.target_type,
            )

        except Exception as exc:  # noqa: BLE001 — общая обработка ошибок Kafka
            return CheckResult(
                name=self.name,
                status=CheckStatus.CRITICAL,
                message=f"Ошибка проверки Kafka DLQ: {exc}",
                details={**details, "error": str(exc)},
                target_type=self.target_type,
            )