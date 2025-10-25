FAQ / Troubleshooting

403 or empty page?
- Try increasing `QJSON_WEBOPEN_TIMEOUT` (e.g., 10–12s).
- Some sites block default User-Agents; a custom UA is not exposed yet in CLI, but you can tune crawl rate and rely on cached results.
- Check robots.txt; if blocked, the crawler will skip.
- Some pages require JS; this stack uses static HTML fetch only.

Why duplicates in the index?
- We normalize URLs and strip fragments, but canonicalization varies by site.
- The crawler also deduplicates by SHA‑1 of section text. If you see near‑dups, it’s likely different URLs with similar content.
- Roadmap includes `<link rel="canonical">` and `Last-Modified` handling for incremental refresh.

How do I make answers more focused?
- Lower `QJSON_WEB_TOPK` (e.g., 3) and keep injected page caps modest.
- Enable retrieval with small top‑k and modest time‑decay for agent memory.
- Add the “truth” note: `/truth on` (the agent will acknowledge local memory/web).

Why does /open truncate content?
- Controlled by `QJSON_WEBOPEN_MAX_BYTES` (read cap) and `QJSON_WEBOPEN_CAP` (injected chars cap).
- Increase carefully; large pages will bloat prompts and slow inference.

How to do air‑gapped?
- Disable local fallback scanning for unified search by leaving `QJSON_LOCAL_SEARCH_ROOTS` unset or setting engine mode to `local` explicitly.
- Keep interactions to local retrieval and local files via `/inject`.
