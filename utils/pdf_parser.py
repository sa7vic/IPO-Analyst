"""
PDF Parser for DRHP documents.
- Table-aware extraction using pdfplumber
- Cross-reference detection and resolution
- Section identification
"""

import re
import pdfplumber
import PyPDF2
from typing import List, Dict, Tuple, Optional


# ── Section keyword map ────────────────────────────────────────────────────────
SECTION_KEYWORDS = {
    "risk_factors":       ["risk factor", "risk factors", "risks"],
    "financials":         ["financial statements", "financial information", "profit and loss",
                           "balance sheet", "cash flow", "restated financial"],
    "business":           ["our business", "business overview", "industry overview"],
    "management":         ["management", "board of directors", "key managerial"],
    "promoters":          ["promoter", "promoter group", "promoter background"],
    "litigations":        ["litigation", "legal proceedings", "outstanding litigation"],
    "related_party":      ["related party", "related-party", "transactions with related"],
    "objects":            ["objects of the issue", "use of proceeds", "fund utilisation"],
    "summary_financials": ["summary financial", "selected financial", "key financial"],
}

XREF_PATTERN = re.compile(
    r'(?:see|refer(?:ence)?|as described in|as set out in|as stated in)\s+'
    r'(?:"([^"]+)"|'
    r'(risk factor[s]?\s+(?:no\.?\s*)?\d+)|'
    r'(annexure\s+[A-Z0-9\-]+)|'
    r'(note\s+\d+[\.\d]*)|'
    r'(page\s+\d+))',
    re.IGNORECASE
)


def extract_text_and_tables(pdf_path: str) -> List[Dict]:
    """
    Extract pages with text + tables from a PDF.
    Returns list of dicts: {page_num, text, tables, section_hint}
    """
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []

                # Flatten tables into readable text blocks
                table_text = ""
                for table in tables:
                    if table:
                        rows = []
                        for row in table:
                            cleaned = [str(c).strip() if c else "" for c in row]
                            rows.append(" | ".join(cleaned))
                        table_text += "\n[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]\n"

                combined = text + "\n" + table_text if table_text else text
                section = _detect_section(combined)

                pages.append({
                    "page_num": i + 1,
                    "text": combined.strip(),
                    "tables_raw": tables,
                    "section_hint": section,
                    "has_table": bool(tables),
                    "cross_refs": _find_cross_references(combined),
                })
    except Exception as e:
        print(f"[pdfplumber] Error: {e}. Falling back to PyPDF2.")
        pages = _fallback_pypdf2(pdf_path)

    return pages


def _fallback_pypdf2(pdf_path: str) -> List[Dict]:
    pages = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append({
                "page_num": i + 1,
                "text": text.strip(),
                "tables_raw": [],
                "section_hint": _detect_section(text),
                "has_table": False,
                "cross_refs": _find_cross_references(text),
            })
    return pages


def _detect_section(text: str) -> str:
    lower = text.lower()
    for section, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return section
    return "general"


def _find_cross_references(text: str) -> List[str]:
    matches = []
    for m in XREF_PATTERN.finditer(text):
        ref = next((g for g in m.groups() if g), None)
        if ref:
            matches.append(ref.strip())
    return list(set(matches))


def chunk_pages(pages: List[Dict], chunk_size: int = 800, overlap: int = 100) -> List[Dict]:
    """
    Split page texts into overlapping chunks for embedding.
    Each chunk carries metadata: page_num, section_hint, has_table, cross_refs.
    """
    chunks = []
    for page in pages:
        text = page["text"]
        if not text:
            continue

        words = text.split()
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk_text = " ".join(words[start:end])
            chunks.append({
                "text": chunk_text,
                "page_num": page["page_num"],
                "section_hint": page["section_hint"],
                "has_table": page["has_table"],
                "cross_refs": page["cross_refs"],
                "chunk_id": f"p{page['page_num']}_c{start}",
            })
            start += chunk_size - overlap

    return chunks


def get_pdf_metadata(pdf_path: str) -> Dict:
    """Extract basic metadata from the PDF."""
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            meta = reader.metadata or {}
            return {
                "total_pages": len(reader.pages),
                "title": meta.get("/Title", "Unknown"),
                "author": meta.get("/Author", "Unknown"),
                "subject": meta.get("/Subject", ""),
            }
    except Exception:
        return {"total_pages": 0, "title": "Unknown", "author": "Unknown", "subject": ""}
