import json
import logging
import os
import time

from confluent_kafka import Consumer, KafkaError

from neo4j_loader import Neo4jLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("loader")

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "csv-rows")


def wait_for_kafka(timeout_seconds: int = 120) -> Consumer:
    deadline = time.time() + timeout_seconds
    last_exc = None
    while time.time() < deadline:
        try:
            consumer = Consumer({
                "bootstrap.servers": BOOTSTRAP_SERVERS,
                "group.id": "csv-loader-group",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            })
            metadata = consumer.list_topics(timeout=5)
            if metadata and metadata.brokers:
                logger.info("Connected to Kafka at %s", BOOTSTRAP_SERVERS)
                return consumer
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        logger.info("Waiting for Kafka ...")
        time.sleep(2)
    raise RuntimeError(f"Kafka never became reachable: {last_exc}")


def main() -> None:
    loader = Neo4jLoader()
    loader.wait_until_ready()

    consumer = wait_for_kafka()
    consumer.subscribe([TOPIC])
    logger.info("Subscribed to topic '%s'", TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error("Kafka error: %s", msg.error())
                continue

            raw_value = msg.value()
            try:
                payload = json.loads(raw_value.decode("utf-8"))
                dataset_id = payload["dataset_id"]
                row_index = payload["row_index"]
                loader.merge_row(
                    dataset_id=dataset_id,
                    filename=payload.get("filename"),
                    uploaded_at=payload.get("uploaded_at"),
                    total_rows=payload.get("total_rows", 0),
                    columns=payload.get("columns", []),
                    row_index=row_index,
                    row=payload.get("row", {}),
                )
                logger.info("Loaded row %s of dataset %s", row_index, dataset_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to process message, recording as failed row")
                try:
                    payload = json.loads(raw_value.decode("utf-8"))
                    loader.mark_row_failed(
                        payload.get("dataset_id", "unknown"),
                        payload.get("row_index", -1),
                        str(exc),
                        raw_value.decode("utf-8", errors="replace"),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Could not even record failed row")
            finally:
                consumer.commit(msg)
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        loader.close()


if __name__ == "__main__":
    main()
