import json
import time
import os
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable
from prometheus_client import Counter, start_http_server

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC_SOS = "sos-events"
TOPIC_TRIAGE = "triage-results"

TRIAGE_TOTAL = Counter(
    "resqchain_triage_total",
    "Total triage decisions"
)
TRIAGE_BY_SEVERITY = Counter(
    "resqchain_triage_by_severity_total",
    "Triage decisions by severity",
    ["severity"]
)

def compute_severity(vitals, incident_type: str):
    hr = vitals.get("heart_rate", 0)
    spo2 = vitals.get("spo2", 100)
    sys_bp = vitals.get("systolic_bp", 120)

    score = 0.0
    if spo2 < 90:
        score += 0.5
    if hr < 40 or hr > 130:
        score += 0.3
    if sys_bp < 90:
        score += 0.3
    if incident_type.lower() in ["cardiac_arrest", "major_accident"]:
        score += 0.4

    score = min(score, 1.0)

    if score >= 0.8:
        label = "CRITICAL"
    elif score >= 0.5:
        label = "HIGH"
    elif score >= 0.2:
        label = "MEDIUM"
    else:
        label = "LOW"

    return float(score), label

def main():
    print(f"[ai-triage] Connecting to Kafka at {KAFKA_BOOTSTRAP}...")

    # expose metrics on :9101
    start_http_server(9101)
    print("[ai-triage] Metrics on :9101")

    consumer = None
    for attempt in range(1, 8):
        try:
            consumer = KafkaConsumer(
                TOPIC_SOS,
                bootstrap_servers=[KAFKA_BOOTSTRAP],
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                group_id="ai-triage-group",
            )
            break
        except NoBrokersAvailable:
            print(f"[ai-triage] Kafka not ready (attempt {attempt}), retrying...")
            time.sleep(2)

    if consumer is None:
        print("[ai-triage] Failed to connect to Kafka. Exiting.")
        return

    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP],
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    print("[ai-triage] Listening for SOS events...")
    for msg in consumer:
        event = msg.value
        vitals = event.get("vitals", {})
        incident_type = event.get("incident_type", "unknown")
        score, label = compute_severity(vitals, incident_type)

        triage = {
            "patient_id": event.get("patient_id"),
            "responder_id": event.get("responder_id"),
            "location": event.get("location"),
            "incident_type": incident_type,
            "severity_score": score,
            "severity_label": label,
            "timestamp": int(time.time()),
        }

        TRIAGE_TOTAL.inc()
        TRIAGE_BY_SEVERITY.labels(label).inc()

        print(f"[ai-triage] Processed event -> {triage}")
        producer.send(TOPIC_TRIAGE, triage)
        producer.flush()

if __name__ == "__main__":
    main()
