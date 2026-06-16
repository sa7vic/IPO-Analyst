"""
IPO Analyst — FastAPI Backend
"""

import os, shutil, tempfile, uuid, json as _json, re
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from utils.pdf_parser     import extract_text_and_tables, chunk_pages, get_pdf_metadata
from utils.vector_store   import index_chunks, query_collection, collection_exists, delete_collection, list_collections
from utils.llm            import rag_answer
from utils.red_flag_agent import RED_FLAG_CHECKS, SEVERITY_ORDER, _parse_severity, run_single_check
from utils.cross_ref      import build_evidence_chain_answer
from utils.agents         import check_financial_consistency, generate_bear_case
from utils.citation_viewer import register_pdf, get_page_snippet, get_page_text_excerpt
from utils.intent_guard    import classify_intent, OUT_OF_DOMAIN_MESSAGE

app = FastAPI(title="IPO Analyst", version="6.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_index_status: dict = {}
_pdf_paths:    dict = {}


def _session_prefix(sid: str) -> str:
    return f"s_{sid[:8]}_"

def _col_name(sid: str, name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40]
    return f"{_session_prefix(sid)}{safe}"


class QueryRequest(BaseModel):
    collection_name: str
    question:        str
    n_results:       int  = 8
    section_filter:  Optional[str] = None
    use_cross_ref:   bool = False

class RedFlagRequest(BaseModel):
    collection_name: str

class ForensicsRequest(BaseModel):
    collection_name: str

class BearCaseRequest(BaseModel):
    collection_name: str
    company_name:    str = ""


@app.get("/")
def root():
    return {"message": "IPO Analyst v6", "docs": "/docs"}


@app.post("/upload")
async def upload_doc(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection_name: Optional[str] = None,
    x_session_id:    Optional[str] = Header(default=None),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")

    sid       = x_session_id or str(uuid.uuid4())
    base_name = collection_name or os.path.splitext(file.filename)[0]
    full_name = _col_name(sid, base_name)

    tmp_dir  = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "source.pdf")
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    meta = get_pdf_metadata(tmp_path)
    _index_status[full_name] = {
        "status": "indexing", "pages": meta["total_pages"],
        "chunks": 0, "filename": file.filename, "session_id": sid,
    }
    _pdf_paths[full_name] = tmp_path
    register_pdf(full_name, tmp_path)
    background_tasks.add_task(_index_pdf, tmp_path, full_name, keep=True)

    return {
        "collection_name": full_name,
        "session_id":      sid,
        "filename":        file.filename,
        "total_pages":     meta["total_pages"],
        "status":          "indexing_started",
    }


def _index_pdf(pdf_path: str, collection_name: str, keep: bool = False):
    try:
        pages  = extract_text_and_tables(pdf_path)
        chunks = chunk_pages(pages, chunk_size=800, overlap=100)
        count  = index_chunks(collection_name, chunks)
        _index_status[collection_name]["status"] = "ready"
        _index_status[collection_name]["chunks"] = count
    except Exception as e:
        _index_status[collection_name]["status"] = f"error: {str(e)}"


@app.get("/status/{collection_name:path}")
def get_status(collection_name: str):
    if collection_name in _index_status:
        return _index_status[collection_name]
    if collection_exists(collection_name):
        return {"status": "ready", "collection_name": collection_name}
    raise HTTPException(404, f"Collection '{collection_name}' not found.")


@app.get("/collections")
def get_collections(x_session_id: Optional[str] = Header(default=None)):
    prefix = _session_prefix(x_session_id) if x_session_id else None
    result = []
    for c in list_collections():
        if prefix and not c.startswith(prefix):
            continue
        info = _index_status.get(c, {})
        result.append({
            "name":     c,
            "status":   info.get("status", "ready"),
            "pages":    info.get("pages", "?"),
            "chunks":   info.get("chunks", "?"),
            "filename": info.get("filename", c),
        })
    return {"collections": result}


@app.post("/query")
def query_doc(req: QueryRequest):
    _check_ready(req.collection_name)
    if not req.use_cross_ref:
        is_valid, reason = classify_intent(req.question)
        if not is_valid:
            return {
                "question": req.question, "answer": OUT_OF_DOMAIN_MESSAGE,
                "sources": [], "chunks_used": 0, "mode": "blocked", "block_reason": reason,
            }
    try:
        if req.use_cross_ref:
            result = build_evidence_chain_answer(req.collection_name, req.question)
            return {
                "question": req.question, "answer": result["answer"],
                "chain_summary": result["chain_summary"], "all_pages": result["all_pages"],
                "depth": result["depth"], "mode": "cross_reference",
            }
        chunks = query_collection(req.collection_name, req.question,
                                  n_results=req.n_results, section_filter=req.section_filter)
        result = rag_answer(req.question, chunks)
        return {
            "question": req.question, "answer": result["answer"],
            "sources": result["sources"], "chunks_used": len(chunks), "mode": "standard",
        }
    except RuntimeError as e:
        if "RATE_LIMIT" in str(e):
            raise HTTPException(429, detail=str(e).replace("RATE_LIMIT: ", ""))
        raise


@app.post("/red-flags-stream")
def red_flags_stream(req: RedFlagRequest):
    _check_ready(req.collection_name)

    def generate():
        findings = []
        total = len(RED_FLAG_CHECKS)
        for i, check in enumerate(RED_FLAG_CHECKS):
            result = run_single_check(check, req.collection_name)
            findings.append(result)
            yield _json.dumps({"check": result, "progress": i + 1, "total": total}) + "\n"
        findings.sort(key=lambda x: SEVERITY_ORDER.get(x["severity"], 5))
        sev_counts = {}
        for f in findings:
            sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
        yield _json.dumps({"done": True, "severity_summary": sev_counts, "findings": findings}) + "\n"

    return StreamingResponse(generate(), media_type="text/plain")


@app.post("/forensics")
def forensics(req: ForensicsRequest):
    _check_ready(req.collection_name)
    try:
        return check_financial_consistency(req.collection_name)
    except RuntimeError as e:
        if "RATE_LIMIT" in str(e):
            raise HTTPException(429, detail=str(e).replace("RATE_LIMIT: ", ""))
        raise


@app.post("/bear-case")
def bear_case(req: BearCaseRequest):
    _check_ready(req.collection_name)
    company = req.company_name
    if not company or company == "the Company":
        try:
            chunks = query_collection(req.collection_name,
                                      "company name incorporated our company registered", n_results=2)
            if chunks:
                from utils.llm import chat, MODEL_QUALITY
                company = chat(
                    "Extract only the full company name from this IPO prospectus text. Reply with ONLY the name.",
                    chunks[0]["text"][:500],
                    model=MODEL_QUALITY, temperature=0.0, max_tokens=20
                ).strip().strip('"\'')
        except Exception:
            company = "the Company"
    try:
        return generate_bear_case(req.collection_name, company or "the Company")
    except RuntimeError as e:
        if "RATE_LIMIT" in str(e):
            raise HTTPException(429, detail=str(e).replace("RATE_LIMIT: ", ""))
        raise


@app.get("/pdf-bytes/{collection_name:path}")
def pdf_bytes(collection_name: str):
    pdf_path = _pdf_paths.get(collection_name)
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(404, "Source PDF not available. Please re-upload the document.")
    with open(pdf_path, "rb") as f:
        content = f.read()
    return Response(content=content, media_type="application/pdf")


@app.get("/reality-check")
def reality_check(company: str = "", collection_name: str = ""):
    try:
        from utils.llm import chat, MODEL_QUALITY

        if not company and collection_name and collection_exists(collection_name):
            try:
                chunks = query_collection(collection_name,
                                          "company name incorporated our company registered", n_results=2)
                if chunks:
                    company = chat(
                        "Extract only the full company name from this IPO prospectus text. Reply with ONLY the name.",
                        chunks[0]["text"][:500],
                        model=MODEL_QUALITY, temperature=0.0, max_tokens=20
                    ).strip().strip('"\'')
            except Exception:
                pass

        if not company:
            return {"success": False, "error": "Could not determine company name."}

        system = (
            "You are a financial data assistant. "
            "Output ONLY valid JSON — no explanation, no markdown, no preamble, no thinking steps."
        )
        user = (
            f"Post-listing stock performance of {company} IPO. "
            f'Return this exact JSON: {{"company_name": "full name", "is_listed": true_or_false, '
            f'"exchange": "NSE/BSE/NYSE/etc or null", "ticker": "symbol or null", '
            f'"ipo_price": number_or_null, "ipo_date": "YYYY-MM or null", '
            f'"current_price": approximate_number_or_null, '
            f'"change_from_ipo": percentage_number_or_null, '
            f'"currency": "INR/USD/etc", '
            f'"summary": "2 sentence factual summary of post-listing performance"}}'
        )
        raw = chat(system, user, model=MODEL_QUALITY, temperature=0.0, max_tokens=300)
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        raw = re.sub(r'```[a-z]*\n?', '', raw).replace('```', '').strip()
        start = raw.find('{')
        end   = raw.rfind('}')
        if start != -1 and end > start:
            data = _json.loads(raw[start:end+1])
            return {"success": True, "data": data}
        return {"success": True, "data": {"is_listed": False, "summary": raw, "company_name": company}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/collection/{collection_name:path}")
def remove_collection(collection_name: str):
    delete_collection(collection_name)
    _index_status.pop(collection_name, None)
    _pdf_paths.pop(collection_name, None)
    return {"message": f"Deleted '{collection_name}'."}


def _check_ready(collection_name: str):
    if not collection_exists(collection_name):
        raise HTTPException(404, f"Collection '{collection_name}' not found.")
    if _index_status.get(collection_name, {}).get("status") == "indexing":
        raise HTTPException(503, "Still indexing — please wait.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api:app", host="0.0.0.0",
                port=int(os.getenv("FASTAPI_PORT", 8000)), reload=True)
