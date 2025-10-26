#!/usr/bin/env python3
import os
import sys
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / ("Scripts\\python.exe" if os.name == "nt" else "bin/python")


def sh(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy(); e.update(env or {})
    return subprocess.run(cmd, capture_output=True, text=True, env=e)


def run_exec(command: str, agent_id: str = "AdvDemo", env: dict | None = None) -> subprocess.CompletedProcess:
    return sh([str(VENV_PY), "-m", "qjson_agents.cli", "exec", command, "--id", agent_id], env)


def assert_ok(cond: bool, ctx: str, out: str = "") -> None:
    if not cond:
        print(f"[FAIL] {ctx}\n---\n{out}\n---")
        raise SystemExit(1)


def main() -> None:
    # Ensure venv and install package locally without deps
    if not VENV_PY.exists():
        r = sh([sys.executable, "-m", "venv", "--system-site-packages", ".venv"])
        assert_ok(r.returncode == 0, "create venv", r.stderr)
    # Skip installation: run module from source; CWD is project root

    # 1) Swarm-Forge: create a child agent and print info
    r = run_exec("/forge create Child role=analyst model=mock-llm goal=analyze-logs plugins=filesystem_plugin,git_plugin")
    assert_ok(r.returncode == 0 and "created agent 'Child'" in r.stdout, "forge create", r.stdout)
    r = run_exec("/forge info Child")
    assert_ok(r.returncode == 0, "forge info", r.stdout)
    info = json.loads(r.stdout)
    assert_ok(info.get("agent_id") == "Child", "forge info parse", r.stdout)

    # 2) Cognitive-Prism: multi-perspective plan
    r = run_exec("/prism Is the feature set stable? hats=optimist,pessimist")
    assert_ok("Cognitive Prism" in r.stdout, "prism header", r.stdout)

    # 3) Meme-Weaver: analyze + generate text
    r = run_exec("/meme analyze open source agents")
    assert_ok(r.returncode == 0, "meme analyze", r.stdout)
    _ = json.loads(r.stdout)
    r = run_exec("/meme generate text open source agents style=humor format=tweet")
    assert_ok("open source agents" in r.stdout, "meme text", r.stdout)

    # 4) Holistic-Scribe: KG operations
    r = run_exec("/kg add_node id=A label=Alpha tags=a,b")
    assert_ok("node added" in r.stdout, "kg add_node A", r.stdout)
    r = run_exec("/kg add_node id=B label=Beta")
    assert_ok("node added" in r.stdout, "kg add_node B", r.stdout)
    r = run_exec("/kg add_edge src=A dst=B type=rel weight=0.8")
    assert_ok("edge added" in r.stdout, "kg add_edge", r.stdout)
    r = run_exec("/kg stats")
    assert_ok("nodes=" in r.stdout and "edges=" in r.stdout, "kg stats", r.stdout)

    # 5) Continuum: export current agent bundle then import into a new id
    tmp = ROOT / "tmp_adv"
    tmp.mkdir(exist_ok=True)
    r = run_exec(f"/continuum export AdvDemo path={tmp}")
    assert_ok("exported" in r.stdout, "continuum export", r.stdout)
    tar = None
    for line in r.stdout.splitlines():
        if "exported ->" in line:
            tar = line.split("exported ->",1)[1].strip()
    assert_ok(tar is not None and Path(tar).exists(), "tar exists", r.stdout)
    r = run_exec(f"/continuum import {tar} new_id=AdvImported")
    assert_ok("imported" in r.stdout, "continuum import", r.stdout)

    print("[OK] advanced plugin smoke tests passed (venv)")


if __name__ == "__main__":
    main()
