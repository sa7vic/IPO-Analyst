"""
Streamlit Frontend — DRHP Analyst Agent
"Read the 600 pages so you don't have to"
"""

import streamlit as st
import requests
import time
import json
import os
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DRHP Analyst Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;600&family=IBM+Plex+Mono:wght@400;600&display=swap');

  html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
  code, .stCode { font-family: 'IBM Plex Mono', monospace; }

  .main-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
    padding: 2rem; border-radius: 12px; margin-bottom: 1.5rem;
    border-left: 4px solid #3b82f6;
  }
  .main-header h1 { color: #f1f5f9; margin: 0; font-size: 1.8rem; font-weight: 600; }
  .main-header p  { color: #94a3b8; margin: 0.5rem 0 0; font-size: 0.95rem; }

  .flag-card {
    border-radius: 8px; padding: 1rem 1.2rem;
    margin-bottom: 0.75rem; border-left: 4px solid;
  }
  .flag-CRITICAL { background: #2d0a0a; border-color: #FF3B30; }
  .flag-HIGH     { background: #2d1a0a; border-color: #FF9500; }
  .flag-MEDIUM   { background: #2d2a0a; border-color: #FFCC00; }
  .flag-LOW      { background: #0a2d12; border-color: #34C759; }
  .flag-CLEAR    { background: #0a2d12; border-color: #30D158; }
  .flag-UNKNOWN  { background: #1a1a2d; border-color: #8E8E93; }

  .severity-badge {
    display: inline-block; padding: 2px 10px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em;
  }
  .badge-CRITICAL { background: #FF3B30; color: white; }
  .badge-HIGH     { background: #FF9500; color: white; }
  .badge-MEDIUM   { background: #FFCC00; color: #000; }
  .badge-LOW      { background: #34C759; color: white; }
  .badge-CLEAR    { background: #30D158; color: white; }
  .badge-UNKNOWN  { background: #8E8E93; color: white; }

  .source-chip {
    display: inline-block; background: #1e293b; color: #94a3b8;
    padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;
    margin: 2px; font-family: 'IBM Plex Mono', monospace;
  }
  .answer-box {
    background: #0f172a; border: 1px solid #1e293b;
    border-radius: 8px; padding: 1.2rem; margin-top: 0.5rem;
  }
  .stButton > button {
    background: #3b82f6; color: white; border: none;
    border-radius: 6px; font-weight: 600;
  }
  .stButton > button:hover { background: #2563eb; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def api_get(path):
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=30)
        return r.json() if r.ok else None
    except Exception:
        return None


def api_post(path, **kwargs):
    try:
        r = requests.post(f"{API_BASE}{path}", timeout=120, **kwargs)
        return r.json() if r.ok else {"error": r.text}
    except Exception as e:
        return {"error": str(e)}


def severity_badge(sev):
    return f'<span class="severity-badge badge-{sev}">{sev}</span>'


def get_collections():
    data = api_get("/collections")
    if data and "collections" in data:
        return [c for c in data["collections"] if c.get("status") == "ready"]
    return []


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📄 Upload DRHP")

    uploaded = st.file_uploader("Upload PDF", type=["pdf"], help="Upload any SEBI DRHP PDF")
    col_name_input = st.text_input("Collection name (optional)", placeholder="e.g. Paytm_DRHP_2021")

    if st.button("⬆️ Index DRHP", use_container_width=True) and uploaded:
        with st.spinner("Uploading..."):
            resp = api_post(
                "/upload",
                files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
                data={"collection_name": col_name_input} if col_name_input else {},
            )
        if "error" not in resp:
            st.success(f"✅ Indexing started!\nCollection: `{resp['collection_name']}`")
            st.caption(f"{resp['total_pages']} pages detected")
            st.session_state["active_collection"] = resp["collection_name"]
        else:
            st.error(f"Upload failed: {resp.get('error', 'Unknown error')}")

    st.divider()
    st.markdown("## 📚 Indexed DRHPs")

    collections = get_collections()
    if not collections:
        st.caption("No DRHPs indexed yet. Upload one above.")
    else:
        for col in collections:
            label = f"📗 {col['filename'] if col.get('filename') else col['name']}"
            if st.button(label, key=f"sel_{col['name']}", use_container_width=True):
                st.session_state["active_collection"] = col["name"]
        st.caption(f"{len(collections)} DRHP(s) available")

    st.divider()
    st.markdown("**Backend**")
    health = api_get("/")
    if health:
        st.success("🟢 API Online")
    else:
        st.error("🔴 API Offline — start `uvicorn backend.api:app`")


# ── Main ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>📊 DRHP Analyst Agent</h1>
  <p>Read the 600 pages so you don't have to &nbsp;·&nbsp; Powered by Groq + LLaMA 3.3 70B</p>
</div>
""", unsafe_allow_html=True)

active = st.session_state.get("active_collection")

if not active:
    # Landing state
    st.info("👈 Upload a DRHP PDF from the sidebar to get started, or select an already-indexed one.")

    with st.expander("💡 What can this agent do?"):
        st.markdown("""
- **Q&A over the full DRHP** — ask anything: financials, promoter history, risk factors
- **Proactive Red Flag Analysis** — 12 automated checks run without you asking
- **Table-aware extraction** — financial tables are parsed and included in answers
- **Cross-reference resolution** — "See Risk Factor 47 → Annexure C" chains are tracked
- **Source citations** — every answer cites the exact page number
- **Trick-question resistant** — one-time exceptional items are flagged, adjusted PAT extracted
        """)

    with st.expander("📝 Sample questions to try"):
        st.markdown("""
```
Is this company profitable?
What are the top 3 risk factors I should worry about?
How much are promoters pledging?
What is the company's revenue from related parties?
What is the debt-to-equity ratio?
Are there any auditor qualifications?
What is the exact use of IPO proceeds?
Has the company had negative cash flows?
```
        """)
    st.stop()

# ── Status check ───────────────────────────────────────────────────────────────
status_data = api_get(f"/status/{active}")
if status_data and status_data.get("status") == "indexing":
    with st.spinner(f"⏳ Indexing in progress for `{active}`... refresh in a moment."):
        time.sleep(3)
    st.rerun()

st.markdown(f"### 🗂 Active DRHP: `{active}`")
if status_data:
    c1, c2, c3 = st.columns(3)
    c1.metric("Pages", status_data.get("pages", "?"))
    c2.metric("Chunks", status_data.get("chunks", "?"))
    c3.metric("Status", status_data.get("status", "ready").upper())

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["💬 Ask the DRHP", "🚨 Red Flag Scanner"])

# ─ Tab 1: Q&A ──────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("#### Ask anything about this DRHP")

    # Quick question buttons
    st.markdown("**Quick questions:**")
    quick_cols = st.columns(3)
    quick_questions = [
        "Is this company profitable?",
        "What are the main risk factors?",
        "What is the promoter background?",
        "Are there any auditor qualifications?",
        "What is the use of IPO proceeds?",
        "What related-party transactions exist?",
    ]
    for i, qq in enumerate(quick_questions):
        if quick_cols[i % 3].button(qq, key=f"qq_{i}", use_container_width=True):
            st.session_state["question_input"] = qq

    st.markdown("")
    question = st.text_area(
        "Your question",
        value=st.session_state.get("question_input", ""),
        height=80,
        placeholder="e.g. What is the adjusted PAT excluding exceptional items?",
    )

    adv_col1, adv_col2 = st.columns([1, 2])
    with adv_col1:
        section_filter = st.selectbox(
            "Filter by section (optional)",
            ["", "risk_factors", "financials", "promoters", "related_party",
             "litigations", "objects", "business", "management"],
        ) or None
    with adv_col2:
        n_results = st.slider("Context chunks to retrieve", 4, 12, 8)

    if st.button("🔍 Analyse", type="primary", use_container_width=True) and question.strip():
        with st.spinner("Reading the DRHP..."):
            result = api_post(
                "/query",
                json={
                    "collection_name": active,
                    "question": question,
                    "n_results": n_results,
                    "section_filter": section_filter,
                },
            )

        if "error" in result:
            st.error(f"Error: {result['error']}")
        else:
            st.markdown("#### 📋 Answer")
            st.markdown(
                f'<div class="answer-box">{result["answer"]}</div>',
                unsafe_allow_html=True,
            )

            st.markdown(f"**Sources** ({result['chunks_used']} chunks retrieved):")
            sources_html = ""
            seen_pages = set()
            for s in result.get("sources", []):
                pg = s["page"]
                if pg not in seen_pages:
                    sources_html += f'<span class="source-chip">Pg {pg} · {s["section"]}</span>'
                    seen_pages.add(pg)
            st.markdown(sources_html, unsafe_allow_html=True)


# ─ Tab 2: Red Flags ────────────────────────────────────────────────────────────
with tab2:
    st.markdown("#### 🚨 Proactive Red Flag Analysis")
    st.markdown(
        "Runs **12 automated checks** — promoter pledging, RPT concentration, "
        "auditor qualifications, litigation exposure, and more — without you having to ask."
    )

    if "red_flag_results" not in st.session_state or st.session_state.get("rf_collection") != active:
        run_btn = st.button("▶️ Run All 12 Checks", type="primary", use_container_width=True)
    else:
        run_btn = False
        if st.button("🔄 Re-run Analysis", use_container_width=True):
            del st.session_state["red_flag_results"]
            st.rerun()

    if run_btn:
        import json as _json

        progress_bar = st.progress(0, text="Starting checks...")
        status_text  = st.empty()
        live_results = st.container()

        partial_findings = []

        try:
            with requests.post(
                f"{API_BASE}/red-flags-stream",
                json={"collection_name": active},
                stream=True,
                timeout=600,   # 10 minutes — more than enough
            ) as resp:
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                    data = _json.loads(line)

                    if data.get("done"):
                        # Final summary arrived
                        st.session_state["red_flag_results"] = data
                        st.session_state["rf_collection"] = active
                        progress_bar.progress(100, text="✅ All 12 checks complete!")
                        status_text.empty()
                        st.rerun()
                    else:
                        # Individual check result
                        check   = data["check"]
                        prog    = data["progress"]
                        total   = data["total"]
                        pct     = int(prog / total * 100)
                        sev     = check["severity"]

                        partial_findings.append(check)
                        progress_bar.progress(pct, text=f"Check {prog}/{total}: {check['name']}")

                        sev_colors = {
                            "CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡",
                            "LOW": "🟢", "CLEAR": "🟢", "UNKNOWN": "⚪"
                        }
                        icon = sev_colors.get(sev, "⚪")
                        status_text.markdown(
                            f"{icon} **{check['name']}** → `{sev}`"
                        )

        except requests.exceptions.Timeout:
            st.error("Request timed out even with streaming. Check that the API server is running and reachable.")
        except Exception as e:
            st.error(f"Streaming error: {str(e)}")

    if "red_flag_results" in st.session_state and st.session_state.get("rf_collection") == active:
        result = st.session_state["red_flag_results"]
        findings = result.get("findings", [])
        summary = result.get("severity_summary", {})

        # Summary bar
        st.markdown("#### Summary")
        sum_cols = st.columns(6)
        for i, (sev, color) in enumerate([
            ("CRITICAL", "#FF3B30"), ("HIGH", "#FF9500"), ("MEDIUM", "#FFCC00"),
            ("LOW", "#34C759"), ("CLEAR", "#30D158"), ("UNKNOWN", "#8E8E93"),
        ]):
            count = summary.get(sev, 0)
            sum_cols[i].markdown(
                f'<div style="background:{color}22;border:1px solid {color};border-radius:8px;'
                f'padding:0.5rem;text-align:center">'
                f'<div style="color:{color};font-size:1.5rem;font-weight:700">{count}</div>'
                f'<div style="color:#94a3b8;font-size:0.7rem">{sev}</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown("")

        # Filter
        sev_filter = st.multiselect(
            "Show severity levels",
            ["CRITICAL", "HIGH", "MEDIUM", "LOW", "CLEAR", "UNKNOWN"],
            default=["CRITICAL", "HIGH", "MEDIUM"],
        )

        # Findings
        for f in findings:
            sev = f["severity"]
            if sev not in sev_filter:
                continue

            with st.expander(
                f"{severity_badge(sev)} &nbsp; {f['name']}",
                expanded=(sev in ["CRITICAL", "HIGH"]),
            ):
                # Parse the finding into structured sections
                raw = f["finding"]
                lines = raw.split("\n")
                for line in lines:
                    if line.startswith("SEVERITY:"):
                        pass  # Already shown in header
                    elif line.startswith("FINDING:"):
                        st.markdown(f"**Finding:** {line.replace('FINDING:', '').strip()}")
                    elif line.startswith("KEY_DATA:"):
                        st.markdown("**Key Data:**")
                    else:
                        st.markdown(line)

                if f.get("pages"):
                    pages_str = ", ".join(str(p) for p in sorted(set(f["pages"])))
                    st.caption(f"📄 Evidence found on pages: {pages_str}")

        # Download results
        st.divider()
        st.download_button(
            "⬇️ Download Full Report (JSON)",
            data=json.dumps(result, indent=2),
            file_name=f"red_flags_{active}.json",
            mime="application/json",
        )
