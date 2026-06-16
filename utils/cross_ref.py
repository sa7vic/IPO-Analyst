"""
Cross-Reference Resolution Agent.
Builds evidence chains by following nested references in a DRHP:
Risk Factor → Annexure → Financial Note → Legal Proceedings
"""

import re
from typing import List, Dict, Optional
from utils.vector_store import query_collection
from utils.llm import chat

REF_PATTERNS = [
    (r'risk\s+factor[s]?\s+(?:no\.?\s*)?(\d+)', "risk_factor"),
    (r'annexure[s]?\s+([A-Z0-9\-]+)',             "annexure"),
    (r'note\s+(\d+[\.\d]*)',                       "financial_note"),
    (r'page[s]?\s+(\d+)',                          "page_ref"),
    (r'section\s+(\d+[\.\d]*)',                    "section_ref"),
    (r'schedule\s+([A-Z0-9\-]+)',                  "schedule"),
    (r'legal\s+proceedings?\s+(?:no\.?\s*)?(\d+)', "legal_proceeding"),
]


def _extract_refs(text: str) -> List[Dict]:
    found = []
    for pattern, ref_type in REF_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            found.append({"type": ref_type, "id": m.group(1), "raw": m.group(0)})
    seen = set()
    unique = []
    for r in found:
        key = f"{r['type']}:{r['id']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _fetch_ref_context(collection_name: str, ref: Dict, n_results: int = 3) -> List[Dict]:
    query_map = {
        "risk_factor":      f"risk factor {ref['id']} risk",
        "annexure":         f"annexure {ref['id']}",
        "financial_note":   f"note {ref['id']} financial statements accounting",
        "page_ref":         f"page {ref['id']}",
        "section_ref":      f"section {ref['id']}",
        "schedule":         f"schedule {ref['id']}",
        "legal_proceeding": f"legal proceedings case {ref['id']} litigation",
    }
    query = query_map.get(ref["type"], ref["raw"])
    return query_collection(collection_name, query, n_results=n_results)


def resolve_cross_references(
    collection_name: str,
    seed_query: str,
    max_depth: int = 3,
    max_refs_per_level: int = 3,
) -> Dict:
    """
    Starting from a seed query, recursively follow cross-references
    to build a full evidence chain.

    Returns:
        {
            "seed_chunks": [...],
            "chain": [
                {"level": 1, "ref": {...}, "chunks": [...], "refs_found": [...]},
                ...
            ],
            "all_pages": [list of all pages touched],
            "depth_reached": int,
        }
    """
    visited_refs = set()
    chain = []
    all_pages = set()

    seed_chunks = query_collection(collection_name, seed_query, n_results=6)
    for c in seed_chunks:
        all_pages.add(c["page_num"])

    seed_text = " ".join(c["text"] for c in seed_chunks)
    current_refs = _extract_refs(seed_text)[:max_refs_per_level]

    for depth in range(1, max_depth + 1):
        if not current_refs:
            break

        next_refs = []
        for ref in current_refs:
            ref_key = f"{ref['type']}:{ref['id']}"
            if ref_key in visited_refs:
                continue
            visited_refs.add(ref_key)

            chunks = _fetch_ref_context(collection_name, ref)
            if not chunks:
                continue

            for c in chunks:
                all_pages.add(c["page_num"])

            level_text = " ".join(c["text"] for c in chunks)
            deeper_refs = _extract_refs(level_text)[:max_refs_per_level]
            next_refs.extend(deeper_refs)

            chain.append({
                "level":      depth,
                "ref":        ref,
                "chunks":     chunks,
                "refs_found": deeper_refs,
            })

        current_refs = next_refs

    return {
        "seed_chunks":   seed_chunks,
        "chain":         chain,
        "all_pages":     sorted(all_pages),
        "depth_reached": len(set(n["level"] for n in chain)) if chain else 0,
    }


def build_evidence_chain_answer(
    collection_name: str,
    question: str,
) -> Dict:
    resolution = resolve_cross_references(collection_name, question)

    context_parts = []

    for c in resolution["seed_chunks"]:
        context_parts.append(
            f"[SEED | Page {c['page_num']} | {c['section_hint']}]\n{c['text']}"
        )

    for node in resolution["chain"]:
        ref = node["ref"]
        for c in node["chunks"]:
            context_parts.append(
                f"[LEVEL {node['level']} via {ref['type'].upper()} {ref['id']} "
                f"| Page {c['page_num']}]\n{c['text']}"
            )

    context_str = "\n\n---\n\n".join(context_parts[:12])  # cap at 12 chunks

    chain_summary = "Direct retrieval only (no cross-references found)."
    if resolution["chain"]:
        steps = []
        for node in resolution["chain"]:
            ref = node["ref"]
            steps.append(f"Level {node['level']}: {ref['type'].replace('_',' ').title()} {ref['id']}")
        chain_summary = " → ".join(steps)

    system = """You are a senior SEBI-registered investment analyst.
You have been given DRHP excerpts retrieved via cross-reference chain resolution.
The context includes both the primary source AND all referenced documents/annexures/notes.

Rules:
1. Answer using ONLY the provided context.
2. Cite EVERY claim with page number and level (e.g. "Page 47, via Annexure C").
3. If you find contradictions across levels, flag them explicitly.
4. Extract adjusted financial figures separately from reported figures.
5. If a reference leads to a material risk, highlight it clearly.
6. Be concise but thorough. Use bullet points."""

    user_msg = f"""Question: {question}

Cross-Reference Chain Resolved: {chain_summary}
Pages Covered: {resolution['all_pages']}

Context (multi-level):
{context_str}

Provide a structured answer with evidence chain citations."""

    answer = chat(system, user_msg, temperature=0.1, max_tokens=1500)

    return {
        "answer":        answer,
        "chain_summary": chain_summary,
        "chain":         resolution["chain"],
        "all_pages":     resolution["all_pages"],
        "depth":         resolution["depth_reached"],
        "seed_chunks":   resolution["seed_chunks"],
    }