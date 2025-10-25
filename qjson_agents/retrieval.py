#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal persistent retrieval for qjson-agents.

- Stores memories in SQLite with float32 embeddings (L2-normalized).
- Embeds via Ollama /api/embeddings (default: nomic-embed-text).
- Cosine similarity + optional time decay.
- Simple API: add_memory(), add_batch(), search_memory(), inject_for_prompt().

Notes
- No hard dependency on requests/sentence-transformers; uses stdlib urllib. If
  Ollama is not running and sentence-transformers is unavailable, falls back to
  a deterministic hashed embedding so features remain usable.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Iterable, List, Dict, Optional, Tuple, Any

import urllib.request as _urlreq
import urllib.error as _urlerr
import hashlib as _hash
import math as _math
from array import array as _array

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional
    np = None  # type: ignore

# FMM-backed IVF-like index (FAISS-ish) utilities
from .fmm_store import PersistentFractalMemory


# ------------ Config ------------
def _default_db_path() -> str:
    # Prefer state/ if available; else ~/.qjson/
    agh = os.environ.get("QJSON_AGENTS_HOME")
    if agh:
        return str(Path(agh) / "retrieval.sqlite3")
    return str(Path.home() / ".qjson" / "memory.sqlite3")


DB_PATH = os.environ.get("QJSON_MEM_DB", _default_db_path())
_OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBED_URL = os.environ.get("QJSON_EMBED_URL", f"{_OLLAMA_BASE}/api/embeddings")
try:
    EMBED_TIMEOUT = float(os.environ.get("QJSON_EMBED_TIMEOUT", "6.0"))
except Exception:
    EMBED_TIMEOUT = 6.0
EMBED_MODEL = os.environ.get("QJSON_EMBED_MODEL", "nomic-embed-text")
DIM = int(os.environ.get("QJSON_EMBED_DIM", "768"))  # adjust to your model dimension
TOP_K_DEFAULT = 8
# --------------------------------

# Performance knobs (scan limits and time budgets)
try:
    SCAN_MAX = int(os.environ.get("QJSON_RETR_SCAN_MAX", "5000"))
except Exception:
    SCAN_MAX = 5000
try:
    RECENT_LIMIT = int(os.environ.get("QJSON_RETR_RECENT_LIMIT", "2000"))
except Exception:
    RECENT_LIMIT = 2000


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
    CREATE TABLE IF NOT EXISTS memories(
        id INTEGER PRIMARY KEY,
        agent_id TEXT NOT NULL,
        ts REAL NOT NULL,
        text TEXT NOT NULL,
        meta TEXT NOT NULL,
        vec BLOB NOT NULL
    );
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_mem_agent ON memories(agent_id);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_mem_ts ON memories(ts);")
    # Migrations: add fingerprint + freq if missing
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(memories);")}
        if "fingerprint" not in cols:
            con.execute("ALTER TABLE memories ADD COLUMN fingerprint TEXT;")
        if "freq" not in cols:
            con.execute("ALTER TABLE memories ADD COLUMN freq INTEGER DEFAULT 1;")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mem_fp ON memories(agent_id, fingerprint);")
    except Exception:
        pass
    con.commit()
    return con


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table});")}
        return column in cols
    except Exception:
        return False


def _norm_list(v: List[float]) -> List[float]:
    n = _math.sqrt(sum(x*x for x in v)) + 1e-12
    return [float(x / n) for x in v]


def _align_dim(v: List[float], dim: int) -> List[float]:
    """Truncate or zero-pad vector to the requested dim, then renormalize."""
    if len(v) > dim:
        v = v[:dim]
    elif len(v) < dim:
        v = v + [0.0] * (dim - len(v))
    return _norm_list(v)


def _vec_to_bytes(v: List[float]) -> bytes:
    a = _array('f', v)
    return a.tobytes()


def _bytes_to_vec(b: bytes) -> List[float]:
    a = _array('f')
    a.frombytes(b)
    return [float(x) for x in a]


def _normalize_text(t: str) -> str:
    return " ".join((t or "").strip().lower().split())


def _fingerprint(text: str) -> str:
    return _hash.sha1(_normalize_text(text).encode("utf-8")).hexdigest()


def _post_json(url: str, payload: Dict, *, timeout: float | None = None) -> Dict:
    data = json.dumps(payload).encode("utf-8")
    req = _urlreq.Request(url, data=data, headers={"Content-Type": "application/json"})
    to = EMBED_TIMEOUT if timeout is None else timeout
    with _urlreq.urlopen(req, timeout=to) as resp:  # type: ignore
        body = resp.read()
        return json.loads(body.decode("utf-8"))


_OLLAMA_READY: Optional[bool] = None


def _ollama_is_ready() -> bool:
    global _OLLAMA_READY
    if _OLLAMA_READY is not None:
        return _OLLAMA_READY
    # Quick ping: POST to embeddings with a tiny prompt and a short timeout
    try:
        _post_json(EMBED_URL, {"model": os.environ.get("QJSON_EMBED_MODEL", "nomic-embed-text"), "prompt": "ping"}, timeout=2.0)
        _OLLAMA_READY = True
    except Exception:
        _OLLAMA_READY = False
    return _OLLAMA_READY


def _embed_ollama(texts: List[str]) -> List[List[float]]:
    if not _ollama_is_ready():
        raise RuntimeError("ollama embeddings not reachable")
    vecs: List[List[float]] = []
    for t in texts:
        obj = _post_json(EMBED_URL, {"model": EMBED_MODEL, "prompt": t})
        emb = obj.get("embedding")
        if not isinstance(emb, list):
            raise RuntimeError("Invalid embedding response shape")
        v = [float(x) for x in emb]
        vecs.append(_norm_list(v))
    return vecs


def _embed_fallback_transformers(texts: List[str]) -> List[List[float]]:  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore

    mdl = SentenceTransformer("all-MiniLM-L6-v2")
    v = mdl.encode(texts, normalize_embeddings=True)
    out: List[List[float]] = []
    for row in v:
        out.append([float(x) for x in row])
    return out


def _embed_hash(texts: List[str]) -> List[List[float]]:
    # Deterministic hashed embedding (feature hashing) as a last resort (no numpy).
    out: List[List[float]] = []
    for t in texts:
        v = [0.0] * DIM
        toks = [w for w in t.lower().split() if w]
        for w in toks[:512]:
            d = _hash.sha256(w.encode("utf-8")).digest()
            for k in range(0, 16, 4):
                idx = int.from_bytes(d[k:k+2], 'big') % DIM
                sgn = 1.0 if (d[k+2] & 1) else -1.0
                v[idx] += sgn
        out.append(_norm_list(v))
    return out


def embed(texts: List[str]) -> List[List[float]]:  # type: ignore
    """Embed texts with pluggable backends.

    Respects env var QJSON_EMBED_MODE:
      - 'hash'          -> use deterministic hashed embeddings (fast, offline)
      - 'transformers'  -> try sentence_transformers, else fall back to hash
      - 'ollama'        -> use Ollama only; on error fall back to hash
      - unset/other     -> try Ollama, then transformers, then hash
    """
    mode = os.environ.get("QJSON_EMBED_MODE", "").strip().lower()
    if mode == "hash":
        return _embed_hash(texts)
    if mode == "transformers":
        try:
            return _embed_fallback_transformers(texts)
        except Exception:
            return _embed_hash(texts)
    if mode == "ollama":
        try:
            return _embed_ollama(texts)
        except Exception:
            return _embed_hash(texts)
    # default cascade: ollama -> hash (avoid transformers to prevent network stalls)
    try:
        return _embed_ollama(texts)
    except Exception:
        return _embed_hash(texts)


def add_memory(agent_id: str, text: str, meta: Dict | None = None, ts: Optional[float] = None) -> int:
    """Store one memory with an embedding."""
    con = _ensure_db()
    meta = meta or {}
    ts = ts or time.time()
    v = embed([text])[0]
    blob = _vec_to_bytes(v)
    # Upsert by fingerprint per agent if schema supports it; else insert
    if _has_column(con, 'memories', 'fingerprint') and _has_column(con, 'memories', 'freq'):
        fp = _fingerprint(text)
        cur = con.execute("SELECT id,freq FROM memories WHERE agent_id=? AND fingerprint=? LIMIT 1;", (agent_id, fp))
        row = cur.fetchone()
        if row:
            mid, freq = int(row[0]), int(row[1] or 1)
            con.execute("UPDATE memories SET ts=?, freq=? WHERE id=?;", (ts, freq + 1, mid))
            con.commit()
            return mid
        cur = con.execute(
            "INSERT INTO memories(agent_id, ts, text, meta, vec, fingerprint, freq) VALUES (?,?,?,?,?,?,?)",
            (agent_id, ts, text, json.dumps(meta, ensure_ascii=False), blob, fp, 1),
        )
    else:
        cur = con.execute(
            "INSERT INTO memories(agent_id, ts, text, meta, vec) VALUES (?,?,?,?,?)",
            (agent_id, ts, text, json.dumps(meta, ensure_ascii=False), blob),
        )
    con.commit()
    mid = int(cur.lastrowid)
    try:
        _ivf_add(agent_id, v, mid)
    except Exception:
        pass
    return mid


def add_batch(agent_id: str, items: Iterable[Tuple[str, Dict | None, Optional[float]]]) -> None:
    """Insert many memories: iterable of (text, meta, ts)."""
    items_list = list(items)
    if not items_list:
        return
    con = _ensure_db()
    texts = [t for (t, _m, _ts) in items_list]
    vecs = embed(texts)
    rows = []
    now = time.time()
    for (t, m, ts), v in zip(items_list, vecs):
        if _has_column(con, 'memories', 'fingerprint') and _has_column(con, 'memories', 'freq'):
            fp = _fingerprint(t)
            row = con.execute("SELECT id,freq FROM memories WHERE agent_id=? AND fingerprint=? LIMIT 1;", (agent_id, fp)).fetchone()
            if row:
                mid, freq = int(row[0]), int(row[1] or 1)
                con.execute("UPDATE memories SET ts=?, freq=? WHERE id=?;", (ts or now, freq + 1, mid))
            else:
                con.execute(
                    "INSERT INTO memories(agent_id, ts, text, meta, vec, fingerprint, freq) VALUES (?,?,?,?,?,?,?)",
                    (agent_id, ts or now, t, json.dumps(m or {}, ensure_ascii=False), _vec_to_bytes(v), fp, 1),
                )
        else:
            con.execute(
                "INSERT INTO memories(agent_id, ts, text, meta, vec) VALUES (?,?,?,?,?)",
                (agent_id, ts or now, t, json.dumps(m or {}, ensure_ascii=False), _vec_to_bytes(v)),
            )
    con.commit()


def _fetch_agent_mem(con, agent_id: str) -> Tuple[List[List[float]], List[Tuple[int, float, str, str]]]:
    rows = list(con.execute("SELECT id, ts, text, meta, vec FROM memories WHERE agent_id=?;", (agent_id,)))
    if not rows:
        return [], []
    vecs: List[List[float]] = []
    meta: List[Tuple[int, float, str, str]] = []
    for r in rows:
        vecs.append(_bytes_to_vec(r[4]))
        meta.append((int(r[0]), float(r[1]), str(r[2]), str(r[3])))
    return vecs, meta


def _fetch_recent_mem(con, agent_id: str, limit: int) -> Tuple[List[List[float]], List[Tuple[int, float, str, str]]]:
    rows = list(con.execute("SELECT id, ts, text, meta, vec FROM memories WHERE agent_id=? ORDER BY ts DESC LIMIT ?;", (agent_id, int(limit))))
    if not rows:
        return [], []
    vecs: List[List[float]] = []
    meta: List[Tuple[int, float, str, str]] = []
    for r in rows:
        vecs.append(_bytes_to_vec(r[4]))
        meta.append((int(r[0]), float(r[1]), str(r[2]), str(r[3])))
    return vecs, meta


# ---------- IVF (FAISS-like) index stored in FMM ----------

def _ivf_meta_path(dim: int, k: int) -> List[str]:
    return ["retrieval", "ivf", f"dim{dim}", f"K{k}"]


def _ivf_read(agent_id: str) -> Optional[Dict[str, Any]]:
    """Return the best available IVF index for an agent (highest K), if any."""
    try:
        fmm = PersistentFractalMemory(agent_id)
        tree = fmm.tree
        node = tree.get("retrieval", {}).get("ivf", {})
        if not isinstance(node, dict):
            return None
        # Pick highest K under any dim
        best: Optional[Tuple[int, int, Dict[str, Any]]] = None  # (dim, K, obj)
        for dim_key, sub in node.items():
            if not isinstance(sub, dict):
                continue
            for kkey, obj in sub.items():
                if not isinstance(obj, dict):
                    continue
                if not isinstance(obj.get("centroids"), list):
                    continue
                try:
                    dim = int(str(dim_key).replace("dim", ""))
                    K = int(str(kkey).replace("K", ""))
                except Exception:
                    continue
                if (best is None) or (K > best[1]):
                    best = (dim, K, obj)
        if best is None:
            return None
        return {"dim": best[0], "K": best[1], **best[2]}
    except Exception:
        return None


def _ivf_write(agent_id: str, *, dim: int, K: int, centroids: List[List[float]], buckets: Dict[int, List[int]], ts: float, count: int) -> None:
    fmm = PersistentFractalMemory(agent_id)
    node = fmm.tree
    cur = node.setdefault("retrieval", {}).setdefault("ivf", {}).setdefault(f"dim{dim}", {})
    cur[f"K{K}"] = {
        "ts": ts,
        "dim": dim,
        "K": K,
        "count": count,
        "centroids": centroids,
        "buckets": {str(k): v for k, v in buckets.items()},
    }
    fmm.persist()


def _l2(a: List[float], b: List[float]) -> float:
    return sum((x - y) * (x - y) for x, y in zip(a, b))


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _kmeans(V: List[List[float]], K: int, iters: int = 3) -> List[List[float]]:
    import random as _rnd
    if not V:
        return []
    n = len(V)
    dim = len(V[0])
    K = min(K, n)
    # KMeans++ init (light)
    C: List[List[float]] = [V[_rnd.randrange(n)][:]]
    while len(C) < K:
        # distance to nearest centroid
        d2 = []
        for v in V:
            m = min(_l2(v, c) for c in C)
            d2.append(m)
        s = sum(d2) or 1.0
        r = _rnd.random() * s
        acc = 0.0
        idx = 0
        for i, dv in enumerate(d2):
            acc += dv
            if acc >= r:
                idx = i
                break
        C.append(V[idx][:])
    # Lloyd iterations
    for _ in range(max(1, iters)):
        assign = [[] for _ in range(K)]
        for i, v in enumerate(V):
            j = max(range(K), key=lambda j: _dot(v, C[j]))
            assign[j].append(i)
        for j in range(K):
            if not assign[j]:
                continue
            # compute mean
            cen = [0.0] * dim
            for i in assign[j]:
                vv = V[i]
                for d in range(dim):
                    cen[d] += vv[d]
            C[j] = _norm_list([x / max(1, len(assign[j])) for x in cen])
    return C


def _ivf_build(agent_id: str, con: sqlite3.Connection, *, K: int = 64, iters: int = 3) -> None:
    V, meta = _fetch_agent_mem(con, agent_id)
    if not V:
        return
    dim = len(V[0])
    # Align all to common dim
    V = [_align_dim(v, dim) for v in V]
    C = _kmeans(V, K=K, iters=iters)
    # Assign to buckets by max dot (cosine, vectors normalized)
    buckets: Dict[int, List[int]] = {j: [] for j in range(len(C))}
    for i, v in enumerate(V):
        j = max(range(len(C)), key=lambda j: _dot(v, C[j]))
        # store DB id for this vector
        buckets[j].append(int(meta[i][0]))
    _ivf_write(agent_id, dim=dim, K=len(C), centroids=C, buckets=buckets, ts=time.time(), count=len(V))


def _ivf_add(agent_id: str, vec: List[float], mem_id: int) -> None:
    """Append a newly inserted vector to the nearest IVF bucket if index exists."""
    idx = _ivf_read(agent_id)
    if not idx:
        return
    dim = int(idx.get("dim") or len(vec))
    v = _align_dim(vec, dim)
    C = [[float(x) for x in c] for c in (idx.get("centroids") or [])]
    if not C:
        return
    j = max(range(len(C)), key=lambda j: _dot(v, C[j]))
    # Update the FMM buckets in-place
    fmm = PersistentFractalMemory(agent_id)
    try:
        node = fmm.tree.setdefault("retrieval", {}).setdefault("ivf", {}).setdefault(f"dim{dim}", {})
        # Find K key — assume only one set under this dim in practice
        # If multiple Ks exist, update the largest one (best quality)
        target_k = None
        if isinstance(node, dict):
            best_k = -1
            for kkey, obj in node.items():
                try:
                    kval = int(str(kkey).replace('K',''))
                except Exception:
                    continue
                if isinstance(obj, dict) and kval > best_k:
                    best_k = kval
                    target_k = kkey
        if target_k is None:
            return
        obj = node.get(target_k)
        if not isinstance(obj, dict):
            return
        buckets = obj.setdefault('buckets', {})
        key = str(j)
        lst = buckets.get(key)
        if not isinstance(lst, list):
            buckets[key] = [int(mem_id)]
        else:
            lst.append(int(mem_id))
        obj['count'] = int(obj.get('count') or 0) + 1
        fmm.persist()
    except Exception:
        pass


def _ivf_maybe_autorebuild(agent_id: str, con: sqlite3.Connection) -> None:
    """Rebuild IVF when threshold is crossed or missing index.

    Env vars:
      - QJSON_RETR_USE_FMM=1 to enable (default on)
      - QJSON_RETR_IVF_K (default 64)
      - QJSON_RETR_REINDEX_THRESHOLD (default 512)
    """
    if os.environ.get("QJSON_RETR_USE_FMM", "1") != "1":
        return
    V, _ = _fetch_agent_mem(con, agent_id)
    n = len(V)
    if n == 0:
        return
    K = int(os.environ.get("QJSON_RETR_IVF_K", "64"))
    thr = int(os.environ.get("QJSON_RETR_REINDEX_THRESHOLD", "512"))
    idx = _ivf_read(agent_id)
    if idx is None or int(idx.get("count") or 0) < n // 2 and n >= thr:
        _ivf_build(agent_id, con, K=K)


def search_memory(
    agent_id: str,
    query: str,
    top_k: int = TOP_K_DEFAULT,
    time_decay: float = 0.0,  # e.g., 0.01 for soft recency boost
    hybrid: str = "none",     # 'none' or 'tfidf'
    tfidf_weight: float = 0.3,
    fresh_boost: float = 0.0,  # alpha for sigmoid freshness (recent > old)
) -> List[Dict]:
    """Vector search with cosine similarity.

    Uses an IVF-like index stored in FMM if available and enabled via
    QJSON_RETR_USE_FMM=1 (default). Falls back to full scan otherwise.
    """
    con = _ensure_db()
    # Embed query first
    q_raw = embed([query])[0]
    use_ivf = os.environ.get("QJSON_RETR_USE_FMM", "1") == "1"
    idx = _ivf_read(agent_id) if use_ivf else None
    if idx and isinstance(idx.get("centroids"), list) and isinstance(idx.get("buckets"), dict):
        dim = int(idx.get("dim") or len(q_raw))
        q = _align_dim(q_raw, dim)
        C = [[float(x) for x in c] for c in idx["centroids"]]
        # Select top-nprobe buckets
        nprobe = max(1, int(os.environ.get("QJSON_RETR_IVF_NPROBE", "4")))
        order = sorted(range(len(C)), key=lambda j: _dot(q, C[j]), reverse=True)[:nprobe]
        # Gather candidate DB ids
        cand_ids: List[int] = []
        buckets = idx.get("buckets") or {}
        for j in order:
            lst = buckets.get(str(j)) or []
            cand_ids.extend(int(x) for x in lst)
        # Fetch candidates
        if cand_ids:
            # Build placeholders for SQL IN clause safe usage
            ph = ",".join(["?"] * len(cand_ids))
            rows = list(con.execute(f"SELECT id, ts, text, meta, vec FROM memories WHERE agent_id=? AND id IN ({ph});", (agent_id, *cand_ids)))
            if rows:
                V: List[List[float]] = []
                meta: List[Tuple[int, float, str, str]] = []
                for r in rows:
                    v = _bytes_to_vec(r[4])
                    V.append(_align_dim(v, dim))
                    meta.append((int(r[0]), float(r[1]), str(r[2]), str(r[3])))
                sims = [_dot(v, q) for v in V]
            else:
                V, meta = _fetch_agent_mem(con, agent_id)
                if not V:
                    return []
                dim = len(V[0])
                V = [_align_dim(v, dim) for v in V]
                q = _align_dim(q_raw, dim)
                sims = [_dot(v, q) for v in V]
        else:
            V, meta = _fetch_agent_mem(con, agent_id)
            if not V:
                return []
            dim = len(V[0])
            V = [_align_dim(v, dim) for v in V]
            q = _align_dim(q_raw, dim)
            sims = [_dot(v, q) for v in V]
    else:
        # Fallback: if collection is very large and no IVF present, limit to recent subset
        # Fallback: if collection is very large and no IVF present, limit to recent subset without loading all
        V, meta = _fetch_agent_mem(con, agent_id)
        if not V:
            return []
        dim = len(V[0]) if V else len(q_raw)
        V = [_align_dim(v, dim) for v in V]
        q = _align_dim(q_raw, dim)
        sims = [_dot(v, q) for v in V]
    # Optional hybrid TF-IDF re-rank
    if hybrid == "tfidf":
        # Tokenize
        def toks(s: str) -> List[str]:
            return [w for w in _normalize_text(s).split() if w]
        qtok = toks(query)
        # Build DF across corpus
        docs = [m[2] for m in meta]
        doc_toks = [toks(d) for d in docs]
        df: Dict[str, int] = {}
        for dt in doc_toks:
            seen = set(dt)
            for t in seen:
                df[t] = df.get(t, 0) + 1
        N = max(1, len(docs))
        idf: Dict[str, float] = {t: _math.log((N + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}
        # Query weights
        q_tf: Dict[str, int] = {}
        for t in qtok:
            q_tf[t] = q_tf.get(t, 0) + 1
        q_w = {t: (q_tf[t] * idf.get(t, 0.0)) for t in q_tf}
        # Doc scores
        tfidf_scores: List[float] = []
        for dt in doc_toks:
            tf: Dict[str, int] = {}
            for t in dt:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for t, wq in q_w.items():
                if t in tf:
                    s += wq * (tf[t] * idf.get(t, 0.0))
            tfidf_scores.append(s)
        sims = [float(s) + float(tfidf_weight) * float(ti) for s, ti in zip(sims, tfidf_scores)]
    if time_decay > 0:
        now = time.time()
        ages_days = [(now - m[1]) / 86400.0 for m in meta]
        sims = [s * _math.exp(-time_decay * age) for s, age in zip(sims, ages_days)]
    if fresh_boost > 0.0:
        now = time.time()
        ages_hours = [(now - m[1]) / 3600.0 for m in meta]
        # recent => large boost via sigmoid( -age )
        boosts = [1.0 / (1.0 + _math.exp(age - 1.0)) for age in ages_hours]
        sims = [s + (fresh_boost * b) for s, b in zip(sims, boosts)]
    # top-k
    idx = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[: top_k]
    out: List[Dict] = []
    for ii in idx:
        mid, ts, text, mjson = meta[ii]
        out.append({
            "id": mid,
            "ts": ts,
            "text": text,
            "meta": json.loads(mjson),
            "score": float(sims[ii]),
        })
    return out


def inject_for_prompt(
    agent_id: str,
    query: str,
    top_k: int = TOP_K_DEFAULT,
    time_decay: float = 0.0,
    min_score: float = 0.25,
    hybrid: str = "none",
    tfidf_weight: float = 0.3,
    fresh_boost: float = 0.0,
    header: str = "### Retrieved long-term memory",
) -> str:
    hits = search_memory(
        agent_id,
        query,
        top_k=top_k,
        time_decay=time_decay,
        hybrid=hybrid,
        tfidf_weight=tfidf_weight,
        fresh_boost=fresh_boost,
    )
    hits = [h for h in hits if float(h.get("score", 0.0)) >= float(min_score)]
    if not hits:
        return ""
    blocks = [f"- ({h['score']:.2f}) {h['text']}" for h in hits]
    return f"{header}:\n" + "\n".join(blocks) + "\n"
def _count_agent_mem(con, agent_id: str) -> int:
    try:
        cur = con.execute("SELECT COUNT(1) FROM memories WHERE agent_id=?;", (agent_id,))
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0
