
# QJSON Agents: A Local-First, Composable, and Inspectable Agent Runtime

## Abstract

The proliferation of large language models (LLMs) has led to a surge in the development of AI-powered agents. However, the majority of these agents rely on centralized, proprietary services, raising concerns about privacy, control, and extensibility. The QJSON Agents project presents a novel, local-first agent runtime that empowers users to build, manage, and deploy autonomous agents on their own machines. The runtime is designed to be predictable, inspectable, and extensible, providing a transparent and customizable alternative to closed-source AI systems. Key features include a multi-layered memory system with retrieval-augmented generation (RAG), a flexible persona management system using the custom YSON configuration format, and support for multi-agent collaboration through swarms and clusters. This whitepaper provides a comprehensive overview of the QJSON Agents project, detailing its architecture, core concepts, key features, and implementation.

## 1. Introduction

The recent advancements in large language models have opened up new frontiers in human-computer interaction. AI-powered agents are becoming increasingly capable of performing complex tasks, from answering questions and generating creative text to controlling software and interacting with the digital world. However, the current landscape of AI agents is dominated by centralized services, which often operate as black boxes, giving users little control over their data and the agents' behavior.

The QJSON Agents project was born out of a desire to create a more open, transparent, and user-centric approach to building and deploying AI agents. We believe that users should have the freedom to run their own agents on their own hardware, with full control over their data and the agents' functionality. To this end, we have developed a local-first agent runtime that is:

*   **Predictable:** The agent's behavior is determined by its manifest and its memory, which are both stored locally and can be inspected and modified by the user.
*   **Inspectable:** The agent's memory and event logs are stored in human-readable formats (JSONL and JSON), making it easy to audit the agent's actions and understand its reasoning.
*   **Extensible:** The agent's functionality can be extended with custom Python logic, allowing users to create highly specialized agents for their specific needs.
*   **Composable:** The project supports multi-agent systems, allowing users to create swarms of agents that can collaborate to solve complex problems.

This whitepaper provides a detailed overview of the QJSON Agents project, from its high-level architecture to its low-level implementation details. We hope that this document will serve as a valuable resource for developers, researchers, and anyone interested in the future of decentralized AI.

## 2. Architecture

The QJSON Agents runtime is built on a layered architecture that separates concerns and promotes modularity. The main layers are:

*   **Persona Layer:** This layer is responsible for defining the agent's identity, roles, goals, and runtime parameters. Personas are defined in JSON or YSON manifests, which are human-readable and easy to customize.
*   **Agent Layer:** This layer contains the core `Agent` class, which wraps a persona manifest and provides the main interface for interacting with the agent. The agent layer is responsible for building prompts, managing the agent's memory, and interacting with the Ollama LLM.
*   **State Layer:** This layer is responsible for persisting the agent's state, including its memory, event logs, and fractal memory tree. The state is stored in a combination of JSONL files, JSON files, and a SQLite database.
*   **Orchestration Layer:** This layer provides the user interface for interacting with the agents, including a command-line interface (CLI) and a text-based menu. The orchestration layer is also responsible for managing multi-agent clusters and swarms.
*   **Retrieval Layer:** This optional layer provides the agent with a long-term memory system based on retrieval-augmented generation (RAG). The retrieval layer uses a SQLite database to store vector embeddings of the agent's memories and a FAISS-like IVF index to accelerate search.

The data flow in the system is designed to be transparent and auditable. When a user interacts with an agent, the input is processed by the agent layer, which assembles a context from the agent's system prompt, its recent memory, and an optional retrieval block. The context is then sent to the Ollama LLM, which generates a response. The user's input and the agent's response are then logged to the agent's memory, and the agent's fractal memory and cluster index are updated accordingly.

## 3. Core Concepts

### 3.1. Agents and Personas

An **agent** in the QJSON Agents system is an autonomous entity with a unique identity, a set of roles and directives, and the ability to interact with the world through a large language model. Each agent is defined by a **persona manifest**, which is a JSON or YSON file that specifies the agent's properties.

The persona manifest includes the following key fields:

*   `agent_id`: A unique identifier for the agent.
*   `origin` and `creator`: Information about the agent's provenance.
*   `roles`: A list of roles that the agent can assume.
*   `core_directives`: A set of high-level instructions that guide the agent's behavior.
*   `features`: A set of flags that enable or disable certain features, such as recursive memory and fractal state.
*   `runtime`: Configuration for the Ollama LLM, such as the model to use and the temperature for generation.

Personas can be swapped and evolved over time. The system provides a mechanism for forking an agent to create a new agent with a modified persona, as well as a mechanism for mutating an agent's persona in place.

### 3.2. Memory

The QJSON Agents system features a sophisticated, multi-layered memory system that allows agents to learn and remember over time. The memory system consists of:

*   **Short-term Memory:** The agent's recent conversational history is stored in an append-only `memory.jsonl` file. This file contains a log of all user inputs and agent responses, as well as system messages.
*   **Event Log:** The agent's operational events, such as forks, swaps, and ingestions, are stored in an append-only `events.jsonl` file.
*   **Fractal Memory (FMM):** The FMM is a hierarchical, tree-like data structure that allows for the storage of structured data. The FMM is persisted in a `fmm.json` file and is used to store aggregated information and metadata about the agent's memories.
*   **Retrieval Store:** The retrieval store is a long-term memory system that uses a SQLite database to store vector embeddings of the agent's memories. This allows the agent to retrieve relevant information from its past experiences to inform its current actions.

### 3.3. Swarms and Clusters

The QJSON Agents project provides built-in support for multi-agent systems, allowing users to create **swarms** or **clusters** of agents that can collaborate to solve complex problems. The system supports several communication topologies:

*   **Ring:** A deterministic, round-robin topology where a "baton" is passed from one agent to the next.
*   **Mesh:** A broadcast topology where the baton is sent to all agents in the swarm simultaneously.
*   **Mixture of Experts (MoE):** A more advanced topology where a router selects the most relevant agents (experts) for a given task based on a TF-IDF overlap score.

The swarm functionality is designed to be flexible and extensible, allowing users to experiment with different multi-agent architectures and collaboration patterns.

## 4. Key Features

### 4.1. Retrieval-Augmented Generation (RAG)

The RAG system is one of the key features of the QJSON Agents project. It provides agents with a long-term memory that they can use to inform their responses. The RAG system consists of the following components:

*   **Embedding:** The system uses Ollama to generate vector embeddings of the agent's memories. It also has fallbacks to sentence-transformers or a deterministic hashing function if Ollama is unavailable.
*   **Storage:** The vector embeddings are stored in a SQLite database, along with the original text of the memory and its metadata.
*   **Search:** The system uses cosine similarity to find the most relevant memories for a given query. It also supports time decay to give more weight to recent memories.
*   **Hybrid Search:** An optional TF-IDF re-ranking mechanism can be used to improve the relevance of the search results.
*   **IVF Index:** A FAISS-like Inverted File (IVF) index is used to accelerate the search process. The IVF index is stored in the agent's Fractal Memory and is automatically updated when new memories are added.

### 4.2. YSON and YSON-X

YSON is a custom configuration format that is designed to be more human-readable and flexible than JSON. YSON combines features of YAML and JSON, and it also supports comments and optional Python logic blocks. YSON-X is an extended version of YSON that provides more advanced features for defining agent personas and swarm architectures.

### 4.3. Command-Line Interface (CLI) and Menu

The project provides a rich user interface for interacting with the agents and managing the system. The CLI provides a wide range of commands for initializing, chatting with, and managing agents. The interactive text-based menu provides a more user-friendly way to access the most common features of the system.

## 5. Implementation Details

### 5.1. Technologies

The QJSON Agents project is implemented in Python 3 and relies on a small number of external libraries. The core technologies used in the project are:

*   **Python 3:** The primary programming language.
*   **SQLite:** For the persistent vector store in the retrieval system.
*   **Ollama:** For running local large language models.
*   **NumPy (optional):** For numerical operations.
*   **PyYAML (optional):** For parsing YSON files.
*   **Sentence-Transformers (optional):** As a fallback for generating embeddings.

### 5.2. Data Structures and Algorithms

The project implements several custom data structures and algorithms, including:

*   **Fractal Memory Tree (FMM):** A hierarchical data structure for storing structured data.
*   **IVF Index:** A FAISS-like Inverted File (IVF) index for accelerating vector search.
*   **Hybrid Search:** A search algorithm that combines cosine similarity with TF-IDF re-ranking.

## 6. Use Cases and Applications

The QJSON Agents project can be used for a wide range of applications, including:

*   **Personal Assistants:** Create a personalized AI assistant that runs on your own machine and has access to your local files and data.
*   **Research Tools:** Use a swarm of agents to perform research on a specific topic, with each agent specializing in a different aspect of the research.
*   **Creative Writing Companions:** Use an agent to help you with creative writing tasks, such as generating ideas, writing dialogue, and developing characters.
*   **Software Development:** Use agents to help with software development tasks, such as writing code, generating documentation, and running tests.

## 7. Future Work

The QJSON Agents project is under active development, and we have many plans for the future. Some of the features we are considering are:

*   **Support for more LLMs:** We plan to add support for other local and remote LLMs, in addition to Ollama.
*   **Improved Swarm Intelligence:** We plan to improve the swarm intelligence by adding more sophisticated routing and collaboration mechanisms.
*   **Graphical User Interface (GUI):** We plan to develop a GUI for the project to make it more accessible to non-technical users.
*   **Plugin System:** We plan to add a plugin system to make it easier to extend the functionality of the agents.

## 8. Conclusion

The QJSON Agents project provides a powerful and flexible platform for building, managing, and deploying local-first AI agents. By giving users full control over their agents and their data, we hope to foster a more open, transparent, and user-centric AI ecosystem. We believe that the QJSON Agents project has the potential to democratize AI and empower users to create their own intelligent assistants.

## 6. Plugin System (Slash-Command Extensions)

### 6.1 Design Goals
- Extend agent capabilities without forking the core runtime.
- Keep plugins simple: pure‑Python modules shipped in‑tree, no heavy deps.
- Unify UX: plugins register slash commands usable in `chat` and `exec`.

### 6.2 Loader and Lifecycle
- Discovery: `qjson_agents.plugin_manager.load_plugins()` scans `qjson_agents/plugins/` via `pkgutil.iter_modules`, imports modules, and instantiates subclasses of `Plugin`.
- Base class: `Plugin` exposes `get_commands() -> Dict[str, Callable]` returning a map of `"/command"` → callable.
- Tool injection: the CLI injects a small `tools` dict when constructing plugins (e.g., a `google_web_search` wrapper if provided by the host), allowing optional host integration without hard dependencies.
- Dispatch: in `chat` and `exec`, the CLI merges `get_commands()` maps from all loaded plugins into `plugin_commands`; if a user input’s first token matches, the callable executes. Plugin commands appear automatically in `/help`.

### 6.3 Environment Contracts (Inter‑Plugin Interop)
- Active agent: `QJSON_AGENT_ID` is set by the CLI; plugins should index into this agent by default.
- Results cache: set `QJSON_WEBSEARCH_RESULTS_ONCE` (JSON array of results) and `QJSON_WEBRESULTS_CACHE` (sticky copy) so `/open N` works across plugins and core.
- Headers: `QJSON_WEBSEARCH_HEADER` for results and `QJSON_WEBOPEN_HEADER` for page content banners.
- Page open policy: `QJSON_WEBOPEN_DEFAULT=text|raw` and one‑shot override `QJSON_WEBOPEN_MODE_ONCE`.

### 6.4 Built‑in Plugins
- Confluence Importer — `qjson_agents/plugins/confluence_importer.py`
  - Command: `/confluence_import <PATH>` (file or directory, recursive).
  - HTML: parsed to a DocOutline via `web_outliner.build_outline(html, url)`.
  - `.md`/`.txt`: wrapped into a single‑section outline.
  - Indexing: `web_indexer.upsert_outline(agent_id, outline)` chunks, indexes into retrieval, and persists to Fractal Memory (fmm.json).
  - Output: summary string `imported=N skipped=M -> <AGENT_ID>`.

- SharePoint Importer — `qjson_agents/plugins/sharepoint_importer.py`
  - Command: `/sharepoint_import <PATH>` (same behavior as Confluence importer).
  - Handles HTML, MD, TXT; indexes outlines into the active agent.

- LangSearch Crawler — `qjson_agents/plugins/langsearch_crawler.py`
  - Command: `/crawl <QUERY | URL... [depth=N] [pages=M] [export=DIR]>`.
  - Modes:
    - BFS crawl when URL seeds or `depth=`/`pages=` detected: fetch via `web_crawler.Crawler` with `robots.txt` + rate limiting; index via `upsert_outline`; optional per‑page JSON export.
    - Web search when only a query: use LangSearch API (when `LANGSEARCH_API_KEY` is set), fallback to `googlesearch-python` else none. Arms one‑shot results for `/open`.
  - Interop: populates `QJSON_WEBSEARCH_RESULTS_ONCE` and `QJSON_WEBRESULTS_CACHE` with normalized results and sets a header `QJSON_WEBSEARCH_HEADER`.

### 6.5 DocOutline Format (summarized)
- Produced by `web_outliner.build_outline(html, url)` or by importers for text files.
- Keys: `url`, `title`, `subtitle?`, `sections[]` (level, title, text, anchors, figures), `dates[]` (published/updated), `lang`.
- Indexer (`web_indexer.upsert_outline`) chunks section text (1000 chars, 150 overlap), writes to retrieval and under a structured fmm path `web/<host>/<YYYY>/<title>/<secN-hL>` with timestamps and hashes.

## 7. Unified Web & Local Search (+ Crawl, Open, Index)

### 7.1 User‑Facing Commands
- `/engine mode=online|local` — sets default search mode; persisted in `state/env.json` as `QJSON_ENGINE_DEFAULT`.
- `/find <QUERY or URL...> [mode=online|local depth=N pages=M export=DIR]` — unified entry: online web search, local filesystem search, or BFS crawl if URL seeds are present.
- `/open N [ingest] [raw|text]` — fetch the Nth cached result, inject content for the next turn; optional `ingest` indexes content.

### 7.2 Execution Model
- Persistent preferences: the CLI stores small env overrides in `state/env.json` (e.g., engine mode, last results cache/header) with `_save_persistent_env`/`_load_persistent_env`.
- One‑shot/sticky cache:
  - After `/find` or plugin search, results are placed in `QJSON_WEBSEARCH_RESULTS_ONCE` (consumed once) and mirrored to `QJSON_WEBRESULTS_CACHE` (sticky) so `/open` works across sessions.
  - `/open` sets `QJSON_WEBOPEN_TEXT_ONCE` with the fetched/outlined page text.

### 7.3 Online Search Flow
- Primary path: LangSearch API when `LANGSEARCH_API_KEY` is set, requesting `count=topk`, extracting `title/url/snippet/summary`.
- Fallbacks: host `google_web_search` tool if available; else `googlesearch-python` URLs; final fallback is the local file search.
- Optional fetch+index: if `QJSON_FIND_FETCH=1`, fetches top‑`N` (`QJSON_FIND_FETCH_TOP_N`) results via `Crawler(max_depth=0)`, outlines and indexes into the active agent.

### 7.4 Local Search Flow (Offline)
- Function: `_local_repo_search(query)` scans configured roots for quick filename/path and content matches.
- Configuration:
  - `QJSON_LOCAL_SEARCH_ROOTS` os.pathsep‑separated roots; defaults to `cwd`.
  - Skips common heavy/transient directories: `state, logs, __pycache__, .venv, venv, node_modules, .git`, plus `QJSON_LOCAL_SEARCH_SKIP_DIRS`.
  - `QJSON_LOCAL_SEARCH_MAX_FILES` cap (default 5000).
- Results: up to `QJSON_WEB_TOPK`, each with `title` (relative path), `url` (path), `snippet`.

### 7.5 Crawler Internals (Online BFS)
- Class: `web_crawler.Crawler(rate_per_host=QJSON_CRAWL_RATE)` with per‑host rate limiting and `robots.txt` policy (`urllib.robotparser`).
- BFS frontier of `(url, depth)` pairs up to `max_depth` and `max_pages`.
- Fetch caps: `timeout=6s`, `max_bytes=~512 KB` default; decodes UTF‑8 with ignore fallback.
- Link extraction: simple `href` regex + normalization; restrict via `allowed_domains` when provided by non‑interactive CLI.
- Dedup: SHA1 over concatenated section bodies to avoid reinserting near‑duplicates.
- Output: list of DocOutlines; the CLI and plugins index via `upsert_outline` and optionally write per‑page JSON with safe slugs.

### 7.6 Outliner: HTML→DocOutline
- Parser: built on `html.parser` (`web_outliner.py`) with a minimal DOM.
- Title selection: prefers `<h1>`; falls back to `<title>`/OpenGraph; optional subtitle via first `<h2>` or meta description.
- Sections: walks header nodes (h1..h6); collects following text (p/li/pre/code/blockquote/td), skipping nav/footers; stores `level/title/text`.
- Dates: `<time datetime>` or regex for common published/updated patterns.
- Language: default `en` (placeholder for future detection).

### 7.7 Indexer: DocOutline→Fractal Memory + Retrieval
- Chunking: 1000 chars with 150‑char overlap per section; each chunk becomes a memory with metadata (`doc_id`, `chunk_id`, `url`, `title`, `section`, `level`, `published_at`, `updated_at`, `crawl_at`, `lang`, `hash`).
- Retrieval: `retrieval.add_memory(agent_id, text, meta)` embeds and writes to SQLite; IVF index metadata is persisted in `state/<id>/fmm.json` when available.
- Fractal Memory path: `web/<host>/<YYYY>/<title or section>/sec<idx>-h<level>`; the `PersistentFractalMemory` persists structured payloads alongside retrieval.

### 7.8 Open: Fetch, Outline/Text, Inject, Ingest
- `/open N [ingest] [raw|text]` pulls the Nth result from cache, fetches with caps (`QJSON_WEBOPEN_TIMEOUT`, `QJSON_WEBOPEN_MAX_BYTES`, `QJSON_WEBOPEN_CAP`).
- Policy: default `text` (outline extraction) unless `QJSON_WEBOPEN_DEFAULT=raw` or one‑shot `QJSON_WEBOPEN_MODE_ONCE=raw` is set; raw injects HTML as‑is, text injects the cleaned outline after body detection.
- Injection: writes `QJSON_WEBOPEN_TEXT_ONCE` and banner `QJSON_WEBOPEN_HEADER` for the next prompt.
- Ingest: when `ingest` is specified, prefers HTML→outline→`upsert_outline`; otherwise falls back to appending raw text into memory and retrieval.

### 7.9 Retrieval and Ranking Notes
- Storage: SQLite blobs with float32 embeddings (Ollama by default, hash fallback; optional transformers backend).
- Hybrid scoring: cosine similarity plus optional TF‑IDF re‑rank (`QJSON_RETRIEVAL_HYBRID=tfidf`, `QJSON_RETRIEVAL_TFIDF_WEIGHT`), with optional freshness boost (`QJSON_RETRIEVAL_FRESH_BOOST`).
- IVF/FMM: per‑agent FAISS‑like IVF index persisted under `fmm.json` (dim/K/nprobe metadata), rebuilt via the `reindex` command.

### 7.10 Safety and Resource Guards
- Robots & rate limits for crawl; conservative page fetch caps; outline‑first injection to minimize prompt bloat.
- Local search guardrails: directory skips, file cap; web fetch timeouts and size caps are tunable via env.

## 8. Implementation Cross‑References
- Plugin base/loader: `qjson_agents/plugin_manager.py`.
- Plugins: `qjson_agents/plugins/confluence_importer.py`, `.../sharepoint_importer.py`, `.../langsearch_crawler.py`.
- CLI search/open/crawl: `qjson_agents/cli.py` (see `_engine_find`, `_perform_websearch`, `_arm_webopen_from_results`).
- Crawler: `qjson_agents/web_crawler.py`. Outliner: `qjson_agents/web_outliner.py`. Indexer: `qjson_agents/web_indexer.py`. Ranking wrapper: `qjson_agents/web_ranker.py`.

## 9. References

As an AI, I do not have access to external websites or the ability to browse the internet. Therefore, I am unable to provide a list of references. However, the concepts and technologies used in this project are based on well-established research in the fields of artificial intelligence, natural language processing, and information retrieval.
