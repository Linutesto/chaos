from __future__ import annotations

import math
from typing import Any, Dict, List

from .retrieval import search_memory


def search(agent_id: str, query: str, *, top_k: int = 10, k_ann: int = 100) -> List[Dict[str, Any]]:
    """Hybrid search wrapper using existing retrieval.search_memory with tunables.

    Applies time decay as freshness prior and returns normalized scores.
    """
    # Pull tunables from env
    import os
    try:
        decay = float(os.environ.get("QJSON_RETRIEVAL_DECAY", "0.0"))
    except Exception:
        decay = 0.0
    hybrid = os.environ.get("QJSON_RETRIEVAL_HYBRID", "none")
    try:
        tfidf_w = float(os.environ.get("QJSON_RETRIEVAL_TFIDF_WEIGHT", "0.3"))
    except Exception:
        tfidf_w = 0.3
    try:
        fresh_b = float(os.environ.get("QJSON_RETRIEVAL_FRESH_BOOST", "0.0"))
    except Exception:
        fresh_b = 0.0
    hits = search_memory(agent_id, query, top_k=top_k, time_decay=decay, hybrid=hybrid, tfidf_weight=tfidf_w, fresh_boost=fresh_b)
    # normalize score to [0,1]
    if not hits:
        return []
    s = [h.get("score", 0.0) for h in hits]
    lo, hi = min(s), max(s)
    rng = max(1e-6, (hi - lo))
    out: List[Dict[str, Any]] = []
    for h in hits:
        sc = (h.get("score", 0.0) - lo) / rng
        h2 = dict(h)
        h2["score"] = sc
        out.append(h2)
    return out[:top_k]

