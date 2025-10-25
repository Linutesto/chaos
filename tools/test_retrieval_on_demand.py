import os, json, time
from pathlib import Path

os.environ.setdefault("QJSON_AGENTS_HOME", str(Path.cwd()/"state"))
os.environ.setdefault("QJSON_EMBED_MODE", "hash")

from qjson_agents.agent import Agent
from qjson_agents.memory import agent_dir
from qjson_agents.retrieval import add_memory


def load_agent(aid: str = "lila") -> Agent:
    adir = agent_dir(aid)
    mpath = adir/"manifest.json"
    if not mpath.exists():
        # Initialize from default manifest and fork
        mf = json.loads(Path("manifests/lila.json").read_text(encoding="utf-8"))
        base = Agent(mf)
        base.fork(aid, note="test fork")
    # Ensure runtime model is gpt-oss:20b for testing
    mf_obj = json.loads((agent_dir(aid)/"manifest.json").read_text(encoding="utf-8"))
    mf_obj.setdefault("runtime", {})["model"] = "gpt-oss:20b"
    ag = Agent(mf_obj)
    return ag


def tail_events(aid: str, n: int = 10):
    p = agent_dir(aid)/"events.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8", errors="ignore").splitlines() if x.strip()][-n:]


class _Mock:
    def chat(self, *, model, messages, options=None, stream=False):
        prev_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        return {"message": {"role": "assistant", "content": f"(gpt-oss:20b mock) {prev_user[:120]}"}}


def main():
    aid = "lila"
    ag = load_agent(aid)

    # Seed a unique fact
    add_memory(aid, "CONSENSUS=v2 uses fan-out quorum=3 ✅", {"source":"test"})

    # Arm one-shot retrieval
    os.environ["QJSON_RETRIEVAL_ONCE"] = "1"
    os.environ["QJSON_RETRIEVAL_TOPK"] = "5"
    os.environ["QJSON_RETRIEVAL_DECAY"] = "0.15"
    os.environ["QJSON_RETRIEVAL_MINSCORE"] = "0.25"
    os.environ["QJSON_RETRIEVAL_ACK"] = "1"

    r1 = ag.chat_turn("How does router v2 reach consensus?", client=_Mock(), model_override="gpt-oss:20b")
    print("reply1:", r1)
    evs = tail_events(aid, 5)
    inj = [e for e in evs if e.get("type")=="retrieval_inject"]
    print("inject_event_present:", bool(inj))

    # Min-score gate test: high threshold should block
    before = len([e for e in tail_events(aid, 1000) if e.get("type")=="retrieval_inject"])
    os.environ["QJSON_RETRIEVAL_MINSCORE"] = "0.60"
    os.environ["QJSON_RETRIEVAL_ONCE"] = "1"
    r2 = ag.chat_turn("weakly related: consensus thoughts?", client=_Mock(), model_override="gpt-oss:20b")
    after = len([e for e in tail_events(aid, 1000) if e.get("type")=="retrieval_inject"])
    print("gate_blocked:", after==before)

    # Restore threshold and ensure inject again
    os.environ["QJSON_RETRIEVAL_MINSCORE"] = "0.25"
    os.environ["QJSON_RETRIEVAL_ONCE"] = "1"
    r3 = ag.chat_turn("consensus mechanics again?", client=_Mock(), model_override="gpt-oss:20b")
    after2 = len([e for e in tail_events(aid, 1000) if e.get("type")=="retrieval_inject"])
    print("inject_after_restore:", after2>after)

    print("done")

if __name__ == "__main__":
    main()

