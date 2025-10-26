from __future__ import annotations

import shlex
import sys
from pathlib import Path
import os
import json
from typing import Iterable, List
import time

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def _execute_command(argv: list[str]) -> int:
    """Execute a qjson-agents CLI command and stream output to the console."""
    # Prefer running the module directly to ensure we use the in-repo code
    cmd_str = f"{shlex.quote(sys.executable)} -m qjson_agents.cli {' '.join(shlex.quote(a) for a in argv)}"
    print(f"\n> {cmd_str}\n")
    try:
        # Ensure the command is run from the project root for module resolution
        repo_root = Path(__file__).resolve().parent.parent
        # Use os.system to properly handle interactive stdio for chat
        # Wrap in a subshell to handle cd and exec
        final_cmd = f"cd {shlex.quote(str(repo_root))} && {cmd_str}"
        res = os.system(final_cmd)
        return res
    except KeyboardInterrupt:
        print("Interrupted.")
        return 1


def _ask(prompt: str, required: bool = True, default: str | None = None) -> str:
    while True:
        val = input(f"{prompt}{' ['+default+']' if default else ''}: ").strip()
        if not val and default is not None:
            return default
        if val or not required:
            return val
        print("Please enter a value.")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


_CACHE: dict = {"scan_files": {}, "agent_ids": {}}

_SQLITE_PLUGIN_INSTANCE = None  # keep a stateful DB connection across menu actions

def _choose_agent_id(prompt: str = "Agent ID (optional)") -> str:
    ids = _scan_agent_ids()
    sel = _select_from_list(prompt, ids, allow_empty=True)
    if isinstance(sel, list):
        return sel[0] if sel else ""
    return sel or ""

def _ensure_sqlite_plugin():
    global _SQLITE_PLUGIN_INSTANCE
    if _SQLITE_PLUGIN_INSTANCE is None:
        try:
            from qjson_agents.plugins.db_plugin import SQLitePlugin
            _SQLITE_PLUGIN_INSTANCE = SQLitePlugin()
        except Exception:
            _SQLITE_PLUGIN_INSTANCE = None
    return _SQLITE_PLUGIN_INSTANCE


def _scan_files(globs: Iterable[str], *, limit: int | None = None, sort_mtime: bool = False, ttl: float = 1.0) -> List[Path]:
    root = _repo_root()
    key = (tuple(globs), limit, sort_mtime)
    now = time.time()
    cached = _CACHE["scan_files"].get(key)
    if cached and (now - cached[0]) <= ttl:
        return cached[1]
    out: List[Path] = []
    for g in globs:
        out.extend([p for p in root.glob(g) if p.is_file()])
    # Deduplicate
    seen = set()
    uniq: List[Path] = []
    for p in out:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    if sort_mtime:
        try:
            uniq.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            pass
    if isinstance(limit, int) and limit > 0:
        uniq = uniq[:limit]
    _CACHE["scan_files"][key] = (now, uniq)
    return uniq


# Simple menu preferences persisted under state/
def _prefs_path() -> Path:
    return _repo_root() / "state" / "menu_prefs.json"


def _load_prefs() -> dict:
    p = _prefs_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_prefs(prefs: dict) -> None:
    p = _prefs_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---- Retrieval helpers (env + prefs) ----
def _get_retrieval_prefs(prefs: dict) -> tuple[bool, int, float, float, bool, int, bool]:
    enabled = bool(prefs.get("retrieval_enabled", False))
    try:
        topk = int(prefs.get("retrieval_top_k", 6))
    except Exception:
        topk = 6
    try:
        decay = float(prefs.get("retrieval_decay", 0.0))
    except Exception:
        decay = 0.0
    try:
        minscore = float(prefs.get("retrieval_minscore", 0.25))
    except Exception:
        minscore = 0.25
    ingest = bool(prefs.get("retrieval_ingest", False))
    try:
        cap = int(prefs.get("retrieval_ingest_cap", 2000))
    except Exception:
        cap = 2000
    note = bool(prefs.get("retrieval_note", True))
    return enabled, topk, decay, minscore, ingest, cap, note


def _apply_retrieval_env_from_prefs(prefs: dict) -> None:
    enabled, topk, decay, minscore, ingest, cap, note = _get_retrieval_prefs(prefs)
    # IVF/FMM prefs with defaults
    fmm_enabled = bool(prefs.get("retrieval_fmm_enabled", True))
    ivf_k = int(prefs.get("retrieval_ivf_k", 64))
    ivf_nprobe = int(prefs.get("retrieval_ivf_nprobe", 4))
    ivf_thresh = int(prefs.get("retrieval_ivf_reindex_threshold", 512))
    try:
        if enabled:
            os.environ["QJSON_RETRIEVAL"] = "1"
            os.environ["QJSON_RETRIEVAL_TOPK"] = str(max(1, int(topk)))
            os.environ["QJSON_RETRIEVAL_DECAY"] = str(float(decay))
            os.environ["QJSON_RETRIEVAL_MINSCORE"] = str(float(minscore))
        else:
            os.environ.pop("QJSON_RETRIEVAL", None)
            os.environ.pop("QJSON_RETRIEVAL_TOPK", None)
            os.environ.pop("QJSON_RETRIEVAL_DECAY", None)
            os.environ.pop("QJSON_RETRIEVAL_MINSCORE", None)
        if note:
            os.environ["QJSON_RETRIEVAL_NOTE"] = "1"
        else:
            os.environ.pop("QJSON_RETRIEVAL_NOTE", None)
        if ingest:
            os.environ["QJSON_RETRIEVAL_INGEST"] = "1"
            os.environ["QJSON_RETRIEVAL_INGEST_CAP"] = str(max(128, int(cap)))
        else:
            os.environ.pop("QJSON_RETRIEVAL_INGEST", None)
            os.environ.pop("QJSON_RETRIEVAL_INGEST_CAP", None)
        # IVF/FMM envs
        os.environ["QJSON_RETR_USE_FMM"] = "1" if fmm_enabled else "0"
        os.environ["QJSON_RETR_IVF_K"] = str(max(2, int(ivf_k)))
        os.environ["QJSON_RETR_IVF_NPROBE"] = str(max(1, int(ivf_nprobe)))
        os.environ["QJSON_RETR_REINDEX_THRESHOLD"] = str(max(1, int(ivf_thresh)))
    except Exception:
        pass


def _apply_general_env_from_prefs(prefs: dict) -> None:
    """Apply general (non-web, non-retrieval) preferences to environment."""
    try:
        show_ctx = prefs.get("show_context", True)
        os.environ["QJSON_SHOW_CONTEXT"] = "1" if show_ctx else "0"
    except Exception:
        pass

# ---- Web & Crawl prefs ----
def _apply_web_env_from_prefs(prefs: dict) -> None:
    try:
        wt = int(prefs.get("web_topk", 5))
        os.environ["QJSON_WEB_TOPK"] = str(max(1, wt))
    except Exception:
        pass
    try:
        to = float(prefs.get("webopen_timeout", 6.0))
        os.environ["QJSON_WEBOPEN_TIMEOUT"] = str(max(1.0, to))
    except Exception:
        pass
    try:
        mb = int(prefs.get("webopen_max_bytes", 204800))
        os.environ["QJSON_WEBOPEN_MAX_BYTES"] = str(max(1024, mb))
    except Exception:
        pass
    try:
        cap = int(prefs.get("webopen_cap", 12000))
        os.environ["QJSON_WEBOPEN_CAP"] = str(max(512, cap))
    except Exception:
        pass
    try:
        rt = float(prefs.get("crawl_rate", 1.0))
        os.environ["QJSON_CRAWL_RATE"] = str(max(0.05, rt))
    except Exception:
        pass
    if prefs.get("langsearch_api_key"):
        os.environ["LANGSEARCH_API_KEY"] = str(prefs.get("langsearch_api_key"))
    # Unified engine fetch settings
    if "find_fetch" in prefs:
        os.environ["QJSON_FIND_FETCH"] = "1" if prefs.get("find_fetch") else "0"
    if "find_fetch_top_n" in prefs:
        try:
            os.environ["QJSON_FIND_FETCH_TOP_N"] = str(max(0, int(prefs.get("find_fetch_top_n", 1))))
        except Exception:
            pass
    # Default /open mode (text|raw)
    mode = str(prefs.get("webopen_default", "text")).strip().lower()
    if mode in ("text","raw"):
        os.environ["QJSON_WEBOPEN_DEFAULT"] = mode


def _show_web_menu() -> None:
    prefs = _load_prefs()
    while True:
        print(
            """
== Search & Crawl Settings ==
1) Set default search mode (online/local)
2) Set web top-k
3) Set webopen timeout/max-bytes/cap
4) Set crawl rate
5) Set LangSearch API key
6) Toggle fetch top-N after search (and set N)
7) Run crawl now (non-interactive)
8) Clear cached results
9) Set default /open mode (raw|text)
10) Back
            """.strip()
        )
        sel = input("Select: ").strip()
        if sel == "1":
            cur = str(prefs.get("engine_mode", os.environ.get("QJSON_ENGINE_DEFAULT","online")))
            v = input(f"Default mode [online/local] [{cur}]: ").strip().lower() or cur
            if v in ("online","local"):
                prefs["engine_mode"] = v
                _save_prefs(prefs)
                os.environ["QJSON_ENGINE_DEFAULT"] = v
                print("Saved.")
            else:
                print("Invalid mode.")
        elif sel == "2":
            cur = str(prefs.get("web_topk", 5))
            v = input(f"Web top-k [{cur}]: ").strip() or cur
            try:
                prefs["web_topk"] = max(1, int(v))
                _save_prefs(prefs)
                _apply_web_env_from_prefs(prefs)
                print("Saved.")
            except Exception:
                print("Invalid value.")
        elif sel == "3":
            cur_to = str(prefs.get("webopen_timeout", 6.0))
            cur_mb = str(prefs.get("webopen_max_bytes", 204800))
            cur_cap = str(prefs.get("webopen_cap", 12000))
            to = input(f"Timeout seconds [{cur_to}]: ").strip() or cur_to
            mb = input(f"Max bytes [{cur_mb}]: ").strip() or cur_mb
            cap = input(f"Inject cap chars [{cur_cap}]: ").strip() or cur_cap
            try:
                prefs["webopen_timeout"] = float(to)
                prefs["webopen_max_bytes"] = int(mb)
                prefs["webopen_cap"] = int(cap)
                _save_prefs(prefs)
                _apply_web_env_from_prefs(prefs)
                print("Saved.")
            except Exception:
                print("Invalid values.")
        elif sel == "4":
            cur = str(prefs.get("crawl_rate", 1.0))
            v = input(f"Crawl rate per host (req/s) [{cur}]: ").strip() or cur
            try:
                prefs["crawl_rate"] = float(v)
                _save_prefs(prefs)
                _apply_web_env_from_prefs(prefs)
                print("Saved.")
            except Exception:
                print("Invalid value.")
        elif sel == "5":
            cur = str(prefs.get("langsearch_api_key", ""))
            v = input(f"LangSearch API key [{cur}]: ").strip() or cur
            prefs["langsearch_api_key"] = v
            _save_prefs(prefs)
            _apply_web_env_from_prefs(prefs)
            print("Saved.")
        elif sel == "6":
            cur_on = prefs.get("find_fetch", True)
            on = input(f"Fetch after search? (y/N) [{'Y' if cur_on else 'N'}]: ").strip().lower()
            if on:
                cur_on = on.startswith("y")
            cur_n = int(prefs.get("find_fetch_top_n", 1))
            n = input(f"Fetch top N [{cur_n}]: ").strip() or str(cur_n)
            try:
                prefs["find_fetch"] = bool(cur_on)
                prefs["find_fetch_top_n"] = max(0, int(n))
                _save_prefs(prefs)
                _apply_web_env_from_prefs(prefs)
                print("Saved.")
            except Exception:
                print("Invalid values.")
        elif sel == "7":
            seeds = input("Seed URLs (space-separated): ").strip().split()
            depth = input("Depth [1]: ").strip() or "1"
            pages = input("Pages [20]: ").strip() or "20"
            rate = str(prefs.get("crawl_rate", 1.0))
            allow = input("Allowed domain(s) (comma-separated, optional): ").strip()
            argv = ["crawl", "--seeds", *seeds, "--depth", depth, "--pages", pages, "--rate", str(rate)]
            if allow:
                for d in [x.strip() for x in allow.split(",") if x.strip()]:
                    argv += ["--allowed-domain", d]
            _execute_command(argv)
        elif sel == "8":
            os.environ.pop("QJSON_WEBRESULTS_CACHE", None)
            os.environ.pop("QJSON_WEBSEARCH_RESULTS_ONCE", None)
            print("Cleared.")
        elif sel == "9":
            cur = str(prefs.get("webopen_default", os.environ.get("QJSON_WEBOPEN_DEFAULT","text")))
            v = input(f"Default /open mode [raw|text] [{cur}]: ").strip().lower() or cur
            if v in ("raw","text"):
                prefs["webopen_default"] = v
                _save_prefs(prefs)
                _apply_web_env_from_prefs(prefs)
                print("Saved.")
            else:
                print("Invalid mode.")
        elif sel == "10":
            return
        else:
            print("Invalid selection.")


def _get_ollama_models() -> List[str]:
    try:
        from qjson_agents.ollama_client import OllamaClient
        client = OllamaClient()
        models = client.tags()
        return [m.get("name") for m in models if m.get("name")]
    except Exception:
        return []


def _scan_agent_ids() -> List[str]:
    # TTL cache to avoid rescanning large state dir repeatedly
    now = time.time()
    cache_key = "agent_ids"
    cached = _CACHE["agent_ids"].get(cache_key)
    if cached and (now - cached[0]) <= 1.0:
        return cached[1]
    state = _repo_root() / "state"
    if not state.exists():
        res: List[str] = []
        _CACHE["agent_ids"][cache_key] = (now, res)
        return res
    res = sorted([p.name for p in state.iterdir() if p.is_dir()])
    _CACHE["agent_ids"][cache_key] = (now, res)
    return res


def _select_from_list(title: str, items: List[str], allow_empty: bool = False, multi: bool = False, default_idx: int | None = None) -> List[str] | str:
    if not items and not allow_empty:
        print(f"No items found for {title}.")
        return ""
    print(f"\n== {title} ==")
    for i, it in enumerate(items, 1):
        mark = " (default)" if default_idx is not None and (i - 1) == default_idx else ""
        print(f"{i}) {it}{mark}")
    extra = []
    if allow_empty:
        extra.append("E) Empty")
    extra.append("C) Custom path/input")
    print(" ".join(extra))
    sel = input("Select: ").strip()
    if allow_empty and sel.upper().startswith("E"):
        return [] if multi else ""
    if sel.upper().startswith("C"):
        val = input("Enter value: ").strip()
        return [val] if multi else val
    # Default on empty
    if not sel and default_idx is not None and 0 <= default_idx < len(items):
        return [items[default_idx]] if multi else items[default_idx]
    # Parse indices
    try:
        if multi:
            idxs = [int(x) for x in sel.replace(",", " ").split() if x]
            chosen = []
            for ix in idxs:
                if 1 <= ix <= len(items):
                    chosen.append(items[ix - 1])
            return chosen
        else:
            ix = int(sel)
            if 1 <= ix <= len(items):
                return items[ix - 1]
    except Exception:
        pass
    print("Invalid selection.")
    return [] if multi else ""


def _show_agent_menu() -> None:
    while True:
        print(
            """
== Agent Management ==
1) init          2) chat         3) status
4) fork          5) loop         6) swap
7) evolve        8) introspect   9) Back
10) retrieval settings
11) toggle context summary
12) Keystone quick load (DevOps/Research/Swarm)
13) Custom Agent Mode (semi-autonomous)
            """.strip()
        )
        choice = input("Select: ").strip()
        if choice == "1":
            files = _scan_files(["manifests/*.json", "personas/*.json", "personas/*.yson", "personas/*.ysonx"]) 
            sel = _select_from_list("Select manifest", [str(p) for p in files], allow_empty=False, default_idx=0)
            manifest = sel if isinstance(sel, str) else (sel[0] if sel else "")
            models = _get_ollama_models()
            model = _select_from_list("Select model (optional)", models, allow_empty=True)
            argv = ["init", "--manifest", manifest]
            if model:
                argv += ["--model", model]
            _execute_command(argv)
        elif choice == "2":
            agents = _scan_agent_ids()
            def_idx = agents.index("Lila-v∞") if "Lila-v∞" in agents else (0 if agents else None)
            sel_id = _select_from_list("Select agent (or Custom)", agents, allow_empty=True, default_idx=def_idx)
            agent_id = sel_id if isinstance(sel_id, str) and sel_id else _ask("Agent ID", default="Lila-v∞")
            files = _scan_files(["manifests/*.json", "personas/*.json", "personas/*.yson", "personas/*.ysonx"]) 
            selm = _select_from_list("Manifest path (optional)", [str(p) for p in files], allow_empty=True, default_idx=0)
            manifest = selm if isinstance(selm, str) else (selm[0] if selm else "")
            models = _get_ollama_models()
            model = _select_from_list("Select model (optional)", models, allow_empty=True)
            prefs = _load_prefs()
            last_max = str(prefs.get("chat_max_tokens", "")) if prefs.get("chat_max_tokens") else None
            max_tokens = _ask("Max tokens (optional)", required=False, default=last_max)
            allow_exec = _ask("Allow YSON logic exec? (y/N)", required=False, default="N")
            allow_logic = _ask("Allow persona logic hooks? (y/N)", required=False, default="N")
            logic_mode = _ask("Logic mode (assist/replace)", required=False, default="assist")
            # Retrieval session toggles
            r_enabled, r_k, r_decay, r_min, _, _, r_note = _get_retrieval_prefs(prefs)
            # IVF/FMM current
            fmm_enabled = bool(prefs.get("retrieval_fmm_enabled", True))
            ivf_k = int(prefs.get("retrieval_ivf_k", 64))
            ivf_nprobe = int(prefs.get("retrieval_ivf_nprobe", 4))
            ivf_thresh = int(prefs.get("retrieval_ivf_reindex_threshold", 512))
            retr_def = "Y" if r_enabled else "N"
            retr = _ask("Enable retrieval? (y/N)", required=False, default=retr_def)
            if retr.strip().lower().startswith("y"):
                os.environ["QJSON_RETRIEVAL"] = "1"
                k = _ask("Retrieval top-k", required=False, default=str(r_k))
                d = _ask("Retrieval decay (float)", required=False, default=str(r_decay))
                mn = _ask("Retrieval min score (0..1)", required=False, default=str(r_min))
                nt = _ask("Add retrieval note to system prompt? (Y/n)", required=False, default=("Y" if r_note else "N"))
                try:
                    os.environ["QJSON_RETRIEVAL_TOPK"] = str(max(1, int(k)))
                    prefs["retrieval_top_k"] = int(k)
                except Exception:
                    pass
                try:
                    os.environ["QJSON_RETRIEVAL_DECAY"] = str(float(d))
                    prefs["retrieval_decay"] = float(d)
                except Exception:
                    pass
                try:
                    os.environ["QJSON_RETRIEVAL_MINSCORE"] = str(float(mn))
                    prefs["retrieval_minscore"] = float(mn)
                except Exception:
                    pass
                prefs["retrieval_note"] = (nt.strip().lower().startswith("y") or nt.strip() == "")
                prefs["retrieval_enabled"] = True

                # IVF/FMM prompts
                fmm_q = _ask("Use IVF/FMM accelerated index? (Y/n)", required=False, default=("Y" if fmm_enabled else "N"))
                fmm_enabled = not fmm_q.strip().lower().startswith('n')
                try:
                    ivf_k = max(2, int(_ask("IVF centroids K", required=False, default=str(ivf_k))))
                except Exception:
                    pass
                try:
                    ivf_nprobe = max(1, int(_ask("IVF nprobe (clusters per query)", required=False, default=str(ivf_nprobe))))
                except Exception:
                    pass
                try:
                    ivf_thresh = max(1, int(_ask("Auto reindex threshold (#memories)", required=False, default=str(ivf_thresh))))
                except Exception:
                    pass
                # Apply to env immediately
                os.environ["QJSON_RETR_USE_FMM"] = "1" if fmm_enabled else "0"
                os.environ["QJSON_RETR_IVF_K"] = str(ivf_k)
                os.environ["QJSON_RETR_IVF_NPROBE"] = str(ivf_nprobe)
                os.environ["QJSON_RETR_REINDEX_THRESHOLD"] = str(ivf_thresh)
                # Persist prefs
                prefs["retrieval_fmm_enabled"] = fmm_enabled
                prefs["retrieval_ivf_k"] = ivf_k
                prefs["retrieval_ivf_nprobe"] = ivf_nprobe
                prefs["retrieval_ivf_reindex_threshold"] = ivf_thresh
            else:
                os.environ.pop("QJSON_RETRIEVAL", None)
                prefs["retrieval_enabled"] = False
            _save_prefs(prefs)
            argv = ["chat", "--id", agent_id]
            if manifest:
                argv += ["--manifest", manifest]
            if model:
                argv += ["--model", model]
            if max_tokens and max_tokens.isdigit():
                argv += ["--max-tokens", max_tokens]
                try:
                    prefs["chat_max_tokens"] = int(max_tokens)
                    _save_prefs(prefs)
                except Exception:
                    pass
            if allow_exec.lower().startswith("y"):
                argv.append("--allow-yson-exec")
            if allow_logic.lower().startswith("y"):
                argv.append("--allow-logic")
                lm = (logic_mode or "").strip().lower()
                if lm in ("assist","replace"):
                    argv += ["--logic-mode", lm]
            _execute_command(argv)
        elif choice == "3":
            agents = _scan_agent_ids()
            sel_id = _select_from_list("Select agent", agents, allow_empty=False, default_idx=0)
            agent_id = sel_id if isinstance(sel_id, str) else (sel_id[0] if sel_id else _ask("Agent ID"))
            tail = _ask("Tail lines", required=False, default="12")
            argv = ["status", "--id", agent_id, "--tail", tail]
            _execute_command(argv)
        elif choice == "4":
            agents = _scan_agent_ids()
            sel_id = _select_from_list("Select source agent", agents, allow_empty=False, default_idx=0)
            source = sel_id if isinstance(sel_id, str) else (sel_id[0] if sel_id else _ask("Source agent ID"))
            new_id = _ask("New agent ID")
            note = _ask("Note (optional)", required=False)
            argv = ["fork", "--source", source, "--new-id", new_id]
            if note:
                argv += ["--note", note]
            _execute_command(argv)
        elif choice == "5":
            agents = _scan_agent_ids()
            def_idx = agents.index("Lila-v∞") if "Lila-v∞" in agents else (0 if agents else None)
            sel_id = _select_from_list("Select agent (or Custom)", agents, allow_empty=True, default_idx=def_idx)
            agent_id = sel_id if isinstance(sel_id, str) and sel_id else _ask("Agent ID", default="Lila-v∞")
            files = _scan_files(["manifests/*.json", "personas/*.json", "personas/*.yson", "personas/*.ysonx"]) 
            selm = _select_from_list("Manifest path (optional)", [str(p) for p in files], allow_empty=True, default_idx=0)
            manifest = selm if isinstance(selm, str) else (selm[0] if selm else "")
            models = _get_ollama_models()
            model = _select_from_list("Select model or 'auto' (optional)", models, allow_empty=True)
            goal = _ask("Loop goal", required=False, default="perform self-diagnostic and reinforce identity while documenting anomalies")
            iterations = _ask("Iterations", required=False, default="3")
            delay = _ask("Delay (seconds)", required=False, default="0.0")
            # Optional retrieval for loop
            prefs = _load_prefs()
            r_enabled, r_k, r_decay, _, _ = _get_retrieval_prefs(prefs)
            fmm_enabled = bool(prefs.get("retrieval_fmm_enabled", True))
            ivf_k = int(prefs.get("retrieval_ivf_k", 64))
            ivf_nprobe = int(prefs.get("retrieval_ivf_nprobe", 4))
            ivf_thresh = int(prefs.get("retrieval_ivf_reindex_threshold", 512))
            retr_def = "Y" if r_enabled else "N"
            retr = _ask("Enable retrieval for loop? (y/N)", required=False, default=retr_def)
            if retr.strip().lower().startswith("y"):
                os.environ["QJSON_RETRIEVAL"] = "1"
                os.environ["QJSON_RETRIEVAL_TOPK"] = str(r_k)
                os.environ["QJSON_RETRIEVAL_DECAY"] = str(r_decay)
                # IVF/FMM
                fmm_q = _ask("Use IVF/FMM accelerated index? (Y/n)", required=False, default=("Y" if fmm_enabled else "N"))
                fmm_enabled = not fmm_q.strip().lower().startswith('n')
                os.environ["QJSON_RETR_USE_FMM"] = "1" if fmm_enabled else "0"
                try:
                    ivf_k = max(2, int(_ask("IVF centroids K", required=False, default=str(ivf_k))))
                except Exception:
                    pass
                try:
                    ivf_nprobe = max(1, int(_ask("IVF nprobe (clusters per query)", required=False, default=str(ivf_nprobe))))
                except Exception:
                    pass
                try:
                    ivf_thresh = max(1, int(_ask("Auto reindex threshold (#memories)", required=False, default=str(ivf_thresh))))
                except Exception:
                    pass
                os.environ["QJSON_RETR_IVF_K"] = str(ivf_k)
                os.environ["QJSON_RETR_IVF_NPROBE"] = str(ivf_nprobe)
                os.environ["QJSON_RETR_REINDEX_THRESHOLD"] = str(ivf_thresh)
            argv = [
                "loop", "--id", agent_id,
                "--goal", goal,
                "--iterations", iterations,
                "--delay", delay,
            ]
            if manifest:
                argv += ["--manifest", manifest]
            if model:
                argv += ["--model", model]
            _execute_command(argv)
        elif choice == "6":
            agents = _scan_agent_ids()
            sel_id = _select_from_list("Select agent", agents, allow_empty=False, default_idx=0)
            agent_id = sel_id if isinstance(sel_id, str) else (sel_id[0] if sel_id else _ask("Agent ID"))
            files = _scan_files(["personas/*.json", "personas/*.yson", "personas/*.ysonx"]) 
            selp = _select_from_list("Persona path/id/tag", [str(p) for p in files], allow_empty=True, default_idx=0)
            persona = selp if isinstance(selp, str) and selp else _ask("Persona path/id/tag")
            cause = _ask("Cause (optional)", required=False)
            argv = ["swap", "--id", agent_id, "--persona", persona]
            if cause:
                argv += ["--cause", cause]
            _execute_command(argv)
        elif choice == "7":
            agent_id = _ask("Agent ID")
            dry = _ask("Dry-run? (y/N)", required=False, default="N")
            argv = ["evolve", "--id", agent_id]
            if dry.lower().startswith("y"):
                argv.append("--dry-run")
            _execute_command(argv)
        elif choice == "8":
            agent_id = _ask("Agent ID")
            auto = _ask("Auto-adapt? (y/N)", required=False, default="N")
            trig = _ask("User trigger token (optional)", required=False)
            argv = ["introspect", "--id", agent_id]
            if auto.lower().startswith("y"):
                argv.append("--auto")
            if trig:
                argv += ["--user-trigger", trig]
            _execute_command(argv)
        elif choice == "9":
            return
        elif choice == "10":
            _show_retrieval_menu()
        elif choice == "11":
            prefs = _load_prefs()
            cur = bool(prefs.get("show_context", True))
            v = _ask("Show context summary in chat? (Y/n)", required=False, default=("Y" if cur else "N"))
            new_val = not v.strip().lower().startswith("n")
            prefs["show_context"] = new_val
            _save_prefs(prefs)
            _apply_general_env_from_prefs(prefs)
            print(f"Saved. Context summary {'enabled' if new_val else 'disabled'}.")
        elif choice == "12":
            _keystone_quickload()
        elif choice == "13":
            _custom_mode_wizard()
        else:
            print("Invalid selection.")


def _show_retrieval_menu() -> None:
    prefs = _load_prefs()
    enabled, topk, decay, minscore, ingest, cap, note = _get_retrieval_prefs(prefs)
    # IVF/FMM current prefs
    fmm_enabled = bool(prefs.get("retrieval_fmm_enabled", True))
    ivf_k = int(prefs.get("retrieval_ivf_k", 64))
    ivf_nprobe = int(prefs.get("retrieval_ivf_nprobe", 4))
    ivf_thresh = int(prefs.get("retrieval_ivf_reindex_threshold", 512))

    print("\n== Retrieval Settings ==")
    print(f"Current: {'on' if enabled else 'off'}  k={topk}  decay={decay}  min={minscore}  ingest={'on' if ingest else 'off'} cap={cap} note={'on' if note else 'off'}")
    print(f"IVF/FMM: {'on' if fmm_enabled else 'off'}  K={ivf_k}  nprobe={ivf_nprobe}  reindex_threshold={ivf_thresh}")
    on = _ask("Enable retrieval? (y/N)", required=False, default=("Y" if enabled else "N"))
    if on.strip().lower().startswith("y"):
        try:
            topk = max(1, int(_ask("Top-k", required=False, default=str(topk))))
        except Exception:
            pass
        try:
            decay = float(_ask("Time decay (float)", required=False, default=str(decay)))
        except Exception:
            pass
        try:
            minscore = float(_ask("Min score (0..1)", required=False, default=str(minscore)))
        except Exception:
            pass
        nt = _ask("Add retrieval note to system prompt? (Y/n)", required=False, default=("Y" if note else "N"))
        ing = _ask("Seed on ingest? (y/N)", required=False, default=("Y" if ingest else "N"))
        if ing.strip().lower().startswith("y"):
            ingest = True
            try:
                cap = max(128, int(_ask("Ingest cap (chars)", required=False, default=str(cap))))
            except Exception:
                pass
        else:
            ingest = False
        # IVF/FMM toggles
        fmm_q = _ask("Use IVF/FMM accelerated index? (Y/n)", required=False, default=("Y" if fmm_enabled else "N"))
        fmm_enabled = not fmm_q.strip().lower().startswith('n')
        try:
            ivf_k = max(2, int(_ask("IVF centroids K", required=False, default=str(ivf_k))))
        except Exception:
            pass
        try:
            ivf_nprobe = max(1, int(_ask("IVF nprobe (clusters per query)", required=False, default=str(ivf_nprobe))))
        except Exception:
            pass
        try:
            ivf_thresh = max(1, int(_ask("Auto reindex threshold (#memories)", required=False, default=str(ivf_thresh))))
        except Exception:
            pass

        prefs.update({
            "retrieval_enabled": True,
            "retrieval_top_k": topk,
            "retrieval_decay": decay,
            "retrieval_minscore": minscore,
            "retrieval_ingest": ingest,
            "retrieval_ingest_cap": cap,
            "retrieval_note": (nt.strip().lower().startswith('y') or nt.strip()==''),
            # IVF/FMM
            "retrieval_fmm_enabled": fmm_enabled,
            "retrieval_ivf_k": ivf_k,
            "retrieval_ivf_nprobe": ivf_nprobe,
            "retrieval_ivf_reindex_threshold": ivf_thresh,
        })
    else:
        prefs.update({
            "retrieval_enabled": False,
        })
    _save_prefs(prefs)
    _apply_retrieval_env_from_prefs(prefs)
    print("[retrieval] settings saved.")

    # Optional: on-demand reindex
    do_reindex = _ask("Rebuild IVF index now? (y/N)", required=False, default="N")
    if do_reindex.strip().lower().startswith("y"):
        agents = _scan_agent_ids()
        sel_id = _select_from_list("Select agent to reindex", agents, allow_empty=False, default_idx=0)
        agent_id = sel_id if isinstance(sel_id, str) else (sel_id[0] if sel_id else _ask("Agent ID"))
        iters = _ask("KMeans iterations", required=False, default="3")
        argv = ["reindex", "--id", agent_id, "--k", str(prefs.get('retrieval_ivf_k', 64)), "--iters", iters]
        _execute_command(argv)


def _show_swarm_menu() -> None:
    while True:
        print(
            """
== Swarm & Cluster Management ==
1) cluster        2) cluster-test
3) yson-run-swarm 4) ysonx-swarm-launch
5) Back
            """.strip()
        )
        choice = input("Select: ").strip()
        if choice == "1":
            agent_id = _ask("Root agent ID (optional)", required=False)
            tree = _ask("Tree view? (y/N)", required=False, default="N")
            refresh = _ask("Refresh index? (y/N)", required=False, default="N")
            argv = ["cluster"]
            if agent_id:
                argv += ["--id", agent_id]
            if tree.lower().startswith("y"):
                argv.append("--tree")
            if refresh.lower().startswith("y"):
                argv.append("--refresh")
            _execute_command(argv)
        elif choice == "2":
            files = _scan_files(["manifests/*.json", "personas/*.json", "personas/*.yson", "personas/*.ysonx"]) 
            sel_multi = _select_from_list("Select manifests (or Custom)", [str(p) for p in files], allow_empty=True, multi=True)
            if isinstance(sel_multi, list) and sel_multi:
                manifests = " ".join(sel_multi)
                manifest = ""
            else:
                manifests = ""
                sel_one = _select_from_list("Manifest path (optional)", [str(p) for p in files], allow_empty=True)
                manifest = sel_one if isinstance(sel_one, str) else (sel_one[0] if sel_one else "")
            duration = _ask("Duration seconds", required=False, default="120")
            interval = _ask("Interval seconds", required=False, default="0.5")
            topology = _ask("Topology (ring/mesh/moe)", required=False, default="moe")
            moe_k = _ask("MoE top-k", required=False, default="2")
            cooldown = _ask("Router cooldown (seconds)", required=False, default="0.0")
            use_ollama = _ask("Use Ollama? (y/N)", required=False, default="Y")
            models = _get_ollama_models()
            model = _select_from_list("Select model (optional)", models, allow_empty=True, default_idx=0)
            argv = [
                "cluster-test",
                "--duration", duration,
                "--interval", interval,
                "--topology", topology,
                "--moe-topk", moe_k,
                "--rate-limit-cooldown", cooldown,
            ]
            if manifests:
                argv += ["--manifests", *manifests.split()]
            elif manifest:
                argv += ["--manifest", manifest]
            if use_ollama.lower().startswith("y"):
                argv.append("--use-ollama")
                if model:
                    argv += ["--model", model]
            _execute_command(argv)
        elif choice == "3":
            files = _scan_files(["yson/*.yson", "yson/*.ysonx"]) 
            sel = _select_from_list("Swarm YSON/YSONX file", [str(p) for p in files], allow_empty=False, default_idx=0)
            yson = sel if isinstance(sel, str) else (sel[0] if sel else _ask("Swarm YSON/YSONX file"))
            duration = _ask("Duration seconds", required=False, default="120")
            interval = _ask("Interval seconds", required=False, default="0.5")
            use_ollama = _ask("Use Ollama? (y/N)", required=False, default="Y")
            models = _get_ollama_models()
            model = _select_from_list("Select model (optional)", models, allow_empty=True, default_idx=0)
            moe_k = _ask("MoE top-k", required=False, default="2")
            cooldown = _ask("Router cooldown (seconds)", required=False, default="0.0")
            allow_exec = _ask("Allow YSON logic exec? (y/N)", required=False, default="N")
            argv = [
                "yson-run-swarm", "--yson", yson,
                "--duration", duration,
                "--interval", interval,
                "--moe-topk", moe_k,
                "--rate-limit-cooldown", cooldown,
            ]
            if use_ollama.lower().startswith("y"):
                argv.append("--use-ollama")
                if model:
                    argv += ["--model", model]
            if allow_exec.lower().startswith("y"):
                argv.append("--allow-yson-exec")
            _execute_command(argv)
        elif choice == "4":
            files = _scan_files(["genesis/*.ysonx", "personas/*.ysonx"]) 
            sel_multi = _select_from_list("Select agents (multi)", [str(p) for p in files], allow_empty=False, multi=True)
            agents = " ".join(sel_multi) if isinstance(sel_multi, list) else _ask("Agent files (space-separated)")
            duration = _ask("Duration seconds", required=False, default="120")
            interval = _ask("Interval seconds", required=False, default="0.5")
            models = _get_ollama_models()
            model = _select_from_list("Select model (optional)", models, allow_empty=True, default_idx=0)
            moe_k = _ask("MoE top-k", required=False, default="3")
            cooldown = _ask("Router cooldown (seconds)", required=False, default="0.5")
            argv = [
                "ysonx-swarm-launch",
                "--agents", *agents.split(),
                "--duration", duration,
                "--interval", interval,
                "--topology", "moe",
                "--moe-topk", moe_k,
                "--rate-limit-cooldown", cooldown,
                "--use-ollama",
                "--model", model,
            ]
            _execute_command(argv)
        elif choice == "5":
            return
        else:
            print("Invalid selection.")


def _show_yson_menu() -> None:
    while True:
        print(
            """
== YSON & Manifest Tools ==
1) yson-validate     2) ysonx-convert
3) encode-manifest   4) decode-manifest
5) personas          6) Back
            """.strip()
        )
        choice = input("Select: ").strip()
        if choice == "1":
            files = _scan_files(["yson/*.yson", "yson/*.ysonx", "personas/*.yson", "personas/*.ysonx"]) 
            sel = _select_from_list("YSON/YSONX path", [str(p) for p in files], allow_empty=False, default_idx=0)
            path = sel if isinstance(sel, str) else (sel[0] if sel else _ask("YSON/YSONX path"))
            strict = _ask("Strict mode? (y/N)", required=False, default="N")
            argv = ["yson-validate", "--path", path]
            if strict.lower().startswith("y"):
                argv.append("--strict")
            _execute_command(argv)
        elif choice == "2":
            files = _scan_files(["personas/*.json", "personas/*.yson", "yson/*.yson"]) 
            sel = _select_from_list("Input file or dir (.json/.yson)", [str(p) for p in files], allow_empty=True, default_idx=0)
            src = sel if isinstance(sel, str) and sel else _ask("Input file or dir (.json/.yson)")
            outd = _ask("Output dir (optional)", required=False)
            argv = ["ysonx-convert", "--input", src]
            if outd:
                argv += ["--output-dir", outd]
            _execute_command(argv)
        elif choice == "3":
            files = _scan_files(["manifests/*.json"]) 
            sel = _select_from_list("Plain manifest .json path", [str(p) for p in files], allow_empty=False, default_idx=0)
            inp = sel if isinstance(sel, str) else (sel[0] if sel else _ask("Plain manifest .json path"))
            outp = _ask("Output envelope path (.json)")
            pwd = _ask("Passphrase")
            depth = _ask("Fractal depth", required=False, default="2")
            fanout = _ask("Fractal fanout", required=False, default="3")
            argv = ["encode-manifest", "--in", inp, "--out", outp, "--passphrase", pwd, "--depth", depth, "--fanout", fanout]
            _execute_command(argv)
        elif choice == "4":
            # Limit heavy log scans for responsiveness; show most recent first
            files = _scan_files(["logs/**/*.json"], sort_mtime=True, limit=200)
            sel = _select_from_list("Envelope path (.json)", [str(p) for p in files], allow_empty=False, default_idx=0)
            inp = sel if isinstance(sel, str) else (sel[0] if sel else _ask("Envelope path (.json)"))
            outp = _ask("Output plain manifest path (.json)")
            pwd = _ask("Passphrase")
            argv = ["decode-manifest", "--in", inp, "--out", outp, "--passphrase", pwd]
            _execute_command(argv)
        elif choice == "5":
            as_json = _ask("JSON output? (y/N)", required=False, default="N")
            argv = ["personas"]
            if as_json.lower().startswith("y"):
                argv.append("--json")
            _execute_command(argv)
        elif choice == "6":
            return
        else:
            print("Invalid selection.")


def _show_system_menu() -> None:
    while True:
        print(
            """
== System & Utilities ==
1) models    2) test    3) analyze
4) toggle context summary
5) Back
            """.strip()
        )
        choice = input("Select: ").strip()
        if choice == "1":
            _execute_command(["models"])
        elif choice == "2":
            manifest = _ask("Manifest path (optional)", required=False)
            duration = _ask("Duration seconds", required=False, default="120")
            interval = _ask("Interval seconds", required=False, default="0.5")
            use_ollama = _ask("Use Ollama? (y/N)", required=False, default="N")
            models = _get_ollama_models()
            model = _select_from_list("Select model (optional)", models, allow_empty=True, default_idx=0)
            argv = ["test", "--duration", duration, "--interval", interval]
            if manifest:
                argv += ["--manifest", manifest]
            if use_ollama.lower().startswith("y"):
                argv.append("--use-ollama")
                if model:
                    argv += ["--model", model]
            _execute_command(argv)
        elif choice == "3":
            path = _ask("Run JSON path")
            compare = _ask("Compare to JSON path (optional)", required=False)
            as_json = _ask("JSON output? (y/N)", required=False, default="N")
            argv = ["analyze", "--path", path]
            if compare:
                argv += ["--compare", compare]
            if as_json.lower().startswith("y"):
                argv.append("--json")
            _execute_command(argv)
        elif choice == "4":
            prefs = _load_prefs()
            cur = bool(prefs.get("show_context", True))
            v = _ask("Show context summary in chat? (Y/n)", required=False, default=("Y" if cur else "N"))
            new_val = not v.strip().lower().startswith("n")
            prefs["show_context"] = new_val
            _save_prefs(prefs)
            _apply_general_env_from_prefs(prefs)
            print(f"Saved. Context summary {'enabled' if new_val else 'disabled'}.")
        elif choice == "5":
            return
        else:
            print("Invalid selection.")


def _show_plugins_menu() -> None:
    while True:
        print(
            """
== Plugins & Tools ==
1) File System       2) Exec (Python)
3) Git               4) Generic API
5) SQLite DB         6) Advanced (Forge/Prism/KG/Continuum/Meme)
7) Back
            """.strip()
        )
        choice = input("Select: ").strip()
        if choice == "1":
            _plugins_fs_menu()
        elif choice == "2":
            _plugins_exec_menu()
        elif choice == "3":
            _plugins_git_menu()
        elif choice == "4":
            _plugins_api_menu()
        elif choice == "5":
            _plugins_sqlite_menu()
        elif choice == "6":
            _plugins_advanced_menu()
        elif choice == "7":
            return
        else:
            print("Invalid selection.")


def _plugins_fs_menu() -> None:
    prefs = _load_prefs()
    while True:
        roots = os.environ.get("QJSON_FS_ROOTS", prefs.get("fs_roots", str(_repo_root())))
        print(
            f"""
== File System == (roots: {roots})
1) Set FS roots (os.pathsep-separated)
2) List files (/fs_list)
3) Read file (/fs_read)
4) Write file (/fs_write) [gated]
5) Back
            """.strip()
        )
        sel = input("Select: ").strip()
        if sel == "1":
            val = _ask("FS roots", required=False, default=roots)
            prefs["fs_roots"] = val
            _save_prefs(prefs)
            os.environ["QJSON_FS_ROOTS"] = val
            print("Saved.")
        elif sel == "2":
            base = _ask("Path", required=False, default=str(_repo_root()))
            glob = _ask("Glob (optional)", required=False)
            mx = _ask("Max N", required=False, default="50")
            agent = _choose_agent_id("Agent ID for context (optional)")
            cmd = f"/fs_list {base}"
            if glob:
                cmd += f" glob={glob}"
            cmd += f" max={mx}"
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "3":
            path = _ask("File path")
            mb = _ask("Max bytes", required=False, default="65536")
            agent = _choose_agent_id("Agent ID for context (optional)")
            cmd = f"/fs_read {path} max_bytes={mb}"
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "4":
            os.environ["QJSON_FS_WRITE"] = "1"
            path = _ask("File path")
            src = _ask("Text or @file", required=False, default="@")
            append = _ask("Append? (y/N)", required=False, default="N")
            agent = _choose_agent_id("Agent ID for context (optional)")
            cmd = f"/fs_write {path} {src} append={'1' if append.lower().startswith('y') else '0'}"
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "5":
            return
        else:
            print("Invalid selection.")


def _plugins_exec_menu() -> None:
    while True:
        print(
            """
== Exec (Python) ==
1) Toggle allow exec (QJSON_ALLOW_EXEC)
2) Run inline code
3) Run @file.py
4) Back
            """.strip()
        )
        sel = input("Select: ").strip()
        if sel == "1":
            cur = os.environ.get("QJSON_ALLOW_EXEC", "0") == "1"
            v = _ask("Enable exec? (y/N)", required=False, default=("Y" if cur else "N"))
            os.environ["QJSON_ALLOW_EXEC"] = "1" if v.lower().startswith("y") else "0"
            print("Saved.")
        elif sel == "2":
            code = _ask("Python code (e.g., print(2+2))")
            agent = _choose_agent_id("Agent ID (optional)")
            cmd = f"/py {code}"
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "3":
            path = _ask("Path to @file.py")
            agent = _choose_agent_id("Agent ID (optional)")
            cmd = f"/py @{path}"
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "4":
            return
        else:
            print("Invalid selection.")


def _plugins_git_menu() -> None:
    prefs = _load_prefs()
    while True:
        root = os.environ.get("QJSON_GIT_ROOT", prefs.get("git_root", str(_repo_root())))
        print(
            f"""
== Git (read-only) == (root: {root})
1) Set git root
2) Status (/git_status)
3) Log (/git_log)
4) Diff (/git_diff)
5) Back
            """.strip()
        )
        sel = input("Select: ").strip()
        if sel == "1":
            val = _ask("Git root", required=False, default=root)
            prefs["git_root"] = val
            _save_prefs(prefs)
            os.environ["QJSON_GIT_ROOT"] = val
            print("Saved.")
        elif sel == "2":
            short = _ask("Short? (Y/n)", required=False, default="Y").lower().startswith("y")
            agent = _choose_agent_id("Agent ID (optional)")
            cmd = f"/git_status {'short=1' if short else ''}".strip()
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "3":
            n = _ask("Show last N", required=False, default="10")
            agent = _choose_agent_id("Agent ID (optional)")
            cmd = f"/git_log {n}"
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "4":
            path = _ask("Path to diff (relative to root)", required=False, default="")
            agent = _choose_agent_id("Agent ID (optional)")
            cmd = f"/git_diff {path}".strip()
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "5":
            return
        else:
            print("Invalid selection.")


def _plugins_api_menu() -> None:
    while True:
        net = os.environ.get("QJSON_ALLOW_NET", "0") == "1"
        print(
            f"""
== Generic API == (allow_net={net})
1) Toggle network (QJSON_ALLOW_NET)
2) GET (/api_get)
3) POST (/api_post)
4) Back
            """.strip()
        )
        sel = input("Select: ").strip()
        if sel == "1":
            v = _ask("Enable network? (y/N)", required=False, default=("Y" if net else "N"))
            os.environ["QJSON_ALLOW_NET"] = "1" if v.lower().startswith("y") else "0"
            print("Saved.")
        elif sel == "2":
            url = _ask("URL")
            hdr = _ask("Headers h:K=V (space-separated, optional)", required=False)
            timeout = _ask("Timeout seconds", required=False, default="6")
            maxc = _ask("Max preview chars", required=False, default="4000")
            agent = _choose_agent_id("Agent ID (optional)")
            cmd = f"/api_get {url} {hdr or ''} timeout={timeout} max={maxc}".strip()
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "3":
            url = _ask("URL")
            body = _ask("Body (single-quoted JSON recommended)")
            ct = _ask("Content-Type", required=False, default="application/json")
            timeout = _ask("Timeout seconds", required=False, default="6")
            maxc = _ask("Max preview chars", required=False, default="4000")
            agent = _choose_agent_id("Agent ID (optional)")
            cmd = f"/api_post {url} body={body} ct={ct} timeout={timeout} max={maxc}"
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "4":
            return
        else:
            print("Invalid selection.")


def _plugins_sqlite_menu() -> None:
    pl = _ensure_sqlite_plugin()
    if pl is None:
        print("[sql] SQLite plugin unavailable.")
        return
    while True:
        print(
            """
== SQLite DB == (stateful)
1) Open DB (path) [ro=1]
2) Tables
3) Query (json=1 max=N)
4) Close
5) Back
            """.strip()
        )
        sel = input("Select: ").strip()
        if sel == "1":
            path = _ask("DB path")
            ro = _ask("Read-only? (Y/n)", required=False, default="Y").lower().startswith("y")
            print(pl.sql_open(path, f"ro={'1' if ro else '0'}"))
        elif sel == "2":
            print(pl.sql_tables())
        elif sel == "3":
            sql = _ask("SQL (e.g., select * from t)")
            mx = _ask("max N", required=False, default="200")
            j = _ask("json output? (Y/n)", required=False, default="Y").lower().startswith("y")
            print(pl.sql_query(*([*sql.split(), f"max={mx}", f"json={'1' if j else '0'}"])) )
        elif sel == "4":
            print(pl.sql_close())
        elif sel == "5":
            return
        else:
            print("Invalid selection.")


def _plugins_advanced_menu() -> None:
    while True:
        print(
            """
== Advanced Plugins ==
1) Forge (/forge create/info/plugins/goal)
2) Delegate/Report (Forge)
3) Prism (/prism hats)
4) Holistic‑Scribe (/kg)
5) Continuum (/continuum export/import)
6) Meme‑Weaver (/meme)
7) Back
            """.strip()
        )
        sel = input("Select: ").strip()
        if sel == "1":
            sub = _ask("create/info/plugins/goal", required=False, default="create")
            aid = _ask("Agent ID")
            if sub == "create":
                role = _ask("role", required=False, default="specialist")
                model = _ask("model", required=False, default="gemma3:4b")
                goal = _ask("goal", required=False)
                plugins = _ask("plugins (comma-separated)", required=False)
                cmd = f"/forge create {aid} role={role} model={model} {'goal='+goal if goal else ''} {'plugins='+plugins if plugins else ''}"
            elif sub == "info":
                cmd = f"/forge info {aid}"
            elif sub == "plugins":
                mode = _ask("set/add/del")
                vals = _ask("values (comma-separated)")
                cmd = f"/forge plugins {aid} {mode}={vals}"
            elif sub == "goal":
                text = _ask("goal text")
                cmd = f"/forge goal {aid} {text}"
            else:
                print("Unknown."); continue
            agent = _choose_agent_id("Parent agent ID (optional)")
            argv = ["exec", cmd]
            if agent:
                argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "2":
            aid = _ask("Target child agent ID")
            task = _ask("Task text")
            cmd = f"/forge delegate {aid} {task}"
            agent = _choose_agent_id("Parent agent ID (optional)")
            argv = ["exec", cmd]
            if agent: argv += ["--id", agent]
            _execute_command(argv)
            # report
            cmd = f"/forge report {aid}"
            argv = ["exec", cmd]
            if agent: argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "3":
            q = _ask("Question")
            hats = _ask("hats (comma-separated or 'auto')", required=False, default="auto")
            cmd = f"/prism {q} hats={hats}"
            agent = _choose_agent_id("Agent ID (optional)")
            argv = ["exec", cmd]
            if agent: argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "4":
            mode = _ask("add_node/add_edge/stats/export")
            agent = _choose_agent_id("Agent ID (optional)")
            if mode == "add_node":
                nid = _ask("id"); label = _ask("label", required=False, default=nid)
                tags = _ask("tags (comma-separated)", required=False)
                data = _ask("data JSON (optional)", required=False)
                cmd = f"/kg add_node id={nid} label={label} {'tags='+tags if tags else ''} {'data='+data if data else ''}".strip()
            elif mode == "add_edge":
                src = _ask("src"); dst = _ask("dst"); et = _ask("type", required=False, default="rel")
                w = _ask("weight", required=False, default="1.0"); data = _ask("data JSON (optional)", required=False)
                cmd = f"/kg add_edge src={src} dst={dst} type={et} weight={w} {'data='+data if data else ''}".strip()
            elif mode == "stats":
                cmd = "/kg stats"
            elif mode == "export":
                path = _ask("Mermaid output path")
                cmd = f"/kg export mermaid {path}"
            else:
                print("Unknown."); continue
            argv = ["exec", cmd]
            if agent: argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "5":
            sub = _ask("export/import")
            agent = _choose_agent_id("Agent ID (for export) (optional)")
            if sub == "export":
                outd = _ask("Destination dir", required=False, default=str(_repo_root()/"tmp"))
                cmd = f"/continuum export {agent or 'Agent'} path={outd}"
            else:
                arc = _ask("Path to tar.gz")
                new_id = _ask("New agent id")
                cmd = f"/continuum import {arc} new_id={new_id}"
            argv = ["exec", cmd]
            if agent: argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "6":
            sub = _ask("analyze/generate")
            agent = _choose_agent_id("Agent ID (optional)")
            if sub == "analyze":
                topic = _ask("topic")
                cmd = f"/meme analyze {topic}"
            else:
                topic = _ask("topic"); style = _ask("style", required=False, default="humor"); fmt = _ask("format", required=False, default="tweet")
                cmd = f"/meme generate text {topic} style={style} format={fmt}"
            argv = ["exec", cmd]
            if agent: argv += ["--id", agent]
            _execute_command(argv)
        elif sel == "7":
            return
        else:
            print("Invalid selection.")


def _keystone_quickload() -> None:
    files = [
        _repo_root() / "personas" / "DevOpsAgent.ysonx",
        _repo_root() / "personas" / "ResearchAgent.ysonx",
        _repo_root() / "personas" / "SwarmLord.ysonx",
    ]
    avail = [str(p) for p in files if p.exists()]
    if not avail:
        print("No Keystone personas found.")
        return
    sel = _select_from_list("Select Keystone persona", avail, allow_empty=False, default_idx=0)
    manifest = sel if isinstance(sel, str) else (sel[0] if sel else avail[0])
    # Initialize
    argv = ["init", "--manifest", manifest]
    _execute_command(argv)
    # Ask to enter chat and/or open Plugins menu
    do_chat = _ask("Start chat now? (Y/n)", required=False, default="Y")
    if not do_chat.strip().lower().startswith("n"):
        agent_id = Path(manifest).stem
        _execute_command(["chat", "--id", agent_id, "--manifest", manifest])
    else:
        j = _ask("Open Plugins & Tools menu? (Y/n)", required=False, default="Y")
        if not j.strip().lower().startswith("n"):
            _show_plugins_menu()


def _custom_mode_wizard() -> None:
    # Agent selection
    agents = _scan_agent_ids()
    sel_id = _select_from_list("Select base agent (or Custom)", agents, allow_empty=True, default_idx=(0 if agents else None))
    agent_id = sel_id if isinstance(sel_id, str) and sel_id else _ask("Agent ID", required=False, default="Lila-v∞")
    # Optional manifest to (re)initialize
    files = _scan_files(["personas/*.ysonx", "personas/*.yson", "manifests/*.json"]) 
    selm = _select_from_list("Manifest path (optional)", [str(p) for p in files], allow_empty=True, default_idx=0)
    manifest = selm if isinstance(selm, str) else (selm[0] if selm else "")
    if manifest:
        _execute_command(["init", "--manifest", manifest])
    # Plugin selection
    print("Select plugin categories (y/N):")
    use_fs = _ask("File System? (y/N)", required=False, default="Y")
    use_exec = _ask("Exec (Python)? (y/N)", required=False, default="N")
    use_git = _ask("Git? (y/N)", required=False, default="Y")
    use_api = _ask("Generic API? (y/N)", required=False, default="N")
    use_db = _ask("SQLite DB? (y/N)", required=False, default="N")
    use_adv = _ask("Advanced (Forge/Prism/KG/Continuum/Meme)? (y/N)", required=False, default="Y")
    allow: list[str] = []
    if use_fs.lower().startswith("y"):
        allow += ["/fs_list","/fs_read","/fs_write"]
        roots = _ask("FS roots (os.pathsep-separated)", required=False, default=os.environ.get("QJSON_FS_ROOTS",""))
        if roots:
            os.environ["QJSON_FS_ROOTS"] = roots
        if _ask("Allow FS writes? (y/N)", required=False, default="N").lower().startswith("y"):
            os.environ["QJSON_FS_WRITE"] = "1"
    if use_exec.lower().startswith("y"):
        allow += ["/py"]
        os.environ["QJSON_ALLOW_EXEC"] = "1"
    if use_git.lower().startswith("y"):
        allow += ["/git_status","/git_log","/git_diff"]
        root = _ask("Git root (optional)", required=False, default=os.environ.get("QJSON_GIT_ROOT",""))
        if root:
            os.environ["QJSON_GIT_ROOT"] = root
    if use_api.lower().startswith("y"):
        allow += ["/api_get","/api_post"]
        if _ask("Enable network? (y/N)", required=False, default="N").lower().startswith("y"):
            os.environ["QJSON_ALLOW_NET"] = "1"
    if use_db.lower().startswith("y"):
        allow += ["/sql_open","/sql_query","/sql_tables","/sql_close"]
    if use_adv.lower().startswith("y"):
        allow += ["/forge","/prism","/kg","/continuum","/meme"]
    os.environ["QJSON_PLUGIN_ALLOW"] = ",".join(allow)
    # Goal & loop settings
    goal = _ask("Goal", required=False, default="execute the task using selected tools")
    iters = _ask("Iterations", required=False, default="3")
    max_tokens = _ask("Max tokens per reply (optional)", required=False, default="")
    delay = _ask("Delay seconds", required=False, default="0.0")
    stop_token = _ask("Stop token (default 'need more info')", required=False, default="need more info")
    model = _select_from_list("Select model (optional)", _get_ollama_models(), allow_empty=True, default_idx=0)
    interactive = _ask("Continue interactively if agent asks for more info? (Y/n)", required=False, default="Y")
    # Launch semi mode
    argv = [
        "semi", "--id", agent_id,
        "--goal", goal,
        "--iterations", iters,
        "--delay", delay,
        "--stop-token", stop_token,
    ]
    if manifest:
        argv += ["--manifest", manifest]
    if model:
        argv += ["--model", model]
    if not interactive.strip().lower().startswith("n"):
        argv.append("--interactive")
    if max_tokens.strip():
        argv += ["--max-tokens", max_tokens.strip()]
    _execute_command(argv)


def run_menu() -> None:
    # Apply saved retrieval prefs to environment for child commands
    try:
        prefs = _load_prefs()
        _apply_retrieval_env_from_prefs(prefs)
        _apply_web_env_from_prefs(prefs)
        _apply_general_env_from_prefs(prefs)
    except Exception:
        pass
    while True:
        print(
            """
==== QJSON Agents Menu ====
1) Agent Management
2) Swarm & Cluster Management
3) YSON & Manifest Tools
4) System & Utilities
5) Plugins & Tools
6) Web & Crawl Settings
7) Exit
            """.strip()
        )
        sel = input("Select: ").strip()
        if sel == "1":
            _show_agent_menu()
        elif sel == "2":
            _show_swarm_menu()
        elif sel == "3":
            _show_yson_menu()
        elif sel == "4":
            _show_system_menu()
        elif sel == "5":
            _show_plugins_menu()
        elif sel == "6":
            _show_web_menu()
        elif sel == "7":
            print("Goodbye.")
            return
        else:
            print("Invalid selection.")


if __name__ == "__main__":
    # Allow running directly via `python menu.py`
    try:
        run_menu()
    except KeyboardInterrupt:
        print("\nExiting.")
