"""
Citation Visual Grounding — renders a cropped PNG of the exact page region cited.
"""

import os, io, tempfile
import pdfplumber
from typing import Optional, Tuple

_pdf_store: dict = {}


def register_pdf(collection_name: str, pdf_path: str):
    _pdf_store[collection_name] = pdf_path


def get_page_snippet(collection_name: str, page_num: int) -> Optional[bytes]:
    pdf_path = _pdf_store.get(collection_name)
    if not pdf_path or not os.path.exists(pdf_path):
        return None

    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc  = fitz.open(pdf_path)
        page = doc[page_num - 1]
        mat  = fitz.Matrix(1.5, 1.5)
        pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        return pix.tobytes("png")
    except Exception:
        pass

    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, first_page=page_num,
                                   last_page=page_num, dpi=120)
        if images:
            buf = io.BytesIO()
            images[0].save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        pass

    return None


def get_page_text_excerpt(collection_name: str, page_num: int,
                           highlight_query: Optional[str] = None) -> str:
    pdf_path = _pdf_store.get(collection_name)
    if not pdf_path or not os.path.exists(pdf_path):
        return "Source PDF not available for this session."
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num < 1 or page_num > len(pdf.pages):
                return f"Page {page_num} out of range."
            text = pdf.pages[page_num - 1].extract_text() or ""
            return text[:1500]
    except Exception as e:
        return f"Could not extract page text: {e}"