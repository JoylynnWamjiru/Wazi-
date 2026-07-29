"""Development stub of the Wazi admin API — no PostgreSQL required.

Implements the endpoints in docs/api-contract.md v0.2.0 with realistic
in-memory sample data, so the Streamlit admin dashboard can be developed
and demoed on a machine without Docker/Postgres.

Run with:
    venv\\Scripts\\python.exe -m uvicorn scripts.dev_stub_api:app --port 8000

Auth matches the real API: Bearer token == ADMIN_PASSWORD (default "admin").
State is in-memory only and resets on restart.
"""

import os
from copy import deepcopy
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

app = FastAPI(title="Wazi API (dev stub)", version="0.2.0-stub")
security = HTTPBearer()


def verify_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    if credentials.credentials != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")
    return credentials.credentials


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Sample data (contract-shaped) -------------------------------------------

DISPUTES: list[dict] = [
    {
        "id": 1, "message_id": 42, "status": "pending_review",
        "reason": "The figure quoted for Keringet project is different from what I saw on the ground",
        "reported_by_user_id": 7, "reviewed_by": None, "reviewed_at": None,
        "resolution_note": None, "correction_message": None, "escalation_report": None,
        "created_at": "2026-07-26T14:30:00Z", "report_count": 3,
        "message_preview": {
            "role": "assistant",
            "text": "Kulingana na ripoti ya Mkaguzi Mkuu (ukurasa 15), mradi huu uligharimu Kshs 16,999,852...",
            "citation": "nakuru_audit_report.pdf, page 15",
        },
        "user_question": {"text": "Je, mradi wa Keringet ulikuwa na thamani ya pesa iliyotumika?"},
        "retrieved_chunks": [
            {
                "chunk_id": 28,
                "source_title": "Auditor-General's Report — Nakuru County Executive, FY 2023/24",
                "government_arm": "executive", "page_number": 15,
                "chunk_text": "...two dormitories, kitchen, dining area and a shed at a contract sum of Kshs.16,999,852 at Keringet Sports Center...",
            }
        ],
    },
    {
        "id": 2, "message_id": 55, "status": "pending_review",
        "reason": "Hii barabara haijakamilika lakini jibu linasema imelipiwa",
        "reported_by_user_id": 11, "reviewed_by": None, "reviewed_at": None,
        "resolution_note": None, "correction_message": None, "escalation_report": None,
        "created_at": "2026-07-27T09:10:00Z", "report_count": 1,
        "message_preview": {
            "role": "assistant",
            "text": "Ripoti inaonyesha malipo ya Kshs.5,703,650 kwa mradi wa maji wa Menengai na Kiamaina...",
            "citation": "nakuru_audit_report.pdf, page 10",
        },
        "user_question": {"text": "Mradi wa maji Menengai umefikia wapi?"},
        "retrieved_chunks": [
            {
                "chunk_id": 19,
                "source_title": "Auditor-General's Report — Nakuru County Executive, FY 2023/24",
                "government_arm": "executive", "page_number": 10,
                "chunk_text": "...purchase and supply of water pipes at a contract sum of Kshs.5,703,650 to Menengai and Kiamaina water projects...",
            }
        ],
    },
    {
        "id": 3, "message_id": 61, "status": "under_review",
        "reason": "Pending bills figure seems outdated",
        "reported_by_user_id": 4, "reviewed_by": "moderator", "reviewed_at": "2026-07-27T16:00:00Z",
        "resolution_note": None, "correction_message": None, "escalation_report": None,
        "created_at": "2026-07-27T12:45:00Z", "report_count": 2,
        "message_preview": {
            "role": "assistant",
            "text": "The County reported pending bills amounting to Kshs 1.44 billion...",
            "citation": "nakuru_birr_q1.pdf, page 6",
        },
        "user_question": {"text": "What did the Auditor-General find about pending bills?"},
        "retrieved_chunks": [
            {
                "chunk_id": 33,
                "source_title": "County Governments BIRR — First Quarter FY 2024/25",
                "government_arm": "consolidated", "page_number": 6,
                "chunk_text": "...The County reported pending bills amounting to Kshs 1.44 billion. The county executive's pending bills consist of Kshs.1.27 billion...",
            }
        ],
    },
]

SOURCES: list[dict] = [
    {
        "id": 1,
        "url": "https://www.oagkenya.go.ke/2023-2024-county-government-audit-reports/",
        "title": "Auditor-General's Report — Nakuru County Executive, FY 2023/24",
        "publisher": "OAG", "government_arm": "executive", "county": "nakuru",
        "report_type": "audit_report", "fiscal_year": "2023/24",
        "published_at": "2024-12-15", "last_scraped_at": "2026-07-20T08:00:00Z",
        "ingestion_status": "completed", "ingestion_error": None,
        "chunk_count": 16, "created_at": "2026-07-18T09:00:00Z",
    },
    {
        "id": 2,
        "url": "https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/",
        "title": "County Governments BIRR — First Quarter FY 2024/25",
        "publisher": "CoB", "government_arm": "consolidated", "county": "nakuru",
        "report_type": "birr", "fiscal_year": "2024/25",
        "published_at": "2024-10-30", "last_scraped_at": "2026-07-20T08:00:00Z",
        "ingestion_status": "completed", "ingestion_error": None,
        "chunk_count": 18, "created_at": "2026-07-18T09:00:00Z",
    },
    {
        "id": 3,
        "url": "https://www.oagkenya.go.ke/2024-2025-county-government-audit-reports/",
        "title": "Auditor-General's Report — Nakuru County Executive, FY 2024/25",
        "publisher": "OAG", "government_arm": "executive", "county": "nakuru",
        "report_type": "audit_report", "fiscal_year": "2024/25",
        "published_at": None, "last_scraped_at": None,
        "ingestion_status": "pending", "ingestion_error": None,
        "chunk_count": 0, "created_at": "2026-07-22T09:00:00Z",
    },
    {
        "id": 4,
        "url": "https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/",
        "title": "County Governments BIRR — First Half FY 2025/26",
        "publisher": "CoB", "government_arm": "consolidated", "county": "nakuru",
        "report_type": "birr", "fiscal_year": "2025/26",
        "published_at": None, "last_scraped_at": "2026-07-25T08:00:00Z",
        "ingestion_status": "failed",
        "ingestion_error": "Listing page returned 404 — CoB may have moved the report",
        "chunk_count": 0, "created_at": "2026-07-22T09:00:00Z",
    },
]

SESSIONS: list[dict] = [
    {"id": 5, "user_id": 12, "is_active": True, "message_count": 4,
     "first_message_at": "2026-07-27T09:00:00Z", "last_message_at": "2026-07-27T09:20:00Z",
     "created_at": "2026-07-27T09:00:00Z"},
    {"id": 4, "user_id": 7, "is_active": False, "message_count": 2,
     "first_message_at": "2026-07-26T14:00:00Z", "last_message_at": "2026-07-26T14:31:00Z",
     "created_at": "2026-07-26T14:00:00Z"},
]

MESSAGES: list[dict] = [
    {"id": 83, "session_id": 5, "role": "user",
     "text": "Kaunti ya Nakuru inapokea pesa ngapi kutoka kwa Serikali ya Kitaifa?",
     "citation": None, "created_at": "2026-07-27T09:00:10Z"},
    {"id": 84, "session_id": 5, "role": "assistant",
     "text": "Serikali ya Kaunti ya Nakuru inatarajia kupokea Kshs.14.13 bilioni kutoka kwa Serikali ya Kitaifa kama mgao wa mapato.",
     "citation": "nakuru_birr_q1.pdf, page 2", "created_at": "2026-07-27T09:00:18Z"},
    {"id": 85, "session_id": 5, "role": "user",
     "text": "What did the Auditor-General find about pending bills?",
     "citation": None, "created_at": "2026-07-27T09:15:00Z"},
    {"id": 86, "session_id": 5, "role": "assistant",
     "text": "The County reported pending bills amounting to Kshs 1.44 billion, consisting of Kshs.1.27 billion for recurrent expenditures.",
     "citation": "nakuru_birr_q1.pdf, page 6", "created_at": "2026-07-27T09:15:05Z"},
    {"id": 41, "session_id": 4, "role": "user",
     "text": "Je, mradi wa Keringet ulikuwa na thamani ya pesa iliyotumika?",
     "citation": None, "created_at": "2026-07-26T14:30:00Z"},
    {"id": 42, "session_id": 4, "role": "assistant",
     "text": "Kulingana na ripoti ya Mkaguzi Mkuu (ukurasa 15), mradi huu uligharimu Kshs 16,999,852...",
     "citation": "nakuru_audit_report.pdf, page 15", "created_at": "2026-07-26T14:30:08Z"},
]

VALID_TRANSITIONS = {
    "pending_review": {"under_review"},
    "under_review": {"resolved_valid", "resolved_invalid", "escalated"},
    "resolved_valid": set(),
    "resolved_invalid": set(),
    "escalated": {"resolved_valid", "resolved_invalid"},
}


# --- Endpoints ---------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "healthy", "service": "wazi-api-stub", "database": "in-memory", "version": "0.2.0-stub"}


@app.get("/api/stats")
def stats(token: str = Depends(verify_admin)):
    by_status: dict[str, int] = {s: 0 for s in ["pending", "in_progress", "completed", "failed"]}
    for s in SOURCES:
        by_status[s["ingestion_status"]] += 1
    d_by_status: dict[str, int] = {s: 0 for s in VALID_TRANSITIONS}
    for d in DISPUTES:
        d_by_status[d["status"]] += 1
    return {
        "total_sources": len(SOURCES),
        "sources_by_status": by_status,
        "total_chunks": sum(s["chunk_count"] for s in SOURCES),
        "total_messages": len(MESSAGES),
        "total_disputes": len(DISPUTES),
        "disputes_by_status": d_by_status,
        "last_ingestion_at": "2026-07-20T08:00:00Z",
        "oldest_source_date": "2024-10-30",
        "newest_source_date": "2024-12-15",
        "unique_citizens": 23,
        "queries_today": 12,
        "queries_this_week": 89,
    }


@app.get("/api/disputes")
def list_disputes(status: str | None = None, limit: int = 50, offset: int = 0,
                  token: str = Depends(verify_admin)):
    rows = [d for d in DISPUTES if status is None or d["status"] == status]
    rows = sorted(rows, key=lambda d: d["created_at"], reverse=True)
    page = rows[offset:offset + limit]
    listing = [
        {k: d[k] for k in ("id", "message_id", "status", "reason",
                           "reported_by_user_id", "created_at", "report_count")}
        for d in page
    ]
    return {"disputes": listing, "total": len(rows), "limit": limit, "offset": offset}


@app.get("/api/disputes/{dispute_id}")
def get_dispute(dispute_id: int, token: str = Depends(verify_admin)):
    for d in DISPUTES:
        if d["id"] == dispute_id:
            return deepcopy(d)
    raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")


@app.patch("/api/disputes/{dispute_id}")
def patch_dispute(dispute_id: int, body: dict, token: str = Depends(verify_admin)):
    dispute = next((d for d in DISPUTES if d["id"] == dispute_id), None)
    if dispute is None:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")

    new_status = body.get("status")
    if new_status not in VALID_TRANSITIONS:
        raise HTTPException(status_code=422, detail=f"Unknown status: {new_status}")
    if new_status not in VALID_TRANSITIONS[dispute["status"]]:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status transition: {dispute['status']} -> {new_status}.",
        )
    correction = body.get("correction_message")
    if correction and new_status not in ("resolved_valid", "resolved_invalid"):
        raise HTTPException(
            status_code=422,
            detail=f"correction_message is only valid when status is resolved_valid or resolved_invalid, not {new_status}.",
        )

    dispute["status"] = new_status
    dispute["resolution_note"] = body.get("resolution_note")
    dispute["reviewed_by"] = "moderator"
    dispute["reviewed_at"] = _now()

    response = {
        "id": dispute["id"], "status": new_status,
        "resolution_note": dispute["resolution_note"],
        "reviewed_by": "moderator", "reviewed_at": dispute["reviewed_at"],
    }
    if correction:
        dispute["correction_message"] = correction
        response["correction_message"] = correction
        response["correction_sent"] = True
    if new_status == "escalated":
        report = {
            "dispute_id": dispute["id"], "generated_at": _now(),
            "recipient": body.get("escalation_recipient", ""),
            "content": {
                "disputed_answer": dispute["message_preview"]["text"],
                "citation": dispute["message_preview"]["citation"],
                "user_question": dispute["user_question"]["text"],
                "retrieved_chunks": [c["chunk_text"] for c in dispute["retrieved_chunks"]],
                "citizen_report": dispute["reason"],
                "moderator_note": dispute["resolution_note"],
            },
        }
        dispute["escalation_report"] = report
        response["escalation_report"] = report
    return response


@app.get("/api/sources")
def list_sources(county: str | None = None, government_arm: str | None = None,
                 report_type: str | None = None, ingestion_status: str | None = None,
                 fiscal_year: str | None = None, token: str = Depends(verify_admin)):
    rows = SOURCES
    for field, value in [("county", county), ("government_arm", government_arm),
                         ("report_type", report_type), ("ingestion_status", ingestion_status),
                         ("fiscal_year", fiscal_year)]:
        if value is not None:
            rows = [s for s in rows if s[field] == value]
    return {"sources": deepcopy(rows), "total": len(rows)}


@app.post("/api/sources", status_code=201)
def create_source(body: dict, token: str = Depends(verify_admin)):
    required = ["url", "title", "publisher", "government_arm", "county", "report_type"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(missing)}")
    source = {
        "id": max(s["id"] for s in SOURCES) + 1,
        **{f: body.get(f) for f in required},
        "fiscal_year": body.get("fiscal_year"),
        "published_at": None, "last_scraped_at": None,
        "ingestion_status": "pending", "ingestion_error": None,
        "chunk_count": 0, "created_at": _now(),
    }
    SOURCES.append(source)
    return deepcopy(source)


@app.get("/api/sources/{source_id}")
def get_source(source_id: int, token: str = Depends(verify_admin)):
    for s in SOURCES:
        if s["id"] == source_id:
            return deepcopy(s)
    raise HTTPException(status_code=404, detail=f"Source {source_id} not found")


@app.patch("/api/sources/{source_id}")
def patch_source(source_id: int, body: dict, token: str = Depends(verify_admin)):
    source = next((s for s in SOURCES if s["id"] == source_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    editable = ["url", "title", "publisher", "government_arm", "county", "report_type", "fiscal_year"]
    for field in editable:
        if field in body:
            source[field] = body[field]
    return deepcopy(source)


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int, token: str = Depends(verify_admin)):
    source = next((s for s in SOURCES if s["id"] == source_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    if source["ingestion_status"] == "in_progress":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete source {source_id} while ingestion is in progress.",
        )
    SOURCES.remove(source)
    return {"deleted": True, "source_id": source_id, "chunks_deleted": source["chunk_count"]}


@app.post("/api/sources/{source_id}/ingest", status_code=202)
def ingest_source(source_id: int, token: str = Depends(verify_admin)):
    source = next((s for s in SOURCES if s["id"] == source_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    if source["ingestion_status"] == "in_progress":
        raise HTTPException(
            status_code=409,
            detail=f"Source {source_id} is already being ingested (status: in_progress)",
        )
    source["ingestion_status"] = "in_progress"
    return {
        "source_id": source_id, "ingestion_status": "in_progress",
        "message": "Ingestion started. Check status via GET /api/sources/{source_id}.",
    }


@app.get("/api/sessions")
def list_sessions(limit: int = 20, offset: int = 0, is_active: bool | None = None,
                  token: str = Depends(verify_admin)):
    rows = [s for s in SESSIONS if is_active is None or s["is_active"] == is_active]
    rows = sorted(rows, key=lambda s: s["last_message_at"], reverse=True)
    return {"sessions": deepcopy(rows[offset:offset + limit]),
            "total": len(rows), "limit": limit, "offset": offset}


@app.get("/api/messages")
def list_messages(limit: int = 20, offset: int = 0, session_id: int | None = None,
                  token: str = Depends(verify_admin)):
    rows = MESSAGES
    if session_id is not None:
        if not any(s["id"] == session_id for s in SESSIONS):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        rows = [m for m in rows if m["session_id"] == session_id]
    rows = sorted(rows, key=lambda m: m["created_at"])
    return {"messages": deepcopy(rows[offset:offset + limit]),
            "total": len(rows), "limit": limit, "offset": offset}
