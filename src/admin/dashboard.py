"""Wazi — authenticated Streamlit admin dashboard.

Consumes the FastAPI admin API per docs/api-contract.md v0.2.0.

Run with:
    streamlit run src/admin/dashboard.py --server.port 8502

Environment:
    WAZI_API_URL — base URL of the FastAPI backend (default http://localhost:8000)

The login password is the backend's ADMIN_PASSWORD: the dashboard validates it
by calling the API, so it needs no local copy of the secret.
"""

import json
import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("WAZI_API_URL", "http://localhost:8000").rstrip("/")

# Split connect vs read timeouts. A short connect timeout fails fast when the
# host is genuinely unreachable (DNS/down), while a long read timeout survives a
# cold start: Render's free tier spins the backend down after ~15 min idle and
# takes ~50s to wake on the next request. A single 15s timeout can't tell the
# two apart and times out mid-wake. Overridable via WAZI_API_READ_TIMEOUT.
_READ_TIMEOUT = float(os.getenv("WAZI_API_READ_TIMEOUT", "60"))
API_TIMEOUT = httpx.Timeout(connect=10.0, read=_READ_TIMEOUT, write=10.0, pool=10.0)
# The login probe is the request most likely to hit a cold backend, so give it
# extra read headroom.
WAKE_TIMEOUT = httpx.Timeout(connect=10.0, read=max(_READ_TIMEOUT, 90.0), write=10.0, pool=10.0)

DISPUTE_TRANSITIONS: dict[str, list[str]] = {
    "pending_review": ["under_review"],
    "under_review": ["resolved_valid", "resolved_invalid", "escalated"],
    "resolved_valid": [],
    "resolved_invalid": [],
    "escalated": ["resolved_valid", "resolved_invalid"],
}
STATUS_BADGES = {
    "pending_review": "🟠 pending_review",
    "under_review": "🔵 under_review",
    "resolved_valid": "🟢 resolved_valid",
    "resolved_invalid": "⚪ resolved_invalid",
    "escalated": "🔴 escalated",
}


def _dispute_badge(d: dict) -> str:
    """Badge for a dispute entry; visually downgrade sub-threshold reports."""
    if d.get("status") == "pending_review" and not d.get("flagged_for_review", False):
        return "🟡 awaiting_more_reports"
    return STATUS_BADGES.get(d.get("status", ""), d.get("status", ""))

# Mirror of the GovernmentArm / ReportType enums in src/shared/models.py, which
# are the source of truth. Duplicated rather than imported because this
# dashboard talks to the API over HTTP only — importing models.py would drag in
# SQLAlchemy and pgvector and break the Postgres-free dev flow. Keep these in
# step with models.py AND docs/api-contract.md §10 when an enum value is added.
GOVERNMENT_ARMS = ["executive", "assembly", "consolidated", "revenue"]
REPORT_TYPES = ["audit_report", "birr", "exchequer", "cbrop", "programme_budget"]

# Sidebar navigation — one page at a time in the main area (cleaner than five
# tabs side-by-side; the demo's human-verification loop lives on Disputes).
PAGES = ["Overview", "Disputes", "Sources", "Sessions", "Validation"]
PAGE_ICONS = {
    "Overview": "📊",
    "Disputes": "🚩",
    "Sources": "📚",
    "Sessions": "💬",
    "Validation": "🗣️",
}

st.set_page_config(page_title="Wazi Admin", page_icon="🛡️", layout="wide")


# --- API client --------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.get('admin_token', '')}"}


def api_request(method: str, path: str, **kwargs) -> dict | None:
    """Call the admin API. Returns parsed JSON, or None after showing an error."""
    try:
        response = httpx.request(
            method, f"{API_URL}{path}", headers=_headers(), timeout=API_TIMEOUT, **kwargs
        )
    except httpx.HTTPError as exc:
        st.error(f"API unreachable at {API_URL} — {type(exc).__name__}. Is the backend running?")
        return None

    if response.status_code == 401:
        st.session_state.pop("admin_token", None)
        st.error("Session expired or invalid token — please log in again.")
        st.rerun()
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:  # noqa: BLE001
            detail = response.text
        st.error(f"API error {response.status_code}: {detail}")
        return None
    return response.json()


# --- Login gate --------------------------------------------------------------

if "admin_token" not in st.session_state:
    st.title("🛡️ Wazi Admin")
    st.caption("Moderation & corpus dashboard — authorized team members only.")
    with st.form("login"):
        password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        try:
            with st.spinner(
                "Inaamsha seva... _(waking the backend — the first request "
                "after it's been idle can take up to a minute on Render's free tier)_"
            ):
                probe = httpx.get(
                    f"{API_URL}/api/stats",
                    headers={"Authorization": f"Bearer {password}"},
                    timeout=WAKE_TIMEOUT,
                )
        except httpx.HTTPError as exc:
            st.error(f"API unreachable at {API_URL} — {type(exc).__name__}. Is the backend running?")
            st.stop()
        if probe.status_code == 200:
            st.session_state["admin_token"] = password
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


# --- Sidebar -----------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🛡️ Wazi Admin")
    page = st.radio(
        "Navigate",
        PAGES,
        format_func=lambda p: f"{PAGE_ICONS[p]} {p}",
        label_visibility="collapsed",
    )
    st.divider()
    try:
        health = httpx.get(f"{API_URL}/health", timeout=5.0).json()
        st.success(f"API healthy · {health.get('service', '?')}")
    except httpx.HTTPError:
        st.error(f"API offline · {API_URL}")
    st.caption(f"Backend: `{API_URL}`")
    if st.button("Log out", use_container_width=True):
        st.session_state.pop("admin_token", None)
        st.rerun()

st.title("🛡️ Wazi Admin")


# --- Overview ----------------------------------------------------------------

if page == "Overview":
    stats = api_request("GET", "/api/stats")
    if stats:
        row1 = st.columns(4)
        row1[0].metric("Sources", stats["total_sources"])
        row1[1].metric("Chunks", stats["total_chunks"])
        row1[2].metric("Messages", stats["total_messages"])
        row1[3].metric("Disputes", stats["total_disputes"])
        row2 = st.columns(4)
        row2[0].metric("Unique citizens", stats["unique_citizens"])
        row2[1].metric("Queries today", stats["queries_today"])
        row2[2].metric("Queries this week", stats["queries_this_week"])
        row2[3].metric(
            "Pending disputes", stats["disputes_by_status"].get("pending_review", 0)
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Disputes by status**")
            st.table(
                [{"status": k, "count": v} for k, v in stats["disputes_by_status"].items()]
            )
        with col_b:
            st.markdown("**Sources by ingestion status**")
            st.table(
                [{"status": k, "count": v} for k, v in stats["sources_by_status"].items()]
            )
        st.caption(
            f"Last ingestion: {stats.get('last_ingestion_at') or 'never'} · "
            f"Source dates: {stats.get('oldest_source_date') or '—'} → "
            f"{stats.get('newest_source_date') or '—'}"
        )


# --- Disputes (moderation queue) ---------------------------------------------

if page == "Disputes":
    queue_col, status_col, _ = st.columns([1, 1, 2])
    with queue_col:
        queue_filter = st.selectbox(
            "Queue",
            ["Flagged", "All", "Awaiting more"],
            key="dispute_queue_filter",
        )
    with status_col:
        status_filter = st.selectbox(
            "Status",
            ["(all)"] + list(DISPUTE_TRANSITIONS),
            key="dispute_filter",
        )
    params = {}
    if queue_filter == "Flagged":
        params["flagged"] = "true"
    elif queue_filter == "Awaiting more":
        params["flagged"] = "false"
    if status_filter != "(all)":
        params["status"] = status_filter
    listing = api_request("GET", "/api/disputes", params=params)

    if listing and listing["disputes"]:
        st.caption(f"{listing['total']} dispute(s)")
        options = {
            f"#{d['id']} · {_dispute_badge(d)} · "
            f"{d['report_count']} report(s) · {d['reason'][:70]}": d["id"]
            for d in listing["disputes"]
        }
        choice = st.selectbox("Open dispute", list(options), key="dispute_choice")
        dispute = api_request("GET", f"/api/disputes/{options[choice]}")

        if dispute:
            left, right = st.columns([3, 2])
            with left:
                st.markdown(f"**Status:** {_dispute_badge(dispute)}"
                            f" &nbsp;·&nbsp; **Reports:** {dispute['report_count']}")
                st.markdown("**Citizen's question**")
                st.info(dispute["user_question"]["text"])
                st.markdown("**Disputed answer**")
                st.warning(dispute["message_preview"]["text"])
                st.caption(f"📄 {dispute['message_preview']['citation']}")
                st.markdown("**Dispute reason**")
                st.write(dispute["reason"])
                with st.expander("Retrieved source passages (what the AI was shown)"):
                    if dispute["retrieved_chunks"]:
                        for chunk in dispute["retrieved_chunks"]:
                            st.markdown(
                                f"**{chunk['source_title']}** · p{chunk['page_number']} "
                                f"· `{chunk['government_arm']}`"
                            )
                            st.text(chunk["chunk_text"])
                    else:
                        st.info(
                            "Source passages aren't captured for this dispute yet — "
                            "retrieval provenance isn't wired into the dispute flow."
                        )
                if dispute.get("resolution_note"):
                    st.markdown("**Resolution note**")
                    st.write(dispute["resolution_note"])
                if dispute.get("correction_message"):
                    st.markdown("**Correction sent to citizen**")
                    st.success(dispute["correction_message"])
                if dispute.get("escalation_report"):
                    with st.expander("Escalation report (send manually to recipient)"):
                        st.json(dispute["escalation_report"])

            with right:
                st.markdown("**Moderation action**")
                allowed = DISPUTE_TRANSITIONS.get(dispute["status"], [])
                if not allowed:
                    st.info("This dispute is resolved — no further transitions.")
                else:
                    with st.form(f"action_{dispute['id']}"):
                        new_status = st.selectbox("New status", allowed)
                        note = st.text_area("Resolution note")
                        correction = st.text_area(
                            "Correction message (optional — sent to the citizen via WhatsApp; "
                            "only for resolved_* statuses)",
                        )
                        recipient = st.text_input(
                            "Escalation recipient email (only for escalated)",
                        )
                        do_it = st.form_submit_button("Apply")
                    if do_it:
                        body: dict = {"status": new_status}
                        if note.strip():
                            body["resolution_note"] = note.strip()
                        if correction.strip():
                            body["correction_message"] = correction.strip()
                        if recipient.strip():
                            body["escalation_recipient"] = recipient.strip()
                        result = api_request(
                            "PATCH", f"/api/disputes/{dispute['id']}", json=body
                        )
                        if result:
                            if result.get("correction_sent"):
                                st.success("Status updated — correction sent to citizen.")
                            elif result.get("escalation_report"):
                                st.success("Escalated — report generated below.")
                                st.json(result["escalation_report"])
                            else:
                                st.success("Status updated.")
                            st.rerun()
    elif listing:
        st.info("No disputes match this filter. 🎉")


# --- Sources (registry) ------------------------------------------------------

if page == "Sources":
    sources = api_request("GET", "/api/sources")
    if sources:
        st.caption(f"{sources['total']} source(s) in the registry")
        st.dataframe(
            [
                {
                    "id": s["id"], "title": s["title"], "publisher": s["publisher"],
                    "arm": s["government_arm"], "type": s["report_type"],
                    "FY": s.get("fiscal_year") or "—",
                    "status": s["ingestion_status"], "chunks": s["chunk_count"],
                    "error": s.get("ingestion_error") or "",
                }
                for s in sources["sources"]
            ],
            use_container_width=True,
            hide_index=True,
        )

        manage_col, add_col = st.columns(2)

        with manage_col:
            st.markdown("**Manage a source**")
            ids = {f"#{s['id']} · {s['title'][:60]}": s["id"] for s in sources["sources"]}
            if ids:
                picked = st.selectbox("Source", list(ids), key="source_pick")
                source_id = ids[picked]
                action_cols = st.columns(3)
                if action_cols[0].button("▶ Trigger ingestion", key="ingest_btn"):
                    result = api_request("POST", f"/api/sources/{source_id}/ingest")
                    if result:
                        st.success(result["message"])
                        st.rerun()
                confirm = action_cols[2].checkbox("confirm", key="del_confirm")
                if action_cols[1].button("🗑 Delete", key="del_btn"):
                    if not confirm:
                        st.warning("Tick 'confirm' first — deletion cascades to all chunks.")
                    else:
                        result = api_request("DELETE", f"/api/sources/{source_id}")
                        if result:
                            st.success(
                                f"Deleted source {result['source_id']} "
                                f"({result['chunks_deleted']} chunks removed)."
                            )
                            st.rerun()
                with st.expander("Edit metadata"):
                    current = next(
                        s for s in sources["sources"] if s["id"] == source_id
                    )
                    with st.form(f"edit_{source_id}"):
                        new_title = st.text_input("Title", value=current["title"])
                        new_fy = st.text_input("Fiscal year", value=current.get("fiscal_year") or "")
                        save = st.form_submit_button("Save")
                    if save:
                        result = api_request(
                            "PATCH", f"/api/sources/{source_id}",
                            json={"title": new_title, "fiscal_year": new_fy or None},
                        )
                        if result:
                            st.success("Metadata updated.")
                            st.rerun()

        with add_col:
            st.markdown("**Register a new source**")
            with st.form("new_source"):
                url = st.text_input("Listing page URL")
                title = st.text_input("Title")
                publisher = st.text_input("Publisher (e.g. OAG, CoB)")
                arm = st.selectbox("Government arm", GOVERNMENT_ARMS)
                rtype = st.selectbox("Report type", REPORT_TYPES)
                county = st.text_input("County slug", value="nakuru")
                fy = st.text_input("Fiscal year (optional, e.g. 2025/26)")
                create = st.form_submit_button("Register")
            if create:
                body = {
                    "url": url, "title": title, "publisher": publisher,
                    "government_arm": arm, "report_type": rtype, "county": county,
                }
                if fy.strip():
                    body["fiscal_year"] = fy.strip()
                result = api_request("POST", "/api/sources", json=body)
                if result:
                    st.success(f"Registered source #{result['id']} (status: pending).")
                    st.rerun()


# --- Sessions (conversation browser) -----------------------------------------

if page == "Sessions":
    sessions = api_request("GET", "/api/sessions")
    if sessions and sessions["sessions"]:
        st.caption(
            f"{sessions['total']} session(s) — user ids are salted hashes, never phone numbers"
        )
        labels = {
            f"Session #{s['id']} · user {s['user_id']} · {s['message_count']} msg · "
            f"last {s['last_message_at'][:16]}": s["id"]
            for s in sessions["sessions"]
        }
        picked = st.selectbox("Open transcript", list(labels), key="session_pick")
        transcript = api_request(
            "GET", "/api/messages", params={"session_id": labels[picked], "limit": 100}
        )
        if transcript:
            for message in transcript["messages"]:
                with st.chat_message("user" if message["role"] == "user" else "assistant"):
                    st.markdown(message["text"])
                    if message.get("citation"):
                        st.caption(f"📄 {message['citation']}")
    elif sessions:
        st.info("No sessions yet.")


# --- Validation (placeholder) ------------------------------------------------

if page == "Validation":
    st.info(
        "Linguist validation (contract §5) is not implemented in the API yet — "
        "planned for Week 4 alongside prompt tuning. This tab will list answers "
        "for tone/register/grounding review once `/api/validation/*` lands."
    )
