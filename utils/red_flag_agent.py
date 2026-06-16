"""
Red Flag Agent
"""

from typing import List, Dict
from utils.vector_store import query_collection
from utils.llm import chat, MODEL_QUALITY


RED_FLAG_CHECKS = [
    {
        "id": "promoter_pledge",
        "name": "Promoter Share Pledging",
        "query": "promoter shares pledged encumbered collateral loan",
        "section": None,
        "prompt": """Analyse: Are any promoter shares pledged or encumbered?
Extract: (a) % of promoter holding pledged, (b) total value, (c) lender names if mentioned.
Severity guide: >30% pledged = HIGH, 10-30% = MEDIUM, <10% = LOW, none = CLEAR.""",
    },
    {
        "id": "related_party",
        "name": "Related-Party Transactions",
        "query": "related party transactions revenue sales purchases loans",
        "section": "related_party",
        "prompt": """Analyse: What % of revenue or purchases comes from related parties?
Extract: (a) total related-party revenue ₹, (b) % of total revenue, (c) party names.
Severity guide: >30% RPT revenue = HIGH, 10-30% = MEDIUM, <10% = LOW.""",
    },
    {
        "id": "auditor_qualifications",
        "name": "Auditor Qualifications",
        "query": "auditor qualification emphasis matter going concern disclaimer audit report",
        "section": "financials",
        "prompt": """Analyse: Are there any auditor qualifications, emphasis-of-matter paragraphs, or going-concern notes?
Extract: exact language used by auditor and the financial year affected.
Severity guide: Going concern = CRITICAL, Qualification = HIGH, Emphasis of matter = MEDIUM.""",
    },
    {
        "id": "litigation",
        "name": "Outstanding Litigations",
        "query": "litigation criminal civil tax outstanding cases amount involved",
        "section": "litigations",
        "prompt": """Analyse: What is the total quantum of outstanding litigations?
Extract: (a) total ₹ amount, (b) number of cases, (c) any criminal proceedings against promoters.
Severity guide: >20% of issue size = HIGH, 5-20% of issue size = MEDIUM, <5% = LOW.""",
    },
    {
        "id": "cashflow",
        "name": "Negative Operating Cash Flow",
        "query": "cash flow from operations operating activities net cash consolidated",
        "section": "financials",
        "prompt": """Analyse: Has the company had negative cash flow from operations?
Extract: operating cash flow for each of the last 3 years (use consolidated figures).
Severity guide: Negative all 3 years = HIGH, 2 years = MEDIUM, 1 year = LOW, all positive = CLEAR.""",
    },
    {
        "id": "debt",
        "name": "Debt & Leverage",
        "query": "total debt borrowings long term short term debt equity ratio interest coverage",
        "section": "financials",
        "prompt": """Analyse: What is the company's debt burden?
Extract: (a) total debt, (b) debt-to-equity ratio, (c) interest coverage ratio.
Severity guide: D/E >3x = HIGH, 1-3x = MEDIUM, <1x = LOW.""",
    },
    {
        "id": "ofs",
        "name": "OFS & Use of Proceeds",
        "query": "offer for sale fresh issue OFS promoter selling shareholders general corporate purposes",
        "section": "objects",
        "prompt": """Analyse: What proportion of the IPO is Offer for Sale vs fresh issue? How are proceeds used?
Extract: (a) OFS amount and %, (b) fresh issue amount, (c) % going to general corporate purposes.
Severity guide: OFS >70% = HIGH, 40-70% = MEDIUM. GCP >25% = HIGH, 10-25% = MEDIUM.""",
    },
    {
        "id": "exceptional_items",
        "name": "Exceptional Items & Earnings Quality",
        "query": "exceptional item one time extraordinary income profit write-back deferred tax",
        "section": "financials",
        "prompt": """Analyse: Are there exceptional or one-time items that inflate reported profit?
Extract: (a) nature of item, (b) ₹ amount, (c) adjusted PAT after removing this item.
Severity guide: >20% of PAT from one-time items = HIGH, 10-20% = MEDIUM.""",
    },
    {
        "id": "pvd",
        "name": "Promoter Valuation Delta",
        "query": "capital structure shares allotted issue price per share private placement pre-IPO allotment",
        "section": None,
        "prompt": """Analyse: Were shares allotted to insiders/promoters in the 12 months before this IPO at a lower price?
Extract: (a) last insider allotment price per share, (b) date, (c) IPO floor/issue price.
Calculate PVD = ((IPO Price - Insider Price) / Insider Price) * 100
Severity guide: PVD >800% = CRITICAL, 400-800% = HIGH, 200-400% = MEDIUM, 100-200% = LOW, <100% = CLEAR.
If data not found, state UNKNOWN.""",
    },
]

SEVERITY_ORDER  = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "CLEAR": 4, "UNKNOWN": 5}
SEVERITY_COLORS = {
    "CRITICAL": "#FF3B30", "HIGH": "#FF9500", "MEDIUM": "#FFCC00",
    "LOW": "#34C759",      "CLEAR": "#30D158", "UNKNOWN": "#8E8E93",
}


def _parse_severity(text: str) -> str:
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "CLEAR"]:
        if sev in text.upper():
            return sev
    return "UNKNOWN"


def run_single_check(check: Dict, collection_name: str) -> Dict:
    try:
        chunks = query_collection(
            collection_name,
            check["query"],
            n_results=5,
            section_filter=check.get("section"),
        )
        if len(chunks) < 2:
            chunks = query_collection(collection_name, check["query"], n_results=5)

        if not chunks:
            return {
                "id":       check["id"],
                "name":     check["name"],
                "severity": "UNKNOWN",
                "finding":  "Insufficient data found in document for this check.",
                "pages":    [],
            }
        context = "\n\n".join(
            f"[Page {c['page_num']}]\n{c['text']}" for c in chunks
        )

        system = """You are a SEBI-registered investment analyst doing red-flag screening on an IPO prospectus.
Be concise. Format your response as:
SEVERITY: [CRITICAL/HIGH/MEDIUM/LOW/CLEAR]
FINDING: [2-3 sentence summary with page citations]
KEY_DATA: [bullet list of key numbers/facts extracted]"""

        finding_raw = chat(
            system,
            f"{check['prompt']}\n\nProspectus Context:\n{context}",
            model=MODEL_QUALITY,
            temperature=0.1,
            max_tokens=400,
        )

        return {
            "id":       check["id"],
            "name":     check["name"],
            "severity": _parse_severity(finding_raw),
            "finding":  finding_raw,
            "pages":    [c["page_num"] for c in chunks],
        }

    except Exception as e:
        return {
            "id":       check["id"],
            "name":     check["name"],
            "severity": "UNKNOWN",
            "finding":  f"Error: {str(e)}",
            "pages":    [],
        }
