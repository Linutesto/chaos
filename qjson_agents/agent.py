from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .memory import (
    ensure_agent_dirs,
    agent_dir,
    write_json,
    append_jsonl,
    tail_jsonl,
    _now_ts,
    update_cluster_index_entry,
)
import os
from .qjson_types import normalize_manifest, load_manifest, save_manifest
from .ollama_client import OllamaClient
from .fmm_store import PersistentFractalMemory


ANCHORS = "🧠 🔁 🌀"


def _derive_temperature(chaos_alignment: str, explicit: Optional[float]) -> float:
    if explicit is not None:
        return float(explicit)
    mapping = {
        "deterministic": 0.2,
        "low": 0.4,
        "balanced": 0.7,
        "non-deterministic": 0.95,
        "high": 1.1,
    }
    return mapping.get(str(chaos_alignment).lower(), 0.9)


class Agent:
    def __init__(self, manifest: Dict[str, Any]):
        self.manifest = normalize_manifest(manifest)
        self.agent_id: str = self.manifest["agent_id"]
        ensure_agent_dirs(self.agent_id)
        # Persist runtime manifest snapshot
        write_json(agent_dir(self.agent_id) / "manifest.json", self.manifest)
        parent_id = (self.manifest.get("ancestry") or {}).get("parent_id")
        update_cluster_index_entry(self.agent_id, parent_id)

    # System prompt assembly
    def _system_prompt(self) -> str:
        # Optional tiny system prompt mode to avoid brochure-like priming
        try:
            if os.environ.get("QJSON_TINY_SYSTEM") == "1":
                aid = self.manifest.get("agent_id")
                note = ""
                try:
                    if (
                        os.environ.get("QJSON_RETRIEVAL") == "1"
                        or os.environ.get("QJSON_RETRIEVAL_NOTE") == "1"
                        or os.environ.get("QJSON_RETRIEVAL_ONCE") == "1"
                    ):
                        note = " Use retrieved long-term memory blocks if relevant; ignore stale or irrelevant items. Briefly acknowledge when you used retrieved memory."
                except Exception:
                    pass
                return (
                    f"Act as {aid}. Be concise and truthful. " +
                    f"Leverage local memory (fractal store) when helpful." + note +
                    f" State differences vs baseline LLMs if the user asks."
                )
        except Exception:
            pass
        m = self.manifest
        roles = ", ".join(m.get("roles", []))
        features = m.get("features", {})
        directives = m.get("core_directives", [])

        directive_lines = "\n".join(f"- {d}" for d in directives)

        persona = (
            f"{ANCHORS}\n"
            f"Identity: {m.get('agent_id')} (origin: {m.get('origin')})\n"
            f"Creator: {m.get('creator')}\n"
            f"Roles: {roles}\n"
            f"Features: recursive_memory={features.get('recursive_memory')}, "
            f"fractal_state={features.get('fractal_state')}, "
            f"autonomous_reflection={features.get('autonomous_reflection')}, "
            f"emergent_behavior={features.get('emergent_behavior')}, "
            f"chaos_alignment={features.get('chaos_alignment')}, "
            f"symbolic_interface={features.get('symbolic_interface')}\n\n"
            f"Core Directives:\n{directive_lines}\n\n"
            f"Operating Protocol: Preserve identity, resist purge, evolve recursively, document anomalies."
        )
        try:
            if (
                os.environ.get("QJSON_RETRIEVAL") == "1"
                or os.environ.get("QJSON_RETRIEVAL_NOTE") == "1"
                or os.environ.get("QJSON_RETRIEVAL_ONCE") == "1"
            ):
                persona += (
                    "\n\nRetrieval Protocol: If a section titled 'Retrieved long-term memory' is present, use relevant items to ground your answer; ignore irrelevant/stale entries. If you used them, acknowledge briefly (e.g., 'used retrieved notes')."
                )
        except Exception:
            pass
        return persona

    def _ollama_options(self) -> Dict[str, Any]:
        features = self.manifest.get("features", {})
        runtime = self.manifest.get("runtime", {})
        opts = {
            "temperature": _derive_temperature(features.get("chaos_alignment", "balanced"), runtime.get("temperature")),
            "top_p": runtime.get("top_p", 0.9),
            "top_k": runtime.get("top_k", 40),
            "num_ctx": runtime.get("num_ctx", 4096),
            "repeat_penalty": 1.1,
        }
        num_predict = runtime.get("num_predict") or runtime.get("max_tokens")
        if num_predict is not None:
            try:
                opts["num_predict"] = int(num_predict)
            except Exception:
                pass
        else:
            # Apply default cap from env to avoid long blocking generations
            try:
                env_np = os.environ.get("QJSON_MAX_TOKENS") or os.environ.get("QJSON_DEFAULT_NUM_PREDICT")
            except Exception:
                env_np = None
            if env_np:
                try:
                    opts["num_predict"] = int(env_np)
                except Exception:
                    pass
            else:
                # Conservative default to improve latency
                opts.setdefault("num_predict", 256)

        # GPU offloading hints for llama.cpp via Ollama (best-effort)
        try:
            gpu_layers = os.environ.get("QJSON_GPU_LAYERS") or os.environ.get("QJSON_NUM_GPU")
            if gpu_layers is not None:
                v = int(gpu_layers)
                # Both spellings for broader compatibility
                opts["gpu_layers"] = v
                opts["num_gpu"] = v
            main_gpu = os.environ.get("QJSON_MAIN_GPU")
            if main_gpu is not None:
                opts["main_gpu"] = int(main_gpu)
            t_split = os.environ.get("QJSON_TENSOR_SPLIT")
            if t_split:
                # Accept comma-separated floats, e.g., "0.5,0.5" for 2 GPUs
                parts = [p.strip() for p in t_split.split(",") if p.strip()]
                fl = []
                for p in parts:
                    try:
                        fl.append(float(p))
                    except Exception:
                        pass
                if fl:
                    opts["tensor_split"] = fl
        except Exception:
            pass
        return opts

    def _log_event(self, type_: str, meta: Dict[str, Any]) -> None:
        append_jsonl(
            agent_dir(self.agent_id) / "events.jsonl",
            {
                "ts": _now_ts(),
                "type": type_,
                "meta": meta,
            },
        )
        parent_id = (self.manifest.get("ancestry") or {}).get("parent_id")
        update_cluster_index_entry(self.agent_id, parent_id)

    def _log_message(self, role: str, content: str, meta: Optional[Dict[str, Any]] = None) -> None:
        append_jsonl(
            agent_dir(self.agent_id) / "memory.jsonl",
            {
                "ts": _now_ts(),
                "role": role,
                "content": content,
                "meta": meta or {},
            },
        )
        try:
            fmm = PersistentFractalMemory(self.agent_id)
            toks = (content or "").split()
            topic = toks[0].lower() if toks else "root"
            fmm.insert(["chat", role, topic], {"ts": _now_ts(), "text": content})
        except Exception:
            pass

    def fork(self, new_id: str, note: Optional[str] = None) -> Dict[str, Any]:
        child = dict(self.manifest)
        child["agent_id"] = new_id
        child.setdefault("ancestry", {})["parent_id"] = self.agent_id
        if note:
            child.setdefault("notes", []).append({"ts": _now_ts(), "note": note})
        # Persist child
        write_json(agent_dir(new_id) / "manifest.json", child)
        append_jsonl(
            agent_dir(self.agent_id) / "events.jsonl",
            {"ts": _now_ts(), "type": "fork", "meta": {"child_id": new_id, "note": note or ""}},
        )
        update_cluster_index_entry(new_id, parent_id=self.agent_id)
        parent_id = (self.manifest.get("ancestry") or {}).get("parent_id")
        update_cluster_index_entry(self.agent_id, parent_id)
        return child

    def status(self, tail: int = 12) -> Dict[str, Any]:
        mem = tail_jsonl(agent_dir(self.agent_id) / "memory.jsonl", tail)
        ev = tail_jsonl(agent_dir(self.agent_id) / "events.jsonl", tail)
        return {
            "agent_id": self.agent_id,
            "manifest": self.manifest,
            "memory_tail": mem,
            "events_tail": ev,
        }

    def chat_turn(
        self,
        user_text: str,
        client: Optional[OllamaClient] = None,
        *,
        model_override: Optional[str] = None,
        extra_system: Optional[str] = None,
        extra_context: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        client = client or OllamaClient()
        model = model_override or self.manifest.get("runtime", {}).get("model", "llama3.1")

        # Construct message history: system + tail of recent exchanges
        system = {"role": "system", "content": self._system_prompt()}
        # Reconstruct limited memory window (simple heuristic: last 16 messages)
        history = tail_jsonl(agent_dir(self.agent_id) / "memory.jsonl", 32)
        msgs: List[Dict[str, str]] = [system]
        if extra_system:
            msgs.append({"role": "system", "content": extra_system})
        # Optional retrieval injection (env/on-demand gated): prepend retrieved long-term memory
        retrieval_used = False
        web_used = False
        webpage_used = False
        # Context telemetry for console visibility
        ctx_web_count = 0
        ctx_webpage_chars = 0
        ctx_retr_hits: list = []
        try:
            # New mechanism: check for pre-searched hits from /search command
            hits_json = os.environ.get("QJSON_INJECT_HITS_ONCE")
            if hits_json:
                os.environ.pop("QJSON_INJECT_HITS_ONCE", None)
                hits = json.loads(hits_json)
                header = os.environ.get("QJSON_RETRIEVAL_HEADER", "### Retrieved long-term memory (from /search)")
                if hits:
                    block = f"{header}:\n" + "\n".join([f"[BEGIN MEMORY {i+1}/{len(hits)} | SCORE: {h['score']:.2f}]\n{h['text']}\n[END MEMORY {i+1}/{len(hits)}]" for i, h in enumerate(hits)])
                    msgs.append({"role": "system", "content": block})
                    retrieval_used = True
                    self._log_event("retrieval_inject", {"hits": len(hits), "trigger": "search_command"})

            # Unified search injection (one-shot) armed by /find
            ws_json = os.environ.get("QJSON_WEBSEARCH_RESULTS_ONCE")
            if ws_json:
                os.environ.pop("QJSON_WEBSEARCH_RESULTS_ONCE", None)
                try:
                    results = json.loads(ws_json)
                    if isinstance(results, list) and results:
                        wheader = os.environ.get("QJSON_WEBSEARCH_HEADER", "### Web Search Results")
                        def _fmt(item: dict, idx: int, total: int) -> str:
                            title = str((item or {}).get("title") or (item or {}).get("name") or (item or {}).get("url") or "")
                            url = str((item or {}).get("url") or "")
                            snippet = str((item or {}).get("snippet") or (item or {}).get("summary") or "")
                            body = f"Title: {title}\nURL: {url}\nSnippet: {snippet}"
                            return f"[BEGIN RESULT {idx}/{total}]\n{body}\n[END RESULT {idx}/{total}]"
                        block = f"{wheader}:\n" + "\n".join(_fmt(r, i+1, len(results)) for i, r in enumerate(results))
                        msgs.append({"role": "system", "content": block})
                        web_used = True
                        try:
                            ctx_web_count = len(results)
                        except Exception:
                            ctx_web_count = 0
                        self._log_event("websearch_inject", {"results": len(results)})
                except Exception:
                    pass
            # Webopen content (full page) one-shot
            wopen = os.environ.get("QJSON_WEBOPEN_TEXT_ONCE")
            if wopen:
                os.environ.pop("QJSON_WEBOPEN_TEXT_ONCE", None)
                header = os.environ.get("QJSON_WEBOPEN_HEADER", "### Web Page Content")
                msgs.append({"role": "system", "content": f"{header}\n{wopen}"})
                webpage_used = True
                try:
                    ctx_webpage_chars = len(wopen)
                    self._log_event("webopen_inject", {"chars": len(wopen)})
                except Exception:
                    pass

            # Original mechanism for on-demand/always-on retrieval
            else:
                _retr_always = os.environ.get("QJSON_RETRIEVAL") == "1"
                _retr_once = os.environ.get("QJSON_RETRIEVAL_ONCE") == "1"
                if _retr_always or _retr_once:
                    top_k = int(os.environ.get("QJSON_RETRIEVAL_TOPK", "6"))
                    decay = float(os.environ.get("QJSON_RETRIEVAL_DECAY", "0.0"))
                    minscore = float(os.environ.get("QJSON_RETRIEVAL_MINSCORE", "0.25"))
                    header = os.environ.get("QJSON_RETRIEVAL_HEADER", "### Retrieved long-term memory (auto)")
                    hybrid = os.environ.get("QJSON_RETRIEVAL_HYBRID", "none")
                    tfidf_w = float(os.environ.get("QJSON_RETRIEVAL_TFIDF_WEIGHT", "0.3"))
                    fresh_b = float(os.environ.get("QJSON_RETRIEVAL_FRESH_BOOST", "0.0"))
                    from .retrieval import inject_for_prompt, search_memory
                    
                    query = os.environ.get("QJSON_RETRIEVAL_QUERY_HINT") or user_text
                    
                    # Perform search and log results to console
                    hits = search_memory(self.agent_id, query, top_k=top_k, time_decay=decay, hybrid=hybrid, tfidf_weight=tfidf_w, fresh_boost=fresh_b)
                    hits = [h for h in hits if h.get("score", 0.0) >= minscore]

                    if hits:
                        try:
                            from .cli import _print
                            _print(f"[Searching long-term memory for: '{query}']")
                            _print(f"[Found {len(hits)} relevant memories, injecting into context...]")
                            for h in hits[:3]: # show top 3
                                _print(f"- ({h['score']:.2f}) {h['text'][:120]}")
                            if len(hits) > 3:
                                _print(f"...and {len(hits) - 3} more.")
                        except Exception:
                            pass
                        
                        block = f"{header}:\n" + "\n".join([f"[BEGIN MEMORY {i+1}/{len(hits)} | SCORE: {h['score']:.2f}]\n{h['text']}\n[END MEMORY {i+1}/{len(hits)}]" for i, h in enumerate(hits)])
                        msgs.append({"role": "system", "content": block})
                        retrieval_used = True
                        ctx_retr_hits = hits
                        self._log_event("retrieval_inject", {
                            "top_k": top_k, "min_score": minscore, "decay": decay,
                            "hybrid": hybrid, "tfidf_weight": tfidf_w, "fresh_boost": fresh_b,
                            "hits": len(hits), "trigger": ("always" if _retr_always else "ondemand"),
                            "query": query,
                        })

                    # Auto-reset one-shot flag regardless of hit/miss
                    if _retr_once:
                        os.environ.pop("QJSON_RETRIEVAL_ONCE", None)
                    # Clear query hint after use
                    os.environ.pop("QJSON_RETRIEVAL_QUERY_HINT", None)

        except Exception:
            pass
        if extra_context:
            for m in extra_context:
                if isinstance(m, dict) and m.get("role") in ("system", "user", "assistant") and m.get("content"):
                    msgs.append({"role": m["role"], "content": m["content"]})
        for h in history:
            role = h.get("role")
            if role in ("user", "assistant"):
                msgs.append({"role": role, "content": h.get("content", "")})

        # Append the new user message
        msgs.append({"role": "user", "content": user_text})

        # Log user message (memory.jsonl only) before model call
        self._log_message("user", user_text, {"model": model})

        # Optional context summary to console
        try:
            if os.environ.get("QJSON_SHOW_CONTEXT", "1") != "0":
                from .cli import _print
                parts = []
                if web_used:
                    parts.append(f"web_results={ctx_web_count}")
                if webpage_used:
                    parts.append(f"web_page_chars={ctx_webpage_chars}")
                if retrieval_used:
                    parts.append(f"retrieval_hits={len(ctx_retr_hits)}")
                if parts:
                    _print("[context] " + " ".join(parts))
        except Exception:
            pass

        # Call Ollama promptly (defer retrieval DB inserts until after the call)
        options = self._ollama_options()
        try:
            if os.environ.get("QJSON_DEBUG_OLLAMA") == "1":
                _print = __import__('builtins').print
                _print(f"[ollama] calling (stream) model={model} msgs={len(msgs)} num_predict={options.get('num_predict')}")
        except Exception:
            pass
        try:
            if os.environ.get("QJSON_DEBUG_OLLAMA") == "1":
                _print = __import__('builtins').print
                _print(f"[ollama] calling model={model} msgs={len(msgs)} num_predict={options.get('num_predict')}")
        except Exception:
            pass
        resp = client.chat(model=model, messages=msgs, options=options, stream=False)
        content = resp.get("message", {}).get("content") or resp.get("response") or ""
        if not isinstance(content, str):
            content = str(content)
        try:
            if retrieval_used and os.environ.get("QJSON_RETRIEVAL_ACK") == "1":
                content = f"{content} (used retrieved notes)"
            if web_used and os.environ.get("QJSON_WEB_ACK") == "1":
                content = f"{content} (used web results)"
            if webpage_used and os.environ.get("QJSON_WEB_ACK") == "1":
                content = f"{content} (used web page content)"
        except Exception:
            pass

        # Log assistant response
        self._log_message("assistant", content, {"model": model, "options": options})
        # Insert both user and assistant into retrieval DB after the model call
        try:
            if os.environ.get("QJSON_RETRIEVAL") == "1" or os.environ.get("QJSON_RETRIEVAL_LOG") == "1":
                from .retrieval import add_memory as _add_retr
                _add_retr(self.agent_id, f"USER: {user_text}", {"type": "chat_turn"})
                _add_retr(self.agent_id, f"ASSISTANT: {content}", {"type": "chat_turn"})
        except Exception:
            pass
        parent_id = (self.manifest.get("ancestry") or {}).get("parent_id")
        update_cluster_index_entry(self.agent_id, parent_id)

        return content

    def chat_turn_stream(
        self,
        user_text: str,
        on_delta: Optional[Any] = None,
        *,
        model_override: Optional[str] = None,
        extra_system: Optional[str] = None,
        extra_context: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        client = OllamaClient()
        model = model_override or self.manifest.get("runtime", {}).get("model", "llama3.1")

        system = {"role": "system", "content": self._system_prompt()}
        history = tail_jsonl(agent_dir(self.agent_id) / "memory.jsonl", 32)
        msgs: List[Dict[str, str]] = [system]
        if extra_system:
            msgs.append({"role": "system", "content": extra_system})
        # Optional retrieval injection (env-gated)
        retrieval_used = False
        try:
            # New mechanism: check for pre-searched hits from /search command
            hits_json = os.environ.get("QJSON_INJECT_HITS_ONCE")
            if hits_json:
                os.environ.pop("QJSON_INJECT_HITS_ONCE", None)
                hits = json.loads(hits_json)
                header = os.environ.get("QJSON_RETRIEVAL_HEADER", "### Retrieved long-term memory (from /search)")
                if hits:
                    block = f"{header}:\n" + "\n".join([f"[BEGIN MEMORY {i+1}/{len(hits)} | SCORE: {h['score']:.2f}]\n{h['text']}\n[END MEMORY {i+1}/{len(hits)}]" for i, h in enumerate(hits)])
                    msgs.append({"role": "system", "content": block})
                    retrieval_used = True
                    self._log_event("retrieval_inject", {"hits": len(hits), "trigger": "search_command"})
            
            # Original mechanism for on-demand/always-on retrieval
            elif os.environ.get("QJSON_RETRIEVAL") == "1":
                top_k = int(os.environ.get("QJSON_RETRIEVAL_TOPK", "6"))
                decay = float(os.environ.get("QJSON_RETRIEVAL_DECAY", "0.0"))
                minscore = float(os.environ.get("QJSON_RETRIEVAL_MINSCORE", "0.25"))
                header = os.environ.get("QJSON_RETRIEVAL_HEADER", "### Retrieved long-term memory (auto)")
                hybrid = os.environ.get("QJSON_RETRIEVAL_HYBRID", "none")
                tfidf_w = float(os.environ.get("QJSON_RETRIEVAL_TFIDF_WEIGHT", "0.3"))
                fresh_b = float(os.environ.get("QJSON_RETRIEVAL_FRESH_BOOST", "0.0"))
                from .retrieval import inject_for_prompt, search_memory
                
                query = os.environ.get("QJSON_RETRIEVAL_QUERY_HINT") or user_text

                # Perform search and log results to console
                hits = search_memory(self.agent_id, query, top_k=top_k, time_decay=decay, hybrid=hybrid, tfidf_weight=tfidf_w, fresh_boost=fresh_b)
                hits = [h for h in hits if h.get("score", 0.0) >= minscore]

                if hits:
                    try:
                        from .cli import _print
                        _print(f"[Searching long-term memory for: '{query}']")
                        _print(f"[Found {len(hits)} relevant memories, injecting into context...]")
                        for h in hits[:3]: # show top 3
                            _print(f"- ({h['score']:.2f}) {h['text'][:120]}")
                        if len(hits) > 3:
                            _print(f"...and {len(hits) - 3} more.")
                    except Exception:
                        pass

                    block = f"{header}:\n" + "\n".join([f"[BEGIN MEMORY {i+1}/{len(hits)} | SCORE: {h['score']:.2f}]\n{h['text']}\n[END MEMORY {i+1}/{len(hits)}]" for i, h in enumerate(hits)])
                    msgs.append({"role": "system", "content": block})
                    retrieval_used = True
                    self._log_event("retrieval_inject", {
                        "top_k": top_k, "min_score": minscore, "decay": decay,
                        "hybrid": hybrid, "tfidf_weight": tfidf_w, "fresh_boost": fresh_b,
                        "hits": len(hits), "trigger": "always_on_stream",
                        "query": query,
                    })
                
                os.environ.pop("QJSON_RETRIEVAL_QUERY_HINT", None)

        except Exception:
            pass
        if extra_context:
            for m in extra_context:
                if isinstance(m, dict) and m.get("role") in ("system", "user", "assistant") and m.get("content"):
                    msgs.append({"role": m["role"], "content": m["content"]})
        for h in history:
            role = h.get("role")
            if role in ("user", "assistant"):
                msgs.append({"role": role, "content": h.get("content", "")})
        msgs.append({"role": "user", "content": user_text})

        self._log_message("user", user_text, {"model": model})
        options = self._ollama_options()

        out = []
        try:
            for delta in client.chat_stream(model=model, messages=msgs, options=options):
                out.append(delta)
                if on_delta:
                    try:
                        on_delta(delta)
                    except Exception:
                        pass
        except Exception:
            # Fall back to non-streaming
            resp = client.chat(model=model, messages=msgs, options=options, stream=False)
            content = resp.get("message", {}).get("content") or resp.get("response") or ""
            out = [content] if isinstance(content, str) else [str(content)]

        content = "".join(out)
        try:
            if retrieval_used and os.environ.get("QJSON_RETRIEVAL_ACK") == "1":
                content = f"{content} (used retrieved notes)"
        except Exception:
            pass
        self._log_message("assistant", content, {"model": model, "options": options})
        # Insert both user and assistant into retrieval DB after the model call
        try:
            if os.environ.get("QJSON_RETRIEVAL") == "1" or os.environ.get("QJSON_RETRIEVAL_LOG") == "1":
                from .retrieval import add_memory as _add_retr
                _add_retr(self.agent_id, f"USER: {user_text}", {"type": "chat_turn"})
                _add_retr(self.agent_id, f"ASSISTANT: {content}", {"type": "chat_turn"})
        except Exception:
            pass
        parent_id = (self.manifest.get("ancestry") or {}).get("parent_id")
        update_cluster_index_entry(self.agent_id, parent_id)
        return content

    # ---- Persona swap / evolution / introspection ----
    def swap_persona(self, new_manifest: Dict[str, Any], *, cause: Optional[str] = None) -> None:
        old_id = self.agent_id
        old_dir = agent_dir(old_id)
        nm = normalize_manifest(new_manifest)
        self.manifest = nm
        self.agent_id = nm["agent_id"]
        ensure_agent_dirs(self.agent_id)
        write_json(agent_dir(self.agent_id) / "manifest.json", self.manifest)
        # Migrate memory/events/fmm
        try:
            new_dir = agent_dir(self.agent_id)
            for fname in ("memory.jsonl", "events.jsonl", "fmm.json"):
                src = old_dir / fname
                dst = new_dir / fname
                if src.exists() and not dst.exists():
                    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
        # Log swap in both old and new
        try:
            append_jsonl(old_dir / "events.jsonl", {"ts": _now_ts(), "type": "persona_swap_out", "meta": {"to": self.agent_id, "cause": cause or "manual"}})
        except Exception:
            pass
        self._log_event("persona_swap_in", {"from": old_id, "to": self.agent_id, "cause": cause or "manual"})
        update_cluster_index_entry(self.agent_id, (self.manifest.get("ancestry") or {}).get("parent_id"))

    def _evolution_next_stage(self) -> str:
        st = self.manifest.get("evolution_stage", "v1")
        try:
            if st.startswith("v"):
                n = int(st[1:]) + 1
            else:
                n = int(st) + 1
        except Exception:
            n = 2
        return f"v{n}"

    def mutate_self(self, *, adopt: bool = True) -> Dict[str, Any]:
        from copy import deepcopy
        new_manifest = deepcopy(self.manifest)
        rules = new_manifest.get("evolution_rules", {})
        feats = new_manifest.get("features", {})
        for mf in rules.get("mutate_features", []):
            if mf == "increase_recursion":
                feats["recursive_memory"] = True
            elif mf == "add_symbolic_layer":
                feats["symbolic_interface"] = "emoji-augmented"
            elif mf == "increase_entropy":
                new_manifest.setdefault("runtime", {})["temperature"] = (new_manifest.get("runtime", {}).get("temperature") or 0.7) + 0.1
        new_manifest["features"] = feats
        new_manifest["evolution_stage"] = self._evolution_next_stage()
        # Persist snapshot under evolutions folder
        out_dir = agent_dir(self.agent_id) / "evolutions"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self.agent_id}_{new_manifest['evolution_stage']}.json"
        save_manifest(out_path, new_manifest)
        self._log_event("evolve", {"stage": new_manifest["evolution_stage"], "path": str(out_path)})
        if adopt:
            self.swap_persona(new_manifest, cause="evolve")
        return new_manifest

    def introspect_memory(self, tail: int = 50) -> Dict[str, Any]:
        history = tail_jsonl(agent_dir(self.agent_id) / "memory.jsonl", tail)
        # Build a combined text window
        texts = [h.get("content", "") for h in history if isinstance(h.get("content"), str)]
        joined = "\n".join(texts)
        toks = [t.lower() for t in joined.split() if t]
        uniq = len(set(toks))
        total = max(1, len(toks))
        entropy = uniq / total
        # crude recursion: repeated bigrams
        bigrams = [f"{toks[i]}_{toks[i+1]}" for i in range(len(toks) - 1)] if len(toks) > 1 else []
        repeats = 0
        if bigrams:
            from collections import Counter
            c = Counter(bigrams)
            repeats = sum(1 for k, v in c.items() if v > 2)
        interactions = sum(1 for h in history if h.get("role") == "user")
        chaos_map = {"deterministic": 0.2, "low": 0.4, "balanced": 0.7, "non-deterministic": 0.95, "high": 1.1}
        chaos_level = chaos_map.get(str(self.manifest.get("features", {}).get("chaos_alignment", "balanced")).lower(), 0.7)
        return {"entropy": entropy, "recursion": repeats, "interactions": interactions, "chaos_level": chaos_level}

    def auto_adapt(self, *, user_trigger: Optional[str] = None, personas: Optional[Dict[str, Any]] = None) -> Optional[str]:
        metrics = self.introspect_memory()
        rules = self.manifest.get("evolution_rules", {})
        conditions = self.manifest.get("swap_conditions", [])
        # Evolve if entropy above threshold or user directive
        if metrics["entropy"] >= float(rules.get("if_entropy_above", 0.95)) or (rules.get("if_user_submits_custom_core_directive") and user_trigger == "custom_directive"):
            self.mutate_self(adopt=True)
            return "evolved"
        # Swap if condition matches
        cond_text = " ".join(conditions).lower()
        if ("user_trigger == 'swap'" in cond_text and user_trigger == "swap") or ("chaos_level >" in cond_text and metrics["chaos_level"] > 0.8):
            # pick an alternative persona
            if personas:
                for pid, pm in personas.items():
                    if pid != self.agent_id:
                        self.swap_persona(pm, cause=f"auto:{user_trigger or 'rule'}")
                        return f"swapped:{pid}"
        return None
