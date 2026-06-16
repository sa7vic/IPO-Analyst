"""
Intent Classification Guardrail.
Uses a fast keyword + pattern check first (zero tokens), falls back to a lightweight Qwen call only for ambiguous cases.
"""

import re
from typing import Tuple

# ── Hard-block patterns ─────────────────────────────────
BLOCK_PATTERNS = [
    r"\bwrite\s+a\s+(poem|song|story|haiku|limerick|rap|essay|letter)\b",
    r"\b(capital\s+of|president\s+of|prime\s+minister\s+of)\b",
    r"\b(recipe|ingredient|cook|weather|temperature|climate)\b",
    r"\b(joke|funny|humor|meme|trivia)\b",
    r"\btranslate\s+(this|to|from)\b",
    r"\b(who\s+is|what\s+is)\s+(the\s+)?(best|worst|most\s+famous)\b",
    r"\bsports?\b.*\b(score|team|player|match|game|tournament)\b",
    r"\b(movie|film|show|series|netflix|spotify|youtube)\b",
    r"\b(stock\s+price|share\s+price)\s+of\s+(?!.*drhp|.*prospectus|.*ipo)",
]

# ── Domain keywords — if ANY present, allow immediately ────────────────────────
FINANCIAL_KEYWORDS = [
    "revenue", "profit", "loss", "ebitda", "pat", "eps", "cash flow", "balance sheet",
    "debt", "equity", "borrowing", "leverage", "ratio", "margin", "valuation",
    "ipo", "drhp", "prospectus", "s-1", "sebi", "sec", "filing",
    "promoter", "auditor", "litigation", "risk factor", "related party",
    "dividend", "shares", "allotment", "offer for sale", "fresh issue",
    "financial", "annual report", "quarterly", "restated", "consolidated",
    "assets", "liabilities", "working capital", "receivable", "payable",
    "investment", "acquisition", "merger", "subsidiary", "holding",
    "compliance", "regulatory", "disclosure", "annexure", "note",
    "page", "section", "document", "company", "business", "industry",
]


def classify_intent(question: str) -> Tuple[bool, str]:
    """
    Returns (is_valid, reason).
    is_valid=True  → proceed with RAG
    is_valid=False → return out-of-domain error
    """
    q_lower = question.lower().strip()

    if len(q_lower) < 8:
        return True, "short query"

    for pattern in BLOCK_PATTERNS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return False, f"Matched out-of-domain pattern: {pattern}"

    for kw in FINANCIAL_KEYWORDS:
        if kw in q_lower:
            return True, f"Financial keyword: {kw}"
    return _llm_classify(question)


def _llm_classify(question: str) -> Tuple[bool, str]:
    try:
        from utils.llm import chat, MODEL_ANALYSIS
        system = (
            "You are a query classifier for a financial due diligence tool. "
            "Classify if the query is relevant to: IPO analysis, DRHP/S-1 review, "
            "financial statements, company due diligence, risk assessment, or investment analysis. "
            "Reply with ONLY 'RELEVANT' or 'NOT_RELEVANT'."
        )
        result = chat(system, f"Query: {question}", model=MODEL_ANALYSIS,
                      temperature=0.0, max_tokens=5)
        is_relevant = "RELEVANT" in result.upper() and "NOT_RELEVANT" not in result.upper()
        return is_relevant, result.strip()
    except Exception:
        return True, "classification_error_fail_open"


OUT_OF_DOMAIN_MESSAGE = (
    "This query is outside the scope of this tool. "
    "IPO Analyst is designed for financial due diligence on IPO prospectuses — "
    "ask about financials, risk factors, promoters, litigation, use of proceeds, "
    "auditor opinions, or any other content from the uploaded document."
)