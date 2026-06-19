# IPO Analyst Agent
### *"Read the 600 pages so you don't have to"*

**Institutional-Grade Prospectus Forensics & Agentic Due Diligence Engine**

IPO-Analyst is a production-ready AI auditing tool that reads dense, 600-page SEBI DRHPs and SEC S-1 filings to expose hidden financial risks, complex cross-references, and buried footnotes in under 120 seconds.

---

### YouTube link - https://youtu.be/ow4BEl-TA74

--- 

## 🚀 Core Features

* **Table-Aware Ingestion:** Uses `pdfplumber` to parse financial tables into structured Markdown grids, ensuring data layout and column headers remain completely intact for the LLM.
* **Recursive Cross-Referencing:** Automatically tracks and resolves multi-hop regulatory chains (e.g., *Risk Factor 47 → Annexure C → Note 14*) up to 3 levels deep to build complete evidence trails.
* **9-Core Forensic Scanner:** Runs parallel background audits on critical metrics (Promoter Pledging, Related-Party Transactions, Cash Flow Velocity) and streams real-time risk heatmaps.
* **Deterministic Citation Viewer:** Uses an inline PDF viewer to render the *exact* source page from the uploaded document right under the answer—eliminating hallucination worries.
* **Bear Case & Reality Check:** Synthesizes institutional-grade risk reports and automatically checks historical training data to score past warnings against actual post-listing stock performance.

---

## 🛠️ The Tech Stack

| Component | Technology | Target Workload |
| --- | --- | --- |
| **Primary LLM** | LLaMA 3.3 70B (via Groq) | Complex Interactive Chat & Nuanced Reasoning |
| **Agent LLM** | Qwen3 32B (via Groq) | High-Throughput Forensic Audits & Code-Stripping |
| **Vector Database** | ChromaDB (Local Persistent) | On-Disk Storage, Zero Cloud Cost, Absolute Privacy |
| **Embeddings** | `all-MiniLM-L6-v2` | Free, Local Execution (384-dimensional vectors) |
| **Backend / API** | FastAPI | Asynchronous Routing & Streaming JSON Payloads |
| **Frontend UI** | Streamlit | Responsive Interface with Forced Native Dark Theme |

---

## 🧠 Architectural Moats

### 1. 3-Layer Intent Guardrail

Protects main model compute limits by filtering inputs before they reach costly inference steps:

* **Layer 1 (Regex):** Instantly drops clear non-financial noise (e.g., "write a poem") at 0 tokens.
* **Layer 2 (Whitelist):** Immediately approves verified financial terminology.
* **Layer 3 (LLM Classifier):** Uses a fast, 5-token Qwen3 call to evaluate ambiguous queries.

### 2. Global Pacing Lock

Instead of utilizing volatile exponential backoff retry loops that flood API limits during high-volume sequential agent calls, a global thread lock enforces a strict **2.5-second minimum gap** between calls. This guarantees high-performance throughput completely within Groq's free tier caps.

### 3. Stateless Session Isolation

Browser sessions generate a unique UUID passed via request headers. Collection names are dynamically prefixed in memory (e.g., `s_a1b2c3d4_paytmDRHP`). Users can only view, query, and manage their own documents without requiring complex relational databases or authentication overhead.

---

## ⏱️ Quick Start

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/sa7vic/IPO-Analyst.git
cd IPO-Analyst
pip install -r requirements.txt

```

### 2. Configure Environment Variables

Create a `.env` file in the root directory:

```env
GROQ_API_KEY=your_groq_api_key_here

```

### 3. Launch the Application

Run the dual-server initialization script to spin up the FastAPI backend (Port 8000) and the Streamlit frontend (Port 8501) simultaneously:

```bash
python start.py

```
