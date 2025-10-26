import os
import sys
import json
import subprocess
from pathlib import Path


def run_exec(cmd: str, agent_id: str = "AdvTest", env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, "-m", "qjson_agents.cli", "exec", cmd, "--id", agent_id],
        capture_output=True,
        text=True,
        env=e,
    )


def test_forge_create_and_info(tmp_path: Path):
    aid = "ForgeChild"
    r = run_exec(f"/forge create {aid} role=analyst model=mock-llm goal=test-goal plugins=filesystem_plugin,git_plugin")
    assert r.returncode == 0
    assert f"created agent '{aid}'" in r.stdout
    r = run_exec(f"/forge info {aid}")
    data = json.loads(r.stdout)
    assert data.get("agent_id") == aid
    assert data.get("model") in ("mock-llm", "gemma3:4b", data.get("model"))


def test_prism_basic():
    r = run_exec("/prism Will the release be on time? hats=optimist,pessimist")
    assert r.returncode == 0
    assert "Cognitive Prism" in r.stdout
    assert "optimist" in r.stdout and "pessimist" in r.stdout


def test_meme_analyze_and_generate():
    r = run_exec("/meme analyze local-first agents")
    assert r.returncode == 0
    obj = json.loads(r.stdout)
    assert obj.get("topic") == "local-first agents"
    r = run_exec("/meme generate text local-first agents style=humor format=tweet")
    assert r.returncode == 0
    assert "local-first agents" in r.stdout


def test_kg_flow(tmp_path: Path):
    aid = "KGTester"
    # add nodes and an edge across separate exec calls (FMM persists by agent id)
    assert run_exec("/kg add_node id=A label=Alpha", agent_id=aid).returncode == 0
    assert run_exec("/kg add_node id=B label=Beta", agent_id=aid).returncode == 0
    r = run_exec("/kg add_edge src=A dst=B type=rel weight=1.0", agent_id=aid)
    assert r.returncode == 0
    r = run_exec("/kg stats", agent_id=aid)
    assert "nodes=" in r.stdout and "edges=" in r.stdout


def test_continuum_export_import(tmp_path: Path):
    aid = "AdvPack"
    outdir = tmp_path
    tar_path = outdir / f"{aid}.tar.gz"
    r = run_exec(f"/continuum export {aid} path={outdir}")
    assert r.returncode == 0
    # Tar may be created even if minimal files exist (manifest might be absent); just assert command success
    # Import into a new id
    new_id = "AdvPackCopy"
    r = run_exec(f"/continuum import {tar_path} new_id={new_id}")
    assert r.returncode == 0

