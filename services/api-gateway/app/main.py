import os
import json
import time
import requests
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Dict, Any, Optional
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
import jwt
from jwt import algorithms
from prometheus_client import Counter, generate_latest
from fastapi.responses import PlainTextResponse

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "").strip()
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "").strip()
AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/" if AUTH0_DOMAIN else ""
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC_SOS = "sos-events"

app = FastAPI(title="ResQChain API Gateway")

producer: Optional[KafkaProducer] = None

# Prometheus metrics
SOS_REQUESTS = Counter("resqchain_sos_requests_total", "Total SOS requests received")
SOS_PUBLISHED = Counter("resqchain_sos_published_total", "Total SOS events published to Kafka")
SOS_PUBLISH_ERRORS = Counter("resqchain_sos_publish_errors_total", "Failed SOS Kafka publishes")


class SOSRequest(BaseModel):
    patient_id: str
    heart_rate: float
    spo2: float
    systolic_bp: float
    diastolic_bp: float
    location_lat: float
    location_lon: float
    incident_type: str


def get_jwks() -> Dict[str, Any]:
    url = f"{AUTH0_ISSUER}.well-known/jwks.json"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()


def verify_jwt_optional(
    auth_header: Optional[str] = Header(default=None, alias="Authorization")
) -> Dict[str, Any]:
    """
    If AUTH0_* is set:
      - Require valid Auth0 RS256 JWT.
    If not:
      - Return dev identity (no enforcement) for local/demo usage.
    """
    if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
        return {"sub": "dev-user", "mode": "no-auth0-dev"}

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ", 1)[1].strip()
    jwks = get_jwks()
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")

    key_data = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    if not key_data:
        raise HTTPException(status_code=401, detail="Invalid token key")

    public_key = algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
            issuer=AUTH0_ISSUER,
        )
        return payload
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {e}")


def get_producer() -> KafkaProducer:
    """Lazy + retrying Kafka producer so gateway doesn't crash on startup."""
    global producer
    if producer is not None:
        return producer

    last_err = None
    for attempt in range(1, 8):
        try:
            p = KafkaProducer(
                bootstrap_servers=[KAFKA_BOOTSTRAP],
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            producer = p
            print(f"[api-gateway] Connected to Kafka at {KAFKA_BOOTSTRAP}")
            return producer
        except NoBrokersAvailable as e:
            last_err = e
            print(f"[api-gateway] Kafka not ready (attempt {attempt}), retrying...")
            time.sleep(2)

    raise HTTPException(status_code=500, detail=f"Kafka not available: {last_err}")


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "api-gateway",
        "auth0_enabled": bool(AUTH0_DOMAIN and AUTH0_AUDIENCE),
        "kafka_bootstrap": KAFKA_BOOTSTRAP,
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"))


@app.post("/api/sos")
def create_sos(req: SOSRequest, user=Depends(verify_jwt_optional)):
    SOS_REQUESTS.inc()
    p = get_producer()

    event = {
        "patient_id": req.patient_id,
        "vitals": {
            "heart_rate": req.heart_rate,
            "spo2": req.spo2,
            "systolic_bp": req.systolic_bp,
            "diastolic_bp": req.diastolic_bp,
        },
        "location": {
            "lat": req.location_lat,
            "lon": req.location_lon,
        },
        "incident_type": req.incident_type,
        "responder_id": user.get("sub", "unknown"),
    }

    try:
        p.send(TOPIC_SOS, event)
        p.flush()
        SOS_PUBLISHED.inc()
    except Exception as e:
        SOS_PUBLISH_ERRORS.inc()
        raise HTTPException(status_code=500, detail=f"Failed to publish event: {e}")

    return {
        "status": "queued",
        "severity": "pending_triage",
        "event": event,
    }
