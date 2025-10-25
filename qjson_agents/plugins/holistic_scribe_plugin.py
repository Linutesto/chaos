from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List

from qjson_agents.plugin_manager import Plugin


class HolisticScribePlugin(Plugin):
    """Maintain a lightweight knowledge graph in Fractal Memory.

    Usage:
      /kg add_node id=<ID> label=<LABEL> [tags=a,b] [data='{"k":"v"}']
      /kg add_edge src=<ID> dst=<ID> type=<TYPE> [weight=1.0] [data='{}']
      /kg stats
      /kg export mermaid <PATH>
    """

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {"/kg": self.kg}

    def kg(self, *parts: str) -> str:
        if not parts:
            return "Usage: /kg add_node ... | add_edge ... | stats | export mermaid <PATH>"
        sub = parts[0].lower()
        agent_id = os.environ.get("QJSON_AGENT_ID") or "KG"
        try:
            from qjson_agents.fmm_store import PersistentFractalMemory
            fmm = PersistentFractalMemory(agent_id)
        except Exception:
            fmm = None  # type: ignore

        if sub == "add_node":
            kv = self._kv(parts[1:])
            nid = kv.get("id"); label = kv.get("label")
            if not nid:
                return "[kg] id=<ID> is required"
            tags = [s.strip() for s in (kv.get("tags","" ).split(",") if kv.get("tags") else []) if s.strip()]
            data = self._json_or_none(kv.get("data")) or {}
            rec = {"id": nid, "label": label or nid, "tags": tags, "data": data}
            if fmm:
                fmm.insert(["kg","nodes"], rec)
                fmm.persist()
            return f"[kg] node added: {nid}"
        if sub == "add_edge":
            kv = self._kv(parts[1:])
            src = kv.get("src"); dst = kv.get("dst"); et = kv.get("type") or "related"
            if not src or not dst:
                return "[kg] src=<ID> and dst=<ID> required"
            try:
                w = float(kv.get("weight","1.0"))
            except Exception:
                w = 1.0
            data = self._json_or_none(kv.get("data")) or {}
            rec = {"src": src, "dst": dst, "type": et, "weight": w, "data": data}
            if fmm:
                fmm.insert(["kg","edges"], rec)
                fmm.persist()
            return f"[kg] edge added: {src} -[{et}:{w}]-> {dst}"
        if sub == "stats":
            nodes = edges = 0
            try:
                nodes = len((fmm.tree.get("kg",{}).get("nodes",{}).get("__data__",[])))  # type: ignore
                edges = len((fmm.tree.get("kg",{}).get("edges",{}).get("__data__",[])))  # type: ignore
            except Exception:
                pass
            return f"[kg] nodes={nodes} edges={edges}"
        if sub == "export" and len(parts) >= 3 and parts[1].lower() == "mermaid":
            outp = parts[2]
            lines: List[str] = ["graph TD"]
            try:
                nodes = (fmm.tree.get("kg",{}).get("nodes",{}).get("__data__",[]))  # type: ignore
                edges = (fmm.tree.get("kg",{}).get("edges",{}).get("__data__",[]))  # type: ignore
            except Exception:
                nodes = []; edges = []
            for n in nodes:
                nid = n.get("id")
                label = (n.get("label") or nid or "").replace("\"","'")
                if nid:
                    lines.append(f"  {nid}[\"{label}\"]")
            for e in edges:
                s = e.get("src"); d = e.get("dst"); t = e.get("type") or "rel"
                if s and d:
                    lines.append(f"  {s} -- {t} --> {d}")
            try:
                Path(outp).write_text("\n".join(lines), encoding="utf-8")
                return f"[kg] mermaid graph written -> {outp}"
            except Exception as e:
                return f"[kg] export error: {e}"
        return "[kg] unknown subcommand"

    def _kv(self, parts: List[str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def _json_or_none(self, s: str | None) -> Dict[str, Any] | None:
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None

