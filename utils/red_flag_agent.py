"""
Red Flag Agent — proactively runs 12 checks on any DRHP.
Each check queries the vector store and asks the LLM to assess severity.
"""

from typing import List, Dict
from utils.vector_store import query_collection
from utils.llm import chat


# ── 12 Red Flag Checks ─────────────────────────────────────────────────────────
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
        "id": "related_party_concentration",
        "name": "Related-Party Revenue Concentration",
        "query": "related party transactions revenue sales purchases loans",
        "section": "related_party",
        "prompt": """Analyse: What % of revenue or purchases comes from related parties?
Extract: (a) total related-party revenue ₹, (b) % of total revenue, (c) party names.
Severity guide: >30% RPT revenue = HIGH, 10-30% = MEDIUM, <10% = LOW.""",
    },
    {
        "id": "auditor_qualifications",
        "name": "Auditor Qualifications / Emphasis of Matter",
        "query": "auditor qualification emphasis matter going concern disclaimer audit report",
        "section": "financials",
        "prompt": """Analyse: Are there any auditor qualifications, emphasis-of-matter paragraphs, or going-concern notes?
Extract: exact language used by auditor and the financial year affected.
Severity guide: Going concern = CRITICAL, Qualification = HIGH, Emphasis of matter = MEDIUM.""",
    },
    {
        "id": "litigation_exposure",
        "name": "Outstanding Litigations",
        "query": "litigation criminal civil tax outstanding cases amount involved",
        "section": "litigations",
        "prompt": """Analyse: What is the total quantum of outstanding litigations?
Extract: (a) total ₹ amount, (b) number of cases, (c) any criminal proceedings against promoters.
Severity guide: >20% of issue size = HIGH, 5-20% = MEDIUM, <5% = LOW.""",
    },
    {
        "id": "revenue_concentration",
        "name": "Customer / Geography Revenue Concentration",
        "query": "top customers revenue concentration single customer geographic",
        "section": "business",
        "prompt": """Analyse: How concentrated is the revenue?
Extract: (a) top-1 and top-5 customer % of revenue, (b) any single geography >50%.
Severity guide: Top customer >30% = HIGH, 10-30% = MEDIUM.""",
    },
    {
        "id": "negative_cashflow",
        "name": "Negative Operating Cash Flow",
        "query": "cash flow from operations operating activities net cash",
        "section": "financials",
        "prompt": """Analyse: Has the company had negative cash flow from operations?
Extract: operating cash flow for each of the last 3 years.
Severity guide: Negative in all 3 years = HIGH, 2 years = MEDIUM, 1 year = LOW.""",
    },
    {
        "id": "debt_levels",
        "name": "High Debt / Leverage",
        "query": "total debt borrowings long term short term debt equity ratio interest coverage",
        "section": "financials",
        "prompt": """Analyse: What is the company's debt burden?
Extract: (a) total debt, (b) debt-to-equity ratio, (c) interest coverage ratio.
Severity guide: D/E > 3x = HIGH, 1-3x = MEDIUM, <1x = LOW.""",
    },
    {
        "id": "promoter_background",
        "name": "Promoter Criminal / Regulatory History",
        "query": "promoter criminal proceedings SEBI penalty debarred disqualified",
        "section": "promoters",
        "prompt": """Analyse: Do any promoters have criminal cases, SEBI penalties, or regulatory actions?
Extract: names, nature of case, current status.
Severity guide: Criminal conviction = CRITICAL, SEBI debarment = HIGH, pending criminal case = MEDIUM.""",
    },
    {
        "id": "object_of_issue",
        "name": "Vague Use of IPO Proceeds",
        "query": "objects of issue use of proceeds general corporate purposes fund utilisation",
        "section": "objects",
        "prompt": """Analyse: How specific is the use of IPO proceeds?
Extract: (a) % going to 'general corporate purposes', (b) % for capex with specific details.
Severity guide: >25% to GCP = HIGH, 10-25% = MEDIUM.""",
    },
    {
        "id": "offer_for_sale",
        "name": "High Offer for Sale (OFS) Proportion",
        "query": "offer for sale fresh issue OFS promoter selling shareholders",
        "section": "objects",
        "prompt": """Analyse: What proportion of the IPO is Offer for Sale (promoters exiting) vs fresh issue?
Extract: (a) OFS amount, (b) fresh issue amount, (c) OFS as % of total issue.
Severity guide: OFS >70% = HIGH (promoters exiting heavily), 40-70% = MEDIUM.""",
    },
    {
        "id": "one_time_items",
        "name": "One-Time / Exceptional Items Inflating Profits",
        "query": "exceptional item one time extraordinary income profit write-back deferred tax",
        "section": "financials",
        "prompt": """Analyse: Are there exceptional or one-time items that inflate reported profit?
Extract: (a) nature of item, (b) ₹ amount, (c) adjusted PAT after removing this item.
Severity guide: >20% of PAT from one-time items = HIGH, 10-20% = MEDIUM.""",
    },
    {
        "id": "working_capital",
        "name": "Deteriorating Working Capital",
        "query": "debtors receivables inventory days payable working capital cycle",
        "section": "financials",
        "prompt": """Analyse: Is the working capital cycle worsening?
Extract: debtor days, inventory days, creditor days for last 2-3 years. Identify any sharp increase.
Severity guide: Debtor days >180 or increasing >30 days YoY = HIGH.""",
    },
]

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "CLEAR": 4, "UNKNOWN": 5}


def run_red_flag_analysis(collection_name: str) -> List[Dict]:
    """
    Run all 12 checks. Returns list of findings sorted by severity.
    """
    results = []

    for check in RED_FLAG_CHECKS:
        try:
            chunks = query_collection(
                collection_name,
                check["query"],
                n_results=5,
                section_filter=check.get("section"),
            )
            # Also try without section filter if results are sparse
            if len(chunks) < 2:
                chunks = query_collection(collection_name, check["query"], n_results=5)

            if not chunks:
                results.append({
                    "id":       check["id"],
                    "name":     check["name"],
                    "severity": "UNKNOWN",
                    "finding":  "Insufficient data found in DRHP for this check.",
                    "pages":    [],
                })
                continue

            context = "\n\n".join(
                f"[Page {c['page_num']}]\n{c['text']}" for c in chunks
            )

            system = """You are a SEBI-registered investment analyst doing red-flag screening.
Be concise. Format your response as:
SEVERITY: [CRITICAL/HIGH/MEDIUM/LOW/CLEAR]
FINDING: [2-3 sentence summary with page citations]
KEY_DATA: [bullet list of key numbers/facts extracted]"""

            finding_raw = chat(
                system,
                f"{check['prompt']}\n\nDRHP Context:\n{context}",
                temperature=0.1,
                max_tokens=400,
            )

            severity = _parse_severity(finding_raw)
            results.append({
                "id":       check["id"],
                "name":     check["name"],
                "severity": severity,
                "finding":  finding_raw,
                "pages":    [c["page_num"] for c in chunks],
            })

        except Exception as e:
            results.append({
                "id":       check["id"],
                "name":     check["name"],
                "severity": "UNKNOWN",
                "finding":  f"Error during analysis: {str(e)}",
                "pages":    [],
            })

    # Sort by severity
    results.sort(key=lambda x: SEVERITY_ORDER.get(x["severity"], 5))
    return results


def _parse_severity(text: str) -> str:
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "CLEAR"]:
        if sev in text.upper():
            return sev
    return "UNKNOWN"


SEVERITY_COLORS = {
    "CRITICAL": "#FF3B30",
    "HIGH":     "#FF9500",
    "MEDIUM":   "#FFCC00",
    "LOW":      "#34C759",
    "CLEAR":    "#30D158",
    "UNKNOWN":  "#8E8E93",
}
