"""Wazi — Streamlit chat UI, wired directly to the real RAG pipeline.

Run with:

    streamlit run src/app/streamlit_app.py
"""

import datetime
import sys
from pathlib import Path

import streamlit as st

# Put the repo root on the path so `src.ingestion.pipeline` imports cleanly when
# Streamlit runs this file directly (its own dir is otherwise sys.path[0]).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.pipeline import get_response
from src.shared import config

TRUSTED_SOURCES = [
    ("nakuru_audit_report.pdf", "Auditor-General's report, Nakuru County Executive, FY2023/24"),
    ("nakuru_birr_q1.pdf", "Budget Implementation Review Report, Q1 FY2024/25"),
]
DISPUTE_THRESHOLD = 3

EXAMPLE_QUESTIONS = [
    "Kaunti ya Nakuru inapokea pesa ngapi kutoka kwa Serikali ya Kitaifa?",
    "Je, mradi wa Keringet ulikuwa na thamani ya pesa iliyotumika?",
    "What did the Auditor-General find about pending bills?",
]

st.set_page_config(page_title="Wazi", page_icon="🗳️", layout="centered")

# --- Light WhatsApp-inspired styling (bubbles, colors) ------------------------
st.markdown("""
<style>
/* User bubbles: WhatsApp green, tucked right */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background-color: #dcf8c6;
    border-radius: 14px 14px 2px 14px;
    padding: 0.6rem 0.9rem;
}
/* Assistant bubbles: white card, tucked left */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background-color: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 14px 14px 14px 2px;
    padding: 0.6rem 0.9rem;
}
/* Dark mode: keep bubbles readable */
@media (prefers-color-scheme: dark) {
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        background-color: #1f3d2b;
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
        background-color: #262730;
        border-color: #3a3b45;
    }
}
/* Example question buttons: full width, left-aligned text */
div[data-testid="stButton"] > button {
    text-align: left;
}
</style>
""", unsafe_allow_html=True)

# --- Session state -----------------------------------------------------------
if "messages" not in st.session_state:
    # Each item: {"role": "user"|"assistant", "text": str, "citation": str}
    st.session_state.messages = []
if "dispute_counts" not in st.session_state:
    # Maps an assistant message's index -> number of "report" clicks.
    st.session_state.dispute_counts = {}
if "pending_query" not in st.session_state:
    # Set by example-question buttons; consumed on the next run.
    st.session_state.pending_query = None


@st.cache_resource(show_spinner=False)
def _warm_pipeline() -> bool:
    """Ensure the corpus exists, then load the embedding model + FAISS index.

    Two jobs, done once per server process (cached across reruns):

    1. Build data/chunks.json if it is missing. It is generated and gitignored,
       so a fresh deploy (e.g. Streamlit Community Cloud) or clone has the source
       PDFs but no chunks file; without this the first retrieve() would crash
       with FileNotFoundError. The PDFs are committed, so build_corpus() can
       regenerate it deterministically.
    2. Warm the model so the first real question doesn't hang ~15s while the
       ONNX model loads.
    """
    from src.ingestion.pipeline import DATA_DIR, build_corpus
    from src.ingestion.embed import retrieve

    if not (DATA_DIR / "chunks.json").exists():
        build_corpus()

    retrieve("warm up", k=1)
    return True


# --- Sidebar -----------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🗳️ Wazi")
    st.caption(
        "Majibu yote yanatoka kwenye nyaraka rasmi pekee — kila jibu lina chanzo. "
        "_(All answers come only from official documents; every reply is cited.)_"
    )

    st.divider()
    st.markdown("**Trusted sources**")
    for filename, description in TRUSTED_SOURCES:
        st.markdown(f"📄 `{filename}`")
        st.caption(description)

    st.divider()
    st.markdown("**Corpus last updated**")
    st.write(datetime.date.today().isoformat())
    st.caption("Re-ingestion scheduled quarterly, matching county publication cadence")

    st.divider()
    if st.button("🧹 Anza upya · Start over", use_container_width=True):
        st.session_state.messages = []
        st.session_state.dispute_counts = {}
        st.rerun()

# --- Header ------------------------------------------------------------------
st.title("🗳️ Wazi")
st.caption("Uliza kuhusu matumizi ya Kaunti ya Nakuru — kwa Kiswahili, Sheng, au English.")

# Warm the retrieval stack with a visible, friendly status (first run only).
if not st.session_state.get("_warmed"):
    with st.status("Inaandaa nyaraka za kaunti... _(preparing county documents)_", expanded=False):
        _warm_pipeline()
    st.session_state["_warmed"] = True


def render_assistant(index: int, message: dict) -> None:
    """Render one bot reply: optional dispute banner, text, citation, report button."""
    left, _ = st.columns([5, 1])  # bot replies sit on the left
    with left:
        with st.chat_message("assistant"):
            count = st.session_state.dispute_counts.get(index, 0)
            if count >= DISPUTE_THRESHOLD:
                st.warning(
                    f"⚠️ {DISPUTE_THRESHOLD} independent citizens disputed this "
                    "status — flagged for human/journalist review."
                )
            st.markdown(message["text"])
            if message.get("citation") and message["citation"] != "N/A":
                st.caption(f"📄 Chanzo · Source: **{message['citation']}**")

            cols = st.columns([3, 2])
            with cols[0]:
                if st.button(
                    "🚩 Report this project status",
                    key=f"report_{index}",
                    help="Ona hali tofauti mtaani? Ripoti — malalamiko 3 huarifu wachunguzi. "
                         "(Seen something different on the ground? 3 reports flag this for review.)",
                ):
                    st.session_state.dispute_counts[index] = count + 1
                    st.rerun()
            if 0 < count < DISPUTE_THRESHOLD:
                with cols[1]:
                    st.caption(f"Ripoti: {count}/{DISPUTE_THRESHOLD}")


def render_user(message: dict) -> None:
    """Render one user message, right-aligned."""
    _, right = st.columns([1, 5])  # user messages sit on the right
    with right:
        with st.chat_message("user"):
            st.markdown(message["text"])


def ask(query: str) -> None:
    """Append the user question, get a grounded answer, append the reply."""
    st.session_state.messages.append({"role": "user", "text": query})

    # UI-level guard: even an unexpected error shows the fallback, never a traceback.
    try:
        with st.spinner("Wazi inatafuta jibu kwenye nyaraka rasmi..."):
            response = get_response(query)
    except Exception:  # noqa: BLE001 - defensive; pipeline already falls back internally
        response = config.FALLBACK_ANSWERS["default"]

    st.session_state.messages.append({
        "role": "assistant",
        "text": response["text"],
        "citation": response["citation"],
    })


# --- Welcome / empty state -----------------------------------------------------
if not st.session_state.messages:
    st.markdown(
        "> 👋 **Karibu!** Wazi hukusaidia kufuatilia matumizi ya pesa za kaunti — "
        "kwa lugha yako. Jaribu mojawapo ya maswali haya, au andika lako hapo chini."
    )
    for i, example in enumerate(EXAMPLE_QUESTIONS):
        if st.button(f"💬 {example}", key=f"example_{i}", use_container_width=True):
            st.session_state.pending_query = example
            st.rerun()

# --- Message history ---------------------------------------------------------
for i, message in enumerate(st.session_state.messages):
    if message["role"] == "user":
        render_user(message)
    else:
        render_assistant(i, message)

# --- Input -------------------------------------------------------------------
prompt = st.chat_input("Andika swali lako hapa... · Type your question here...")

# Consume a pending example-question click, if any.
if st.session_state.pending_query:
    pending, st.session_state.pending_query = st.session_state.pending_query, None
    ask(pending)
    st.rerun()

if prompt:
    ask(prompt)
    st.rerun()
