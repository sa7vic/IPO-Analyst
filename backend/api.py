"""
FastAPI Backend for DRHP Analyst Agent.

Endpoints:
  POST /upload          — upload & index a DRHP PDF
  GET  /collections     — list indexed DRHPs
  POST /query           — RAG question answering
  POST /red-flags       — run proactive 12-check analysis
  GET  /status/{name}   — collection status
  DELETE /collection/{name} — remove a collection
"""

import os
import shutil
import tempfile
from typing import Optional

import json as _json
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from utils.pdf_parser import extract_text_and_tables, chunk_pages, get_pdf_metadata
from utils.vector_store import (
    index_chunks, query_collection, collection_exists,
    delete_collection, list_collections,
)
from utils.llm import rag_answer
from utils.red_flag_agent import run_red_flag_analysis

app = FastAPI(
    title="DRHP Analyst Agent",
    description="AI-powered IPO DRHP analysis — reads 600 pages so you don't have to.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory index status tracker
_index_status: dict = {}   # collection_name -> {"status": ..., "pages": ..., "chunks": ...}


# ── Models ─────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    collection_name: str
    question: str
    n_results: int = 8
    section_filter: Optional[str] = None


class RedFlagRequest(BaseModel):
    collection_name: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "DRHP Analyst Agent API is running.", "docs": "/docs"}


@app.post("/upload")
async def upload_drhp(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection_name: Optional[str] = None,
):
    """Upload a DRHP PDF and index it into ChromaDB."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")

    # Derive collection name from filename
    safe_name = collection_name or os.path.splitext(file.filename)[0]
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in safe_name)[:50]

    # Save to temp file
    tmp_path = tempfile.mktemp(suffix=".pdf")
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    meta = get_pdf_metadata(tmp_path)
    _index_status[safe_name] = {
        "status": "indexing",
        "pages": meta["total_pages"],
        "chunks": 0,
        "filename": file.filename,
    }

    background_tasks.add_task(_index_pdf, tmp_path, safe_name)

    return {
        "collection_name": safe_name,
        "filename": file.filename,
        "total_pages": meta["total_pages"],
        "status": "indexing_started",
        "message": f"Indexing {meta['total_pages']} pages in the background. Poll /status/{safe_name}.",
    }


def _index_pdf(pdf_path: str, collection_name: str):
    try:
        pages  = extract_text_and_tables(pdf_path)
        chunks = chunk_pages(pages, chunk_size=800, overlap=100)
        count  = index_chunks(collection_name, chunks)

        _index_status[collection_name]["status"] = "ready"
        _index_status[collection_name]["chunks"] = count
    except Exception as e:
        _index_status[collection_name]["status"] = f"error: {str(e)}"
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)


@app.get("/status/{collection_name}")
def get_status(collection_name: str):
    if collection_name in _index_status:
        return _index_status[collection_name]
    if collection_exists(collection_name):
        return {"status": "ready", "collection_name": collection_name}
    raise HTTPException(404, f"Collection '{collection_name}' not found.")


@app.get("/collections")
def get_collections():
    cols = list_collections()
    enriched = []
    for c in cols:
        info = _index_status.get(c, {})
        enriched.append({
            "name": c,
            "status": info.get("status", "ready"),
            "pages": info.get("pages", "?"),
            "chunks": info.get("chunks", "?"),
            "filename": info.get("filename", c),
        })
    return {"collections": enriched}


@app.post("/query")
def query_drhp(req: QueryRequest):
    """Ask a question against a specific DRHP collection."""
    if not collection_exists(req.collection_name):
        raise HTTPException(404, f"Collection '{req.collection_name}' not found. Upload a DRHP first.")

    status = _index_status.get(req.collection_name, {}).get("status", "ready")
    if status == "indexing":
        raise HTTPException(503, "DRHP is still being indexed. Please wait.")

    chunks = query_collection(
        req.collection_name,
        req.question,
        n_results=req.n_results,
        section_filter=req.section_filter,
    )

    result = rag_answer(req.question, chunks)
    return {
        "question": req.question,
        "answer": result["answer"],
        "sources": result["sources"],
        "chunks_used": len(chunks),
    }


@app.post("/red-flags")
def run_red_flags(req: RedFlagRequest):
    """Run the full 12-check proactive red flag analysis."""
    if not collection_exists(req.collection_name):
        raise HTTPException(404, f"Collection '{req.collection_name}' not found.")

    status = _index_status.get(req.collection_name, {}).get("status", "ready")
    if status == "indexing":
        raise HTTPException(503, "DRHP is still being indexed. Please wait.")

    findings = run_red_flag_analysis(req.collection_name)
    severity_counts = {}
    for f in findings:
        severity_counts[f["severity"]] = severity_counts.get(f["severity"], 0) + 1

    return {
        "collection_name": req.collection_name,
        "total_checks": len(findings),
        "severity_summary": severity_counts,
        "findings": findings,
    }


@app.post("/red-flags-stream")
def run_red_flags_stream(req: RedFlagRequest):
    """
    Streaming version — sends each check result as a JSON line the moment it's done.
    Fixes timeout issue for slow networks / many LLM calls.
    """
    if not collection_exists(req.collection_name):
        raise HTTPException(404, f"Collection '{req.collection_name}' not found.")

    status = _index_status.get(req.collection_name, {}).get("status", "ready")
    if status == "indexing":
        raise HTTPException(503, "DRHP is still being indexed. Please wait.")

    from utils.red_flag_agent import RED_FLAG_CHECKS, _parse_severity, SEVERITY_ORDER
    from utils.vector_store import query_collection
    from utils.llm import chat

    def generate():
        findings = []
        total = len(RED_FLAG_CHECKS)

        for i, check in enumerate(RED_FLAG_CHECKS):
            try:
                chunks = query_collection(req.collection_name, check["query"], n_results=5,
                                          section_filter=check.get("section"))
                if len(chunks) < 2:
                    chunks = query_collection(req.collection_name, check["query"], n_results=5)

                if not chunks:
                    result = {"id": check["id"], "name": check["name"],
                              "severity": "UNKNOWN", "finding": "Insufficient data.", "pages": []}
                else:
                    context = "\n\n".join(f"[Page {c['page_num']}]\n{c['text']}" for c in chunks)
                    system = """You are a SEBI analyst doing red-flag screening. Be concise.
Format your response as:
SEVERITY: [CRITICAL/HIGH/MEDIUM/LOW/CLEAR]
FINDING: [2-3 sentence summary with page citations]
KEY_DATA: [bullet list of key numbers/facts extracted]"""
                    finding_raw = chat(system,
                                       f"{check['prompt']}\n\nDRHP Context:\n{context}",
                                       temperature=0.1, max_tokens=400)
                    severity = _parse_severity(finding_raw)
                    result = {"id": check["id"], "name": check["name"],
                              "severity": severity, "finding": finding_raw,
                              "pages": [c["page_num"] for c in chunks]}
            except Exception as e:
                result = {"id": check["id"], "name": check["name"],
                          "severity": "UNKNOWN", "finding": f"Error: {str(e)}", "pages": []}

            findings.append(result)
            # Send this check result immediately
            payload = _json.dumps({"check": result, "progress": i + 1, "total": total})
            yield payload + "\n"

        # Final summary line
        findings.sort(key=lambda x: SEVERITY_ORDER.get(x["severity"], 5))
        severity_counts = {}
        for f in findings:
            severity_counts[f["severity"]] = severity_counts.get(f["severity"], 0) + 1

        summary = _json.dumps({
            "done": True,
            "collection_name": req.collection_name,
            "total_checks": len(findings),
            "severity_summary": severity_counts,
            "findings": findings,
        })
        yield summary + "\n"

    return StreamingResponse(generate(), media_type="text/plain")


@app.delete("/collection/{collection_name}")
def remove_collection(collection_name: str):
    delete_collection(collection_name)
    _index_status.pop(collection_name, None)
    return {"message": f"Collection '{collection_name}' deleted."}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("FASTAPI_PORT", 8000))
    uvicorn.run("backend.api:app", host="0.0.0.0", port=port, reload=True)
