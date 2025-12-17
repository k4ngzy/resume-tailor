from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from sentence_transformers import SentenceTransformer

from backend.job_index import DEFAULT_COLLECTION, DEFAULT_DB_PATH, DEFAULT_MODEL, get_collection, load_embedding_model


def _use_local_only() -> bool:
    value = os.getenv("JOB_EMBEDDING_LOCAL_ONLY", "true").strip().lower()
    return value not in {"0", "false", "no"}


@lru_cache(maxsize=1)
def get_job_collection():
    db_path = Path(os.getenv("JOB_CHROMA_PATH", str(DEFAULT_DB_PATH)))
    collection_name = os.getenv("JOB_CHROMA_COLLECTION", DEFAULT_COLLECTION)
    return get_collection(db_path, collection_name, reset=False)


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    model_name = os.getenv("JOB_EMBEDDING_MODEL", DEFAULT_MODEL)
    device = os.getenv("JOB_EMBEDDING_DEVICE", "cpu")
    return load_embedding_model(model_name=model_name, device=device, local_only=_use_local_only())


def embed_text(text: str) -> List[float]:
    model = get_embedding_model()
    embedding = model.encode(
        [text],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return embedding[0].tolist()


def query_jobs(
    resume_text: str,
    top_k: int = 20,
    job_category: Optional[str] = None,
) -> List[Dict[str, str]]:
    collection = get_job_collection()
    if collection.count() == 0:
        return []

    query_embedding = embed_text(resume_text)
    where = {"job_category": job_category} if job_category else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["metadatas"],
    )
    return results.get("metadatas", [[]])[0] or []
