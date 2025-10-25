QJSON Agents — TODO

- Ingestion
  - [ ] Chunk very large files on /inject[_py]/_mem into N-sized blocks with metadata (chunk i/N)
  - [ ] Optional gzip compression for stored content (flag/setting)
  - [ ] Code-aware /inject_py summary (list classes/defs, call graphs)

- Chat UX
  - [ ] /include_cap N is session-persistent; add per-agent defaults in manifest runtime
  - [ ] /settings export/import presets
  - [ ] /preflight without args previews last typed line (line buffer)

- Performance
  - [ ] Add model throughput sampling (measure TPS from recent runs) to improve /preflight estimate
  - [ ] Optional streaming by default with a quiet mode

- Swarm
  - [ ] Better fairness router v2; track cumulative selection and entropy over runs
  - [ ] Integrate JSON Schema validation for YSON/YSONX

- Security & Safety
  - [ ] Sandboxed execution for YSON logic (separate process, restricted env)
  - [ ] Add hash and origin metadata to ingested files for traceability

- Plugins
  - [ ] File System plugin: /fs_list, /fs_read, /fs_write (write gated by QJSON_FS_WRITE=1; restrict to QJSON_FS_ROOTS)
  - [ ] Code Execution plugin: /py (Python exec) gated by QJSON_ALLOW_EXEC=1 with timeout caps
  - [ ] Database plugin (SQLite): /sql_open, /sql_query, /sql_tables, /sql_close; cap rows and require ro=1 by default
  - [ ] Git plugin: /git_status, /git_log, /git_diff; write ops gated by QJSON_GIT_WRITE=1
  - [ ] Generic API plugin: /api_get, /api_post; gated by QJSON_ALLOW_NET=1 and timeouts
