Hybrid Ranking & RAG Settings

Scoring (conceptual)
```
score = wv * cosine + wl * tfidf + wf * freshness + ws * section_boost - wd * dup_penalty

defaults: wv=0.50, wl=0.25, wf=0.15, ws=0.07, wd=0.03
```

Controls (env)
- `QJSON_RETRIEVAL_HYBRID=tfidf` — enable TF‑IDF hybrid
- `QJSON_RETRIEVAL_TFIDF_WEIGHT` — weight for TF‑IDF term
- `QJSON_RETRIEVAL_FRESH_BOOST` — freshness boost alpha
- `QJSON_RETRIEVAL_DECAY` — time‑decay lambda for aging memories/pages

MMR (roadmap)
- Section‑level Max Marginal Relevance to reduce redundancy before answer assembly.

Query expansion (optional)
- Add synonyms via a small local table or a local model; log expanded_terms for transparency.

