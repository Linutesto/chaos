import os
import sys
import subprocess
from pathlib import Path


def run_cli(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run([sys.executable, "-m", "qjson_agents.cli"] + args, capture_output=True, text=True, env=e)


def test_semi_prerun_and_actions(tmp_path: Path):
    # Create a safe FS root with a file to read
    root = tmp_path / "root"
    root.mkdir()
    f = root / "README.md"
    f.write_text("hello world from semi", encoding="utf-8")

    goal = f"/fs_list {root} then /fs_read {f}"
    args = [
        "semi",
        "--id",
        "SemiTest",
        "--model",
        "mock-llm",
        "--iterations",
        "1",
        "--plugins",
        "/fs_list,/fs_read",
        "--fs-roots",
        str(root),
        "--goal",
        goal,
    ]
    r = run_cli(args)
    assert r.returncode == 0
    out = r.stdout
    # Pre-run should execute both commands and print [tool:pre]
    assert "[tool:pre] /fs_list" in out
    assert "[tool:pre] /fs_read" in out
    # Tick should run and complete
    assert "[semi] complete." in out


def test_semi_early_stop_on_task_complete(tmp_path: Path):
    # If goal includes 'task complete', mock reply echoes it -> early stop
    root = tmp_path / "root2"
    root.mkdir()
    args = [
        "semi",
        "--id",
        "SemiStop",
        "--model",
        "mock-llm",
        "--iterations",
        "3",
        "--plugins",
        "/fs_list",
        "--fs-roots",
        str(root),
        "--goal",
        "analyze repo and then task complete",
    ]
    r = run_cli(args)
    assert r.returncode == 0
    out = r.stdout
    assert "[semi] stop: agent marked task complete." in out

