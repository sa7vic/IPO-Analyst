"""
Analyst Agents — Qwen3-32B.
Bear Case + Financial Forensics only.
"""

import re
from typing import Dict, List
from utils.vector_store import query_collection
from utils.llm import chat, MODEL_ANALYSIS


def _strip_thinking(text: str) -> str:
    
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    for marker in ['## ', 'FLAG:', 'SEVERITY:', '**RISK', '# ']:
        idx = text.find(marker)
        if idx > 0:
            preamble = text[:idx].strip()
            
            if len(preamble) > 100 and not preamble.startswith('SEVERITY'):
                text = text[idx:].strip()
                break

    return text


def _get_context(collection_name: str, queries: List[str],
                 n_per_query: int = 2, char_limit: int = 500) -> str:
    all_chunks, seen = [], set()
    for q in queries:
        chunks = query_collection(collection_name, q, n_results=n_per_query)
        for c in chunks:
            if c["page_num"] not in seen:
                seen.add(c["page_num"])
                all_chunks.append(f"[Pg {c['page_num']} | {c['section_hint']}] {c['text'][:char_limit]}")
    return "\n\n".join(all_chunks[:8])


def generate_bear_case(collection_name: str, company_name: str = "the Company") -> Dict:
    context = _get_context(collection_name, [
        "related party transactions loans advances subsidiaries conflict interest",
        "litigation criminal civil tax outstanding contingent liability",
        "cash flow operations negative loss making EBITDA",
        "promoter pledging encumbered shares allotment history",
        "auditor qualification emphasis matter going concern",
        "debt borrowings repayment obligation covenant",
        "exceptional one time item adjusted PAT restated",
        "offer for sale OFS general corporate purposes objects",
        "regulatory SEBI RBI penalty non-compliance",
    ], n_per_query=2, char_limit=500)

    system = (
        "You are a forensic equity analyst reviewing an IPO prospectus. "
        "Output only the final analysis — no reasoning preamble, no thinking steps. "
        "Start directly with ## RISK OVERVIEW. "
        "Surface material risks disclosed but not prominently highlighted. "
        "Focus on financial, governance, and structural risks only. "
        "Cite page numbers for every claim. Be specific with numbers."
    )

    user_msg = f"""Material risk analysis for {company_name}.

## RISK OVERVIEW
[2-3 sentence summary of most material financial and governance concerns]

## RISK #1 — [Specific name]
Evidence: [exact data with page number]
Why it matters: [financial or governance consequence]

## RISK #2 — [Specific name]
Evidence: [exact data with page number]
Why it matters: [consequence]

## RISK #3 — [Specific name]
Evidence: [exact data with page number]
Why it matters: [consequence]

## RISK #4 — [Specific name]
Evidence: [exact data with page number]
Why it matters: [consequence]

## RISK #5 — [Specific name]
Evidence: [exact data with page number]
Why it matters: [consequence]

## WHAT IS BURIED
[Disclosed facts buried in footnotes/annexures not on cover page]

## RISK PATTERN
[Pattern across risks — e.g. financial distress, governance gaps, exit-heavy structure]

Excerpts:
{context}"""

    raw = chat(system, user_msg, model=MODEL_ANALYSIS, temperature=0.1, max_tokens=1000)
    result = _strip_thinking(raw)
    return {"bear_case": result}


def check_financial_consistency(collection_name: str) -> Dict:
    context = _get_context(collection_name, [
        "restated statement of assets liabilities total equity shareholders funds",
        "total borrowings long term short term debt net worth",
        "revenue from operations total income financial year ended",
        "cash flow from operations activities net cash used",
        "profit after tax PAT net loss EBITDA operating profit",
        "exceptional extraordinary one time item write back",
        "trade receivables debtors days outstanding collection",
        "audit qualification emphasis matter opinion going concern",
    ], n_per_query=2, char_limit=500)

    system = (
        "You are a forensic accountant analysing an IPO prospectus for earnings quality. "
        "Output only the final analysis — no reasoning preamble, no thinking steps. "
        "Start directly with FLAG: or EARNINGS QUALITY:. "
        "Identify specific numerical inconsistencies. Cite page numbers."
    )

    user_msg = f"""Financial forensics review. For each concern found:

FLAG: [Name]
DATA: [Specific numbers with page citations]
INTERPRETATION: [What this pattern may indicate]
SEVERITY: HIGH / MEDIUM / LOW

End with:
EARNINGS QUALITY: HIGH / MEDIUM / LOW
REASONING: [2 sentences based only on data found]

Data:
{context}"""

    raw = chat(system, user_msg, model=MODEL_ANALYSIS, temperature=0.1, max_tokens=800)
    result = _strip_thinking(raw)

    flags, current = [], {}
    for line in result.split("\n"):
        s = line.strip()
        if s.startswith("FLAG:"):
            if current: flags.append(current)
            current = {"name": s.replace("FLAG:", "").strip(), "details": []}
        elif s.startswith("SEVERITY:") and current:
            current["severity"] = s.replace("SEVERITY:", "").strip()
        elif current and s and not s.startswith("EARNINGS QUALITY") and not s.startswith("REASONING"):
            current["details"].append(s)
    if current: flags.append(current)

    eq_line = ""
    for line in result.split("\n"):
        if line.strip().startswith("EARNINGS QUALITY"):
            eq_line = line.strip()
            break

    return {"flags": flags, "earnings_quality": eq_line, "analysis": result}