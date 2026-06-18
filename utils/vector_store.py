"""
Vector store using ChromaDB (local, persistent, no Docker).
Uses sentence-transformers for free embeddings.
"""

import os
import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Optional


CHROMA_DIR = os.path.join(os.path.dirname(__file__), "../data/chroma_db")
EMBED_MODEL = "all-MiniLM-L6-v2"  


def _get_client():
    chroma_api_key = os.getenv("CHROMA_API_KEY")
    if chroma_api_key:
        tenant = os.getenv("CHROMA_TENANT", "default_tenant")
        database = os.getenv("CHROMA_DATABASE", "default_database")
        cloud_host = os.getenv("CHROMA_CLOUD_HOST")
        if cloud_host:
            cloud_port = int(os.getenv("CHROMA_CLOUD_PORT", "443"))
            return chromadb.CloudClient(
                api_key=chroma_api_key,
                tenant=tenant,
                database=database,
                cloud_host=cloud_host,
                cloud_port=cloud_port
            )
        else:
            return chromadb.CloudClient(
                api_key=chroma_api_key,
                tenant=tenant,
                database=database
            )

    chroma_host = os.getenv("CHROMA_HOST")
    if chroma_host:
        ssl = os.getenv("CHROMA_SSL", "False").lower() in ("true", "1", "yes")
        port = os.getenv("CHROMA_PORT")
        
        # Auto-detect scheme and clean host
        if chroma_host.startswith("https://"):
            ssl = True
            chroma_host = chroma_host[8:]
            if not port:
                port = "443"
        elif chroma_host.startswith("http://"):
            chroma_host = chroma_host[7:]
            if not port:
                port = "80"
                
        # Clean trailing slashes or paths if present
        if "/" in chroma_host:
            chroma_host = chroma_host.split("/")[0]
            
        port_val = int(port) if port else 8000
        
        headers = {}
        auth_token = os.getenv("CHROMA_AUTH_TOKEN")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
            
        tenant = os.getenv("CHROMA_TENANT", "default_tenant")
        database = os.getenv("CHROMA_DATABASE", "default_database")
        
        return chromadb.HttpClient(
            host=chroma_host,
            port=port_val,
            ssl=ssl,
            headers=headers,
            tenant=tenant,
            database=database
        )
    else:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        return chromadb.PersistentClient(path=CHROMA_DIR)


def _get_ef():
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )


def get_or_create_collection(collection_name: str):
    client = _get_client()
    ef = _get_ef()
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def index_chunks(collection_name: str, chunks: List[Dict]) -> int:

    collection = get_or_create_collection(collection_name)

    batch_size = 500
    total = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i: i + batch_size]
        ids       = [c["chunk_id"] for c in batch]
        documents = [c["text"] for c in batch]
        metadatas = [
            {
                "page_num":     str(c["page_num"]),
                "section_hint": c["section_hint"],
                "has_table":    str(c["has_table"]),
                "cross_refs":   ", ".join(c.get("cross_refs", [])),
            }
            for c in batch
        ]

        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        total += len(batch)

    return total


def query_collection(
    collection_name: str,
    query: str,
    n_results: int = 8,
    section_filter: Optional[str] = None,
) -> List[Dict]:
    collection = get_or_create_collection(collection_name)

    where = {"section_hint": section_filter} if section_filter else None

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    docs  = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    for doc, meta, dist in zip(docs, metas, dists):
        output.append({
            "text":         doc,
            "page_num":     meta.get("page_num", "?"),
            "section_hint": meta.get("section_hint", "general"),
            "has_table":    meta.get("has_table", "False") == "True",
            "cross_refs":   meta.get("cross_refs", ""),
            "relevance":    round(1 - dist, 4),
        })

    return output


def collection_exists(collection_name: str) -> bool:
    client = _get_client()
    existing = [c.name for c in client.list_collections()]
    return collection_name in existing


def delete_collection(collection_name: str):
    client = _get_client()
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass


def list_collections() -> List[str]:
    client = _get_client()
    return [c.name for c in client.list_collections()]
