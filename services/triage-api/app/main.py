import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Any

LEDGER_PATH = os.getenv("LEDGER_PATH", "/data/triage_ledger.json")

app = FastAPI(title="ResQChain Triage API")

# Allow frontend (localhost:5173) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_ledger() -> List[dict]:
    try:
        with open(LEDGER_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Ledger file corrupted")

@app.get("/health")
def health():
    return {"status": "ok", "service": "triage-api"}

@app.get("/api/triage")
def get_triage_cases() -> Any:
    entries = load_ledger()
    entries_sorted = sorted(entries, key=lambda e: e.get("timestamp", 0), reverse=True)
    return {"count": len(entries_sorted), "items": entries_sorted}
