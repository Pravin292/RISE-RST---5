import os
import json
import logging
import time
from typing import Dict, Any, List, Optional
from kafka import KafkaProducer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import KafkaError

logger = logging.getLogger("kafka_producer_service")
logging.basicConfig(level=logging.INFO)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "csv-rows")

class KafkaService:
    def __init__(self):
        self.producer: Optional[KafkaProducer] = None
        self._connect()

    def _connect(self):
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                retries=5,
                acks="all"
            )
            logger.info("Kafka Producer connected successfully.")
            self._ensure_topic_exists()
        except Exception as e:
            logger.warning(f"Failed to connect Kafka Producer: {e}")
            self.producer = None

    def _ensure_topic_exists(self):
        try:
            admin = KafkaAdminClient(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                request_timeout_ms=3000
            )
            topics = admin.list_topics()
            if KAFKA_TOPIC not in topics:
                logger.info(f"Creating Kafka topic: {KAFKA_TOPIC}")
                new_topic = NewTopic(name=KAFKA_TOPIC, num_partitions=1, replication_factor=1)
                admin.create_topics(new_topics=[new_topic], validate_only=False)
            admin.close()
        except Exception as e:
            logger.warning(f"Could not verify/create Kafka topic: {e}")

    def check_health(self) -> bool:
        if not self.producer:
            self._connect()
        if not self.producer:
            return False
        try:
            admin = KafkaAdminClient(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                request_timeout_ms=3000
            )
            cluster_metadata = admin.describe_cluster()
            admin.close()
            return cluster_metadata is not None
        except Exception as e:
            logger.warning(f"Kafka health check failed: {e}")
            return False

    def send_row_message(self, dataset_id: str, filename: str, row_index: int, row_data: Dict[str, Any], uploaded_at: str) -> bool:
        if not self.producer:
            self._connect()
        if not self.producer:
            raise RuntimeError("Kafka producer is not connected.")

        message = {
            "dataset_id": dataset_id,
            "filename": filename,
            "row_index": row_index,
            "row_data": row_data,
            "uploaded_at": uploaded_at
        }
        
        message_key = f"{dataset_id}_{row_index}"
        
        try:
            future = self.producer.send(KAFKA_TOPIC, key=message_key, value=message)
            future.get(timeout=5.0)
            return True
        except Exception as e:
            logger.error(f"Failed to send Kafka message for row {row_index}: {e}")
            return False

    def flush(self):
        if self.producer:
            self.producer.flush()

kafka_service = KafkaService()
