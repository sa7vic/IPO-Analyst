"""
IPO Analyst — Streamlit Frontend
"""

import streamlit as st
import requests
import time, json, os, uuid
from dotenv import load_dotenv

load_dotenv()
API_BASE = os.getenv("API_BASE", "http://localhost:8000")

try:
    from streamlit_pdf_viewer import pdf_viewer as _pdf_viewer
    PDF_VIEWER_AVAILABLE = True
except ImportError:
    PDF_VIEWER_AVAILABLE = False

st.set_page_config(
    page_title="IPO Analyst",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

_css_path = os.path.join(os.path.dirname(__file__), "static", "style.css")
_css = open(_css_path, encoding="utf-8").read() if os.path.exists(_css_path) else ""
st.html(f"<style>{_css}</style>")
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"/>',
            unsafe_allow_html=True)

if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())
SESSION_ID = st.session_state["session_id"]
HEADERS    = {"x-session-id": SESSION_ID}


# ── Helpers ─────────────────────────────────────────────────────────────────────
def api_get(path):
    try:
        r = requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=30)
        return r.json() if r.ok else None
    except: return None

def api_post(path, timeout=120, **kwargs):
    try:
        h = {**kwargs.pop("headers", {}), **HEADERS}
        r = requests.post(f"{API_BASE}{path}", headers=h, timeout=timeout, **kwargs)
        if r.status_code == 429:
            return {"error": r.json().get("detail", "Rate limit reached. Wait 60 seconds.")}
        return r.json() if r.ok else {"error": r.text}
    except Exception as e:
        return {"error": str(e)}

def api_delete(path):
    try: return requests.delete(f"{API_BASE}{path}", headers=HEADERS, timeout=15).ok
    except: return False

def get_pdf_bytes(collection_name: str) -> bytes | None:
    """Fetch and cache PDF bytes for the citation viewer."""
    cache_key = f"pdf_bytes_{collection_name}"
    if cache_key not in st.session_state:
        try:
            r = requests.get(f"{API_BASE}/pdf-bytes/{collection_name}",
                             headers=HEADERS, timeout=30)
            if r.ok and r.headers.get("content-type","").startswith("application/pdf"):
                st.session_state[cache_key] = r.content
            else:
                st.session_state[cache_key] = None
        except:
            st.session_state[cache_key] = None
    return st.session_state.get(cache_key)

def show_pdf_page(collection_name: str, pages: list, label: str = "Source pages"):
    """Show specific pages of the source PDF using streamlit-pdf-viewer."""
    if not PDF_VIEWER_AVAILABLE:
        st.caption("Install streamlit-pdf-viewer for visual citations: pip install streamlit-pdf-viewer")
        return
    pdf_bytes = get_pdf_bytes(collection_name)
    if not pdf_bytes:
        st.caption("Source PDF not available — re-upload document to enable visual citations.")
        return
    with st.expander(f"📄 {label}", expanded=False):
        _pdf_viewer(
            input=pdf_bytes,
            pages_to_render=pages,
            width=700,
            height=600,
        )

def get_collections():
    d = api_get("/collections")
    return [c for c in d.get("collections", []) if c.get("status") == "ready"] if d else []

def badge_html(sev):
    icons = {"CRITICAL":"fa-circle-xmark","HIGH":"fa-triangle-exclamation",
             "MEDIUM":"fa-circle-exclamation","LOW":"fa-circle-check",
             "CLEAR":"fa-circle-check","UNKNOWN":"fa-circle-question"}
    return f'<span class="badge badge-{sev}"><i class="fa-solid {icons.get(sev,"fa-circle-question")}"></i> {sev}</span>'

def parse_finding(raw):
    sev, finding, bullets, mode = "UNKNOWN", "", [], None
    for line in raw.split("\n"):
        s = line.strip()
        if s.startswith("SEVERITY:"):   sev = s.replace("SEVERITY:","").strip().split()[0].upper()
        elif s.startswith("FINDING:"):  finding = s.replace("FINDING:","").strip(); mode="finding"
        elif s.startswith("KEY_DATA:"): mode="bullets"
        elif mode=="finding" and s:     finding += " " + s
        elif mode=="bullets" and s:
            c = s.lstrip("-•* ")
            if c: bullets.append(c)
    return sev, finding.strip(), bullets

def show_rate_limit_warning(err: str):
    st.warning(f"⏱ {err}")


# ── Sidebar ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.html('<p class="sidebar-label"><i class="fa-solid fa-file-arrow-up"></i> Upload Document</p>')
    st.html('<p class="sidebar-sub">Supports SEBI DRHPs and SEC S-1 filings</p>')

    uploaded       = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")
    col_name_input = st.text_input("Collection name", placeholder="Name (optional)", label_visibility="collapsed")

    if st.button("Index Document", use_container_width=True) and uploaded:
        with st.spinner("Uploading…"):
            resp = api_post("/upload",
                files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
                data={"collection_name": col_name_input} if col_name_input else {},
            )
        if "error" not in resp:
            st.success(f"Indexing started — {resp['total_pages']} pages")
            st.session_state["active_collection"] = resp["collection_name"]
            st.rerun()
        else:
            st.error(resp.get("error", "Upload failed"))

    st.html('<hr class="s-divider"/><p class="sidebar-label"><i class="fa-solid fa-folder-open"></i> Indexed Documents</p>')

    collections = get_collections()
    active = st.session_state.get("active_collection")

    if not collections:
        st.html('<p class="sidebar-empty">No documents indexed yet.</p>')
    else:
        for col in collections:
            fname  = col.get("filename", col["name"])
            c1, c2 = st.columns([5, 1])
            with c1:
                if st.button(fname[:30] + ("…" if len(fname)>30 else ""),
                             key=f"sel_{col['name']}", use_container_width=True):
                    st.session_state["active_collection"] = col["name"]
                    for k in ["chat_history","red_flag_results","forensics_result"]:
                        st.session_state.pop(k, None)
                    st.rerun()
            with c2:
                if st.button("✕", key=f"del_{col['name']}", help="Remove"):
                    api_delete(f"/collection/{col['name']}")
                    if active == col["name"]:
                        st.session_state.pop("active_collection", None)
                        for k in ["chat_history","red_flag_results","forensics_result"]:
                            st.session_state.pop(k, None)
                    st.rerun()

    st.html('<hr class="s-divider"/>')
    health = api_get("/")
    st.html(
        '<p class="api-status online"><i class="fa-solid fa-circle"></i> API Online</p>'
        if health else
        '<p class="api-status offline"><i class="fa-solid fa-circle"></i> API Offline — run start.py</p>'
    )
    st.html(f'<p class="session-id">Session: {SESSION_ID[:8]}…</p>')


# ── Header ───────────────────────────────────────────────────────────────────────
st.html("""
<div class="app-header">
  <div class="header-icon"><i class="fa-solid fa-magnifying-glass-chart"></i></div>
  <div>
    <h1>IPO Analyst</h1>
    <p>AI-Powered DRHP &amp; S-1 Analysis &nbsp;·&nbsp; Groq LLaMA 70B + Qwen3 32B</p>
  </div>
</div>
""")

active = st.session_state.get("active_collection")

# ── Landing ──────────────────────────────────────────────────────────────────────
if not active:
    st.html("""
    <div class="landing-box">
      <i class="fa-solid fa-file-invoice landing-icon"></i>
      <h2>Upload an IPO prospectus to begin</h2>
      <p>Works with SEBI DRHPs and SEC S-1 filings — any company, any year.</p>
    </div>
    """)
    c1, c2, c3, c4 = st.columns(4)
    for col, icon, title, desc in [
        (c1, "fa-comments",         "Ask the Document",    "Chat with the full prospectus. Every answer cites the exact page."),
        (c2, "fa-shield-halved",    "Red Flag Scanner",    "9 automated checks — promoter pledging, litigation, OFS, PVD and more."),
        (c3, "fa-scale-balanced",   "Financial Forensics", "Checks if the numbers add up. Flags revenue vs cash flow divergence."),
        (c4, "fa-file-excel",       "Financial Snapshot",  "Extracts restated financials into a formula-validated Excel file."),
    ]:
        with col:
            st.html(f"""<div class="feature-card">
              <i class="fa-solid {icon} feature-icon"></i>
              <h3>{title}</h3>
              <p>{desc}</p>
            </div>""")
    st.stop()

# ── Indexing check ───────────────────────────────────────────────────────────────
status_data = api_get(f"/status/{active}")
if status_data and status_data.get("status") == "indexing":
    st.info("Indexing in progress… refreshing shortly.")
    time.sleep(3); st.rerun()

# ── Info bar ─────────────────────────────────────────────────────────────────────
fname  = status_data.get("filename", active) if status_data else active
pages  = status_data.get("pages",  "?")      if status_data else "?"
chunks = status_data.get("chunks", "?")      if status_data else "?"

st.html(f"""
<div class="info-bar">
  <div class="info-item">
    <i class="fa-solid fa-file-pdf" style="color:#f97316"></i>
    <span class="info-val">{fname[:50]}</span>
    <span class="info-lbl">Active Document</span>
  </div>
  <div class="info-item"><span class="info-val">{pages}</span><span class="info-lbl">Pages</span></div>
  <div class="info-item"><span class="info-val">{chunks}</span><span class="info-lbl">Chunks</span></div>
</div>
<div class="tip-bar"><i class="fa-solid fa-circle-info"></i> Allow ~60 seconds between AI features to stay within free API limits.</div>
""")

company_name = st.text_input("Company name", placeholder="Company name for reports (optional)…",
                              label_visibility="collapsed", key="company_name_input") or "the Company"


# ── Tabs ──────────────────────────────────────────────────────────────────────────
tab_chat, tab_flags, tab_forensics, tab_bear = st.tabs([
    "💬 Ask the Document",
    "🚨 Red Flag Scanner",
    "🔬 Financial Forensics",
    "🔍 Bear Case",
])


# CHAT TAB
with tab_chat:
    QUICK_QUESTIONS = [
        "Is this company profitable?",
        "What are the top risk factors?",
        "What is the promoter background?",
        "Are there auditor qualifications?",
        "What is the use of IPO proceeds?",
        "Any related-party transactions?",
        "What is the debt-to-equity ratio?",
        "Has cash flow been negative?",
    ]

    st.html('<p class="section-label">Quick Questions</p>')
    cols = st.columns(4)
    for i, qq in enumerate(QUICK_QUESTIONS):
        if cols[i % 4].button(qq, key=f"qq_{i}", use_container_width=True):
            st.session_state["main_chat_input"] = qq

    st.html('<hr class="s-divider"/>')
    use_xref = st.toggle("Cross-reference chain mode", value=False,
                         help="Follows Risk Factor → Annexure → Note chains for deeper answers")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for msg in st.session_state["chat_history"]:
        with st.chat_message("user" if msg["role"]=="user" else "assistant"):
            st.markdown(msg["content"])
            if msg["role"] == "bot":
                hist_pages = []
                if msg.get("all_pages"):
                    hist_pages = [int(p) for p in msg["all_pages"]]
                    chips = "".join(f'<span class="source-chip">Pg {p}</span>' for p in hist_pages)
                    st.html(f'<div class="source-row">{chips}</div>')
                elif msg.get("sources"):
                    seen, chips, hist_pages = set(), [], []
                    for s in msg["sources"]:
                        k = f"{s.get('page')}_{s.get('section')}"
                        if k not in seen:
                            seen.add(k)
                            chips.append(f'<span class="source-chip">Pg {s["page"]} · {s.get("section","")}</span>')
                            hist_pages.append(int(s["page"]))
                    if chips:
                        st.html(f'<div class="source-row">{"".join(chips)}</div>')
                if hist_pages:
                    show_pdf_page(active, hist_pages, "View source pages")
                if msg.get("chain_info"):
                    st.html(f'<span class="chain-badge"><i class="fa-solid fa-diagram-project"></i> {msg["chain_info"]}</span>')

    question = st.chat_input("Ask anything about this prospectus…", key="main_chat_input")

    if question and question.strip():
        with st.chat_message("user"):
            st.markdown(question)
        st.session_state["chat_history"].append({"role": "user", "content": question})

        with st.chat_message("assistant"):
            with st.spinner("Reading prospectus…"):
                result = api_post("/query", json={
                    "collection_name": active,
                    "question":        question,
                    "n_results":       8,
                    "use_cross_ref":   use_xref,
                }, timeout=90)

            if "error" in result:
                err = result["error"]
                if "rate limit" in err.lower() or "429" in err:
                    st.warning(f"⏱ {err}")
                    answer = err
                else:
                    st.error(err); answer = err
            elif result.get("mode") == "blocked":
                st.html(
                    '<div class="out-of-domain">'
                    '<i class="fa-solid fa-ban"></i> '
                    f'{result["answer"]}'
                    '</div>'
                )
                answer = result["answer"]
            else:
                answer = result.get("answer", "")
                st.markdown(answer)
                sources    = result.get("sources", [])
                chain_info = result.get("chain_summary") if use_xref else None

                cited_pages = []
                if result.get("mode") == "cross_reference" and result.get("all_pages"):
                    cited_pages = [int(p) for p in result["all_pages"]]
                    page_chips  = "".join(
                        f'<span class="source-chip">Pg {p}</span>' for p in cited_pages
                    )
                    st.html(f'<div class="source-row">{page_chips}</div>')
                elif sources:
                    seen, chips = set(), []
                    for s in sources:
                        k = f"{s.get('page')}_{s.get('section')}"
                        if k not in seen:
                            seen.add(k)
                            chips.append(
                                f'<span class="source-chip">'
                                f'Pg {s["page"]} · {s.get("section","")}</span>'
                            )
                            cited_pages.append(int(s["page"]))
                    if chips:
                        st.html(f'<div class="source-row">{"".join(chips)}</div>')

                if cited_pages:
                    show_pdf_page(active, cited_pages, "View source pages")

                if chain_info:
                    st.html(f'<span class="chain-badge"><i class="fa-solid fa-diagram-project"></i> {chain_info}</span>')

        st.session_state["chat_history"].append({
            "role":       "bot",
            "content":    answer,
            "sources":    result.get("sources") if "error" not in result and result.get("mode") != "blocked" else None,
            "chain_info": result.get("chain_summary") if use_xref and "error" not in result else None,
            "all_pages":  result.get("all_pages") if use_xref and "error" not in result else None,
        })
        st.rerun()

    if st.session_state.get("chat_history"):
        if st.button("Clear chat", key="clear_chat"):
            st.session_state["chat_history"] = []
            st.rerun()


# RED FLAGS TAB
with tab_flags:
    st.html('<p class="section-label"><i class="fa-solid fa-shield-halved"></i> 9 Automated Checks</p>')

    already = ("red_flag_results" in st.session_state
               and st.session_state.get("rf_collection") == active)

    c1, c2 = st.columns([3,1])
    run_btn   = c1.button("Run All 9 Checks", type="primary", use_container_width=True, disabled=already)
    rerun_btn = c2.button("Re-run", use_container_width=True, disabled=not already)
    if rerun_btn:
        st.session_state.pop("red_flag_results", None)
        st.rerun()

    if run_btn:
        prog = st.progress(0, text="Starting…")
        slot = st.empty()
        try:
            with requests.post(f"{API_BASE}/red-flags-stream",
                               json={"collection_name": active},
                               headers=HEADERS, stream=True, timeout=600) as resp:
                for raw in resp.iter_lines():
                    if not raw: continue
                    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    if data.get("done"):
                        st.session_state["red_flag_results"] = data
                        st.session_state["rf_collection"]    = active
                        prog.progress(100, text="Complete")
                        slot.empty(); st.rerun()
                    else:
                        check = data["check"]
                        pct   = int(data["progress"] / data["total"] * 100)
                        prog.progress(pct, text=f"Check {data['progress']}/{data['total']}: {check['name']}")
                        sev  = check["severity"]
                        _ico = {"CRITICAL":"fa-circle-xmark","HIGH":"fa-triangle-exclamation",
                                "MEDIUM":"fa-circle-exclamation","LOW":"fa-circle-check",
                                "CLEAR":"fa-circle-check"}.get(sev,"fa-circle-question")
                        slot.html(f'{badge_html(sev)} &nbsp;<strong>{check["name"]}</strong>')
        except Exception as e:
            st.error(f"Error: {e}")

    if already or "red_flag_results" in st.session_state:
        result   = st.session_state["red_flag_results"]
        findings = result.get("findings", [])
        summary  = result.get("severity_summary", {})

        sev_cfgs = [("CRITICAL","#ff3b30"),("HIGH","#ff9500"),("MEDIUM","#ffcc00"),
                    ("LOW","#34c759"),("CLEAR","#30d158"),("UNKNOWN","#8b949e")]
        pills = "".join(
            f'<div class="sev-pill" style="border-color:{c}44;background:{c}11">'
            f'<div class="sev-count" style="color:{c}">{summary.get(s,0)}</div>'
            f'<div class="sev-label" style="color:{c}">{s}</div></div>'
            for s, c in sev_cfgs
        )
        st.html(f'<div class="sev-bar">{pills}</div>')

        # Heatmap
        color_map = {"CRITICAL":"#ff3b30","HIGH":"#ff9500","MEDIUM":"#ffcc00",
                     "LOW":"#34c759","CLEAR":"#30d158","UNKNOWN":"#8b949e"}
        cells = "".join(
            f'<div class="heatmap-cell" style="border-color:{color_map.get(f["severity"],"#8b949e")}44;'
            f'background:{color_map.get(f["severity"],"#8b949e")}11">'
            f'<div style="color:{color_map.get(f["severity"],"#8b949e")}">&#9679;</div>'
            f'<div class="hc-name" style="color:{color_map.get(f["severity"],"#8b949e")}">{f["name"]}</div>'
            f'</div>' for f in findings
        )
        st.html(f'<p class="section-label">Risk Heatmap</p><div class="heatmap-grid">{cells}</div>')

        st.html('<p class="section-label" style="margin-top:1.2rem">Detailed Findings</p>')
        sev_filter = st.multiselect("Filter", ["CRITICAL","HIGH","MEDIUM","LOW","CLEAR","UNKNOWN"],
                                     default=["CRITICAL","HIGH","MEDIUM"], label_visibility="collapsed")

        for f in findings:
            sev = f["severity"]
            if sev not in sev_filter: continue
            _, finding_text, bullets = parse_finding(f["finding"])
            pages_str = ", ".join(str(p) for p in sorted(set(f["pages"]))) if f.get("pages") else "—"
            bl_html   = "".join(f"<li>{b}</li>" for b in bullets)
            st.html(f"""
            <div class="rf-card sev-{sev}">
              <div class="rf-header">{badge_html(sev)} <span class="rf-title">{f["name"]}</span></div>
              <div class="rf-finding">{finding_text or "See key data below."}</div>
              {"<ul class='rf-keydata'>" + bl_html + "</ul>" if bullets else ""}
              <div class="rf-pages"><i class="fa-solid fa-bookmark"></i> Pages: {pages_str}</div>
            </div>""")

        st.divider()
        st.download_button("Download Report (JSON)", data=json.dumps(result, indent=2),
                           file_name="red_flags.json", mime="application/json")


# FORENSICS TAB
with tab_forensics:
    st.html('<p class="section-label"><i class="fa-solid fa-scale-balanced"></i> Financial Forensics</p>')

    if st.button("Run Financial Forensics", type="primary", use_container_width=True):
        with st.spinner("Checking financial consistency…"):
            r = api_post("/forensics", json={"collection_name": active}, timeout=120)
        if "error" in r:
            if "rate limit" in r["error"].lower():
                show_rate_limit_warning(r["error"])
            else:
                st.error(r["error"])
        else:
            st.session_state["forensics_result"] = r

    if "forensics_result" in st.session_state:
        cr    = st.session_state["forensics_result"]
        flags = cr.get("flags", [])
        eq    = cr.get("earnings_quality", "")

        if eq:
            color = "#ff3b30" if "LOW" in eq else "#ffcc00" if "MEDIUM" in eq else "#34c759"
            st.html(f'<div class="eq-badge" style="border-color:{color};color:{color}">'
                    f'<i class="fa-solid fa-chart-line"></i> {eq}</div>')

        if flags:
            for fl in flags:
                sev = fl.get("severity","UNKNOWN").strip().upper()
                details = "".join(f'<div class="flag-detail">{d}</div>' for d in fl.get("details",[]))
                st.html(f"""
                <div class="rf-card sev-{sev}">
                  <div class="rf-header">{badge_html(sev)}
                    <span class="rf-title">{fl.get("name","Flag")}</span></div>
                  {details}
                </div>""")
        else:
            st.html('<p style="color:#8b949e">No material inconsistencies detected in available data.</p>')


# BEAR CASE TAB
with tab_bear:
    st.html('<p class="section-label"><i class="fa-solid fa-magnifying-glass"></i> Bear Case — Material Risk Analysis</p>')

    if st.button("Generate Bear Case", type="primary", use_container_width=True):
        with st.spinner("Analysing material risks…"):
            r = api_post("/bear-case",
                         json={"collection_name": active, "company_name": company_name},
                         timeout=180)
        if "error" in r:
            if "rate limit" in r["error"].lower():
                show_rate_limit_warning(r["error"])
            else:
                st.error(r["error"])
        else:
            st.session_state["bear_result"] = r
            rc = api_get(f"/reality-check?collection_name={active}&company={requests.utils.quote(company_name if company_name != 'the Company' else '')}")
            if rc and rc.get("success"):
                st.session_state["reality_check"] = rc.get("data", {})

    if "bear_result" in st.session_state:
        bc = st.session_state["bear_result"]["bear_case"]
        if "## Excerpts Used" in bc:
            bc = bc[:bc.index("## Excerpts Used")].strip()
        st.html(f'<div class="report-box bear">{bc.replace(chr(10),"<br>")}</div>')
        st.download_button("Download Bear Case", data=bc,
                           file_name="bear_case.txt", mime="text/plain")

        rc = st.session_state.get("reality_check", {})
        if rc.get("is_listed"):
            chg     = rc.get("change_from_ipo")
            summary = rc.get("summary", "")
            st.html('<hr class="s-divider"/><p class="section-label"><i class="fa-solid fa-chart-line"></i> Reality Check</p>')
            try:
                chg     = float(chg)
                color   = "#ff3b30" if chg < -20 else "#ff9500" if chg < 0 else "#34c759"
                arrow   = "↓" if chg < 0 else "↑"
                verdict = "Bear case validated" if chg < -20 else "Declined post-IPO" if chg < 0 else "Stock held up"
                st.html(f"""
                <div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:1rem 1.25rem">
                  <div style="display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap">
                    <div><div style="color:#8b949e;font-size:0.7rem;text-transform:uppercase">IPO Price</div>
                      <div style="color:#e6edf3;font-weight:600">{rc.get("currency","")} {rc.get("ipo_price","N/A")}</div></div>
                    <div><div style="color:#8b949e;font-size:0.7rem;text-transform:uppercase">Current Price</div>
                      <div style="color:#e6edf3;font-weight:600">{rc.get("currency","")} {rc.get("current_price","N/A")}</div></div>
                    <div><div style="color:#8b949e;font-size:0.7rem;text-transform:uppercase">Change from IPO</div>
                      <div style="color:{color};font-weight:700;font-size:1.3rem">{arrow} {abs(chg):.1f}%</div></div>
                    <div style="margin-left:auto">
                      <span style="background:{color}22;border:1px solid {color};color:{color};
                        padding:4px 12px;border-radius:20px;font-size:0.78rem;font-weight:600">{verdict}</span></div>
                  </div>
                  {f'<div style="color:#8b949e;font-size:0.8rem;margin-top:0.75rem;border-top:1px solid #21262d;padding-top:0.5rem">{summary}</div>' if summary else ''}
                </div>""")
            except (ValueError, TypeError):
                if summary:
                    st.html(f'<div class="report-box" style="margin-top:0.5rem">{summary.replace(chr(10),"<br>")}</div>')

# end of app
