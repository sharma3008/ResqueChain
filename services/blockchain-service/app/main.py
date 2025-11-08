import os
import json
import time
import hashlib
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from prometheus_client import Counter, generate_latest, start_http_server

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC_TRIAGE = "triage-results"
LEDGER_PATH = os.getenv("LEDGER_PATH", "/data/triage_ledger.json")

LOGGED_CASES = Counter("resqchain_cases_logged_total", "Total triage cases logged to ledger")

def load_ledger():
    try:
        with open(LEDGER_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_ledger(entries):
    with open(LEDGER_PATH, "w") as f:
        json.dump(entries, f)

def append_to_ledger(triage):
    entries = load_ledger()
    raw = f'{triage.get("patient_id")}{triage.get("responder_id")}{triage.get("timestamp")}{triage.get("severity_label")}'
    case_hash = hashlib.sha256(raw.encode()).hexdigest()
    entry = {"case_hash": case_hash, **triage}
    entries.append(entry)
    save_ledger(entries)
    LOGGED_CASES.inc()
    print(f"[blockchain-service] Logged case {case_hash[:10]}... severity={triage.get('severity_label')}")

def main():
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    if not os.path.exists(LEDGER_PATH):
        save_ledger([])

    # expose Prometheus metrics on :9100 inside container
    start_http_server(9100)
    print(f"[blockchain-service] Metrics on :9100")
    print(f"[blockchain-service] Connecting to Kafka at {KAFKA_BOOTSTRAP}...")

    consumer = None
    for attempt in range(1, 8):
        try:
            consumer = KafkaConsumer(
                TOPIC_TRIAGE,
                bootstrap_servers=[KAFKA_BOOTSTRAP],
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                group_id="blockchain-writer-group",
            )
            break
        except NoBrokersAvailable:
            print(f"[blockchain-service] Kafka not ready (attempt {attempt}), retrying...")
            time.sleep(2)

    if consumer is None:
        print("[blockchain-service] Failed to connect to Kafka. Exiting.")
        return

    print(f"[blockchain-service] Listening on topic={TOPIC_TRIAGE}")
    for msg in consumer:
        triage = msg.value
        append_to_ledger(triage)

if __name__ == "__main__":
    main()
