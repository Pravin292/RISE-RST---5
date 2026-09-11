import json
import logging
import os
import time

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient

logger = logging.getLogger("api.kafka")

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "csv-rows")


class KafkaProducerService:
    def __init__(self) -> None:
        self._producer = Producer({
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "acks": "all",
            "retries": 5,
            "linger.ms": 20,
        })
        self._admin = AdminClient({"bootstrap.servers": BOOTSTRAP_SERVERS})

    def is_connected(self) -> bool:
        try:
            metadata = self._admin.list_topics(timeout=3)
            return metadata is not None and metadata.brokers is not None and len(metadata.brokers) > 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("Kafka health check failed: %s", exc)
            return False

    def wait_until_ready(self, timeout_seconds: int = 60) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.is_connected():
                logger.info("Kafka is reachable at %s", BOOTSTRAP_SERVERS)
                return
            logger.info("Waiting for Kafka at %s ...", BOOTSTRAP_SERVERS)
            time.sleep(2)
        logger.warning("Kafka not reachable after %ss, continuing anyway", timeout_seconds)

    def publish_row(self, message: dict) -> None:
        self._producer.produce(TOPIC, value=json.dumps(message).encode("utf-8"))

    def flush(self, timeout: float = 10.0) -> int:
        return self._producer.flush(timeout)


producer_service = KafkaProducerService()
