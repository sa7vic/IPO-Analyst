"""
Groq API client — wraps llama-3.3-70b for all LLM calls.
Fast inference, free tier available.
"""

import os
from groq import Groq
from typing import List, Dict, Optional


def get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Add it to your .env file.")
    return Groq(api_key=api_key)


def chat(
    system_prompt: str,
    user_message: str,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """Simple chat completion."""
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def rag_answer(
    question: str,
    context_chunks: List[Dict],
    system_extra: str = "",
) -> Dict:
    """
    Answer a question using retrieved context chunks.
    Returns {answer, sources, confidence_note}.
    """
    if not context_chunks:
        return {
            "answer": "I could not find relevant information in the DRHP for this question.",
            "sources": [],
            "confidence_note": "No context retrieved.",
        }

    # Build context string with page references
    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        context_parts.append(
            f"[Source {i} | Page {chunk['page_num']} | Section: {chunk['section_hint']}]\n"
            f"{chunk['text']}"
        )
    context_str = "\n\n---\n\n".join(context_parts)

    system_prompt = f"""You are a senior investment banker and SEBI-registered analyst reviewing a DRHP (Draft Red Herring Prospectus).

Your job:
1. Answer the user's question using ONLY the provided DRHP excerpts.
2. Always cite the page number and section for every claim (e.g., "Page 47, Risk Factors").
3. If the answer involves financial figures, extract BOTH the reported figure AND any adjusted/restated figure if available.
4. Flag any one-time exceptional items that inflate/deflate a metric.
5. If the context does not contain enough information, say so explicitly — DO NOT hallucinate.
6. Be concise but thorough. Use bullet points for lists.

{system_extra}"""

    user_message = f"""Question: {question}

DRHP Excerpts:
{context_str}

Provide a structured answer with page citations."""

    answer = chat(system_prompt, user_message, temperature=0.1, max_tokens=1500)

    sources = [
        {"page": c["page_num"], "section": c["section_hint"], "relevance": c["relevance"]}
        for c in context_chunks
    ]

    return {"answer": answer, "sources": sources, "confidence_note": ""}
