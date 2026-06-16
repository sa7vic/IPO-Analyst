"""
Groq LLM client — paced, model-split, clean error handling.
Model split:
  Chat Q&A      → llama-3.3-70b-versatile   
  Red Flags     → llama-3.3-70b-versatile           
  Forensics     → qwen/qwen3-32b
  Snapshot val  → qwen/qwen3-32b
"""

import os, time, threading
from groq import Groq
from typing import List, Dict

_lock         = threading.Lock()
_last_call_ts = 0.0
MIN_GAP       = 2.2   

MODEL_QUALITY  = "llama-3.3-70b-versatile"
MODEL_ANALYSIS = "qwen/qwen3-32b"
MODEL_FAST     = MODEL_ANALYSIS  


def _pace():
    global _last_call_ts
    with _lock:
        elapsed = time.time() - _last_call_ts
        if elapsed < MIN_GAP:
            time.sleep(MIN_GAP - elapsed)
        _last_call_ts = time.time()


def get_client() -> Groq:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise ValueError("GROQ_API_KEY not set in .env")
    return Groq(api_key=key)


def chat(
    system_prompt: str,
    user_message:  str,
    model:         str   = MODEL_QUALITY,
    temperature:   float = 0.2,
    max_tokens:    int   = 1024,
) -> str:
    _pace()
    try:
        resp = get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower() or "rate limit" in err.lower():
            raise RuntimeError(
                "RATE_LIMIT: Groq rate limit reached. Wait ~60 seconds and try again."
            ) from None
        raise


def rag_answer(question: str, context_chunks: List[Dict], system_extra: str = "") -> Dict:
    if not context_chunks:
        return {"answer": "No relevant information found in the document.",
                "sources": [], "confidence_note": ""}

    parts = []
    for i, c in enumerate(context_chunks, 1):
        text = c["text"][:700] + ("…" if len(c["text"]) > 700 else "")
        parts.append(f"[Source {i} | Page {c['page_num']} | {c['section_hint']}]\n{text}")

    system = (
        "You are a senior analyst reviewing an IPO prospectus (DRHP or S-1).\n"
        "Rules:\n"
        "1. Answer ONLY from the provided excerpts — never hallucinate.\n"
        "2. Cite page number for every specific claim: (Page 47).\n"
        "3. For financial figures, state both reported and adjusted figures if present.\n"
        "4. Flag any one-time or exceptional items explicitly.\n"
        "5. If the answer is not in the excerpts, say so clearly.\n"
        "6. Be concise. Use bullet points where helpful.\n"
        + system_extra
    )

    answer = chat(system,
                  f"Question: {question}\n\nExcerpts:\n" + "\n\n---\n\n".join(parts),
                  model=MODEL_QUALITY, temperature=0.1, max_tokens=1200)

    sources = [{"page": c["page_num"], "section": c["section_hint"],
                "relevance": c["relevance"]} for c in context_chunks]
    return {"answer": answer, "sources": sources, "confidence_note": ""}
