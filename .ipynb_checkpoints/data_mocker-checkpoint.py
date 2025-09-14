"""
AI-native PMO demo
Single-file demo that:
- Creates mock data for collaboration sources in ./mock_store
- Spins up a FastAPI mock API exposing each source
- Implements simple agent classes: DataCollectors, GrainClassifier, Summarizer, ActionExtractor, Orchestrator, Nudger
- Provides a /run_pipeline?grain=<grain_name> endpoint that runs the agent pipeline for a grain and returns the outputs

Run:
1. pip install fastapi uvicorn requests
2. python ai_pmo_demo.py
3. Open http://127.0.0.1:8000/docs to explore endpoints

This is a lightweight demo suitable for local experimentation and extension.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
import json
import time
import threading
from typing import List, Dict, Any
import requests
import re
from datetime import datetime, timedelta

# -----------------------------
# Mock data creation
# -----------------------------
MOCK_DIR = "mock_store"
if not os.path.exists(MOCK_DIR):
    os.makedirs(MOCK_DIR)

# Create mock collaboration data for multiple sources
mock_data = {
    "jira": [
        {"id": "JIRA-101", "project": "mobile-v3.2", "summary": "Login crash on Android 13", "status": "In Progress", "assignee": "alice", "updated": "2025-09-10T09:12:00"},
        {"id": "JIRA-110", "project": "mobile-v3.2", "summary": "Implement new onboarding flow", "status": "Ready for QA", "assignee": "bob", "updated": "2025-09-11T16:00:00"},
    ],
    "azure_devops": [
        {"id": "ADO-501", "project": "infra", "summary": "Update staging with DB migration", "status": "Open", "assignee": "devops", "updated": "2025-09-09T11:00:00"}
    ],
    "sharepoint": [
        {"id": "DOC-1", "project": "mobile-v3.2", "title": "Design Spec - Onboarding", "content": "Design decisions: use progressive onboarding. Pending approval from @designer.", "updated": "2025-09-08T10:00:00"}
    ],
    "confluence": [
        {"id": "CONF-7", "project": "mobile-v3.2", "title": "Release Notes Draft", "content": "v3.2: performance improvements, bug fixes. TODO: confirm analytics event names.", "updated": "2025-09-10T09:00:00"}
    ],
    "outlook": [
        {"id": "EMAIL-501", "project": "mobile-v3.2", "from": "pm@example.com", "to": ["team@example.com"], "subject": "Design approval needed", "body": "Design must be approved by Monday. @designer please confirm.", "date": "2025-09-11T08:00:00"}
    ],
    "teams": [
        {"id": "MSG-9001", "project": "mobile-v3.2", "channel": "#mobile-release", "user": "carol", "text": "I think the onboarding copy needs legal review. Action: @legal to review by 2025-09-13.", "ts": "2025-09-11T12:34:00"},
        {"id": "MSG-9002", "project": "mobile-v3.2", "channel": "#mobile-release", "user": "dave", "text": "We deployed a fix to staging. Noticed a flakey test. TODO: investigate failing e2e.", "ts": "2025-09-11T15:00:00"}
    ],
    "zoom_transcripts": [
        {"id": "ZOOM-300", "project": "mobile-v3.2", "participants": ["alice","bob","pm"], "transcript": "Alice: we will need design sign-off. Bob: I can pick it after lunch. PM: schedule a 15-min decision sync if unresolved.", "date": "2025-09-10T14:00:00"}
    ]
}

# Write mock data files
for k, v in mock_data.items():
    path = os.path.join(MOCK_DIR, f"{k}.json")
    with open(path, "w") as f:
        json.dump(v, f, indent=2)

# -----------------------------
# FastAPI mock server exposing the mock_store
# -----------------------------
mock_api = FastAPI(title="Mock Collaboration API")

@mock_api.get("/sources/{source_name}")
def read_source(source_name: str):
    path = os.path.join(MOCK_DIR, f"{source_name}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Source not found")
    with open(path) as f:
        return JSONResponse(content=json.load(f))

@mock_api.get("/sources")
def list_sources():
    files = [f.replace('.json','') for f in os.listdir(MOCK_DIR) if f.endswith('.json')]
    return {"sources": files}

# Run the mock server in a thread so main app can also run

def run_mock_api():
    uvicorn.run(mock_api, host="127.0.0.1", port=8001, log_level="warning")

mock_thread = threading.Thread(target=run_mock_api, daemon=True)
mock_thread.start()
print("mocck thread started")
# Small delay to let mock API start
time.sleep(0.8)

