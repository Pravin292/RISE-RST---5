import os
import json
import time
import logging
from kafka import KafkaConsumer
from neo4j_loader import neo4j_loader

logger = logging.getLogger("kafka_consumer")
logging.basicConfig(level=logging.INFO)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "csv-rows")

def create_consumer_with_retry(max_retries=30, delay=2):
    for attempt in range(1, max_retries + 1):
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                group_id="neo4j-loader-group",
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode("utf-8"))
            )
            logger.info(f"Kafka Consumer connected successfully to topic: {KAFKA_TOPIC}")
            return consumer
        except Exception as e:
            logger.warning(f"Attempt {attempt}/{max_retries} - Kafka broker not ready: {e}")
            time.sleep(delay)
    raise RuntimeError("Could not connect to Kafka consumer after multiple retries.")

def main():
    logger.info("Starting Kafka Loader Service...")
    consumer = create_consumer_with_retry()
    
    logger.info("Listening for messages on topic 'csv-rows'...")
    for message in consumer:
        try:
            data = message.value
            dataset_id = data.get("dataset_id")
            filename = data.get("filename")
            row_index = data.get("row_index")
            row_data = data.get("row_data", {})
            uploaded_at = data.get("uploaded_at")

            logger.info(f"Consuming row {row_index} for dataset {dataset_id} ({filename})")
            neo4j_loader.load_row(
                dataset_id=dataset_id,
                filename=filename,
                row_index=row_index,
                row_data=row_data,
                uploaded_at=uploaded_at
            )
        except Exception as e:
            logger.error(f"Error processing message offset {message.offset}: {e}")

if __name__ == "__main__":
    main()
