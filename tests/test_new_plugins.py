import os
import sys
import json
import sqlite3
import subprocess
from pathlib import Path


def run_exec(cmd: str, env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, "-m", "qjson_agents.cli", "exec", cmd, "--id", "TestAgent"],
        capture_output=True,
        text=True,
        env=e,
    )


def test_fs_plugin_list_read_write(tmp_path: Path):
    base = tmp_path / "fsroot"
    base.mkdir()
    f1 = base / "a.txt"
    f1.write_text("hello", encoding="utf-8")
    env = {"QJSON_FS_ROOTS": str(base)}

    # list
    r = run_exec(f"/fs_list {base} glob=*.txt max=10", env=env)
    assert r.returncode == 0
    assert "a.txt" in r.stdout

    # read
    r = run_exec(f"/fs_read {f1} max_bytes=100", env=env)
    assert "[fs] read" in r.stdout
    assert "hello" in r.stdout

    # write gated
    r = run_exec(f"/fs_write {base/'b.txt'} hi", env=env)
    assert "writes disabled" in r.stdout
    env_w = env | {"QJSON_FS_WRITE": "1"}
    r = run_exec(f"/fs_write {base/'b.txt'} hi", env=env_w)
    assert "wrote" in r.stdout
    assert (base / "b.txt").read_text(encoding="utf-8").startswith("hi")


def test_exec_plugin_gating(tmp_path: Path):
    # Disabled by default
    r = run_exec("/py print(1+2)")
    assert "disabled" in r.stdout
    # Enabled
    r = run_exec("/py print(1+2)", env={"QJSON_ALLOW_EXEC": "1", "QJSON_EXEC_TIMEOUT": "3"})
    assert r.returncode == 0
    assert "[py] exit=0" in r.stdout
    assert "3" in r.stdout


def test_sqlite_plugin(tmp_path: Path):
    # Use the plugin in-process so connection state is preserved
    import importlib.util as _ilu
    p = Path("qjson_agents/plugins/db_plugin.py").resolve()
    spec = _ilu.spec_from_file_location("db_plugin", str(p))
    mod = _ilu.module_from_spec(spec)  # type: ignore
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    SQLitePlugin = getattr(mod, "SQLitePlugin")

    db = tmp_path / "test.db"
    con = sqlite3.connect(db)
    con.execute("create table t(id integer, name text);")
    con.executemany("insert into t(id,name) values(?,?)", [(1, "a"), (2, "b")])
    con.commit(); con.close()

    pl = SQLitePlugin()
    out = pl.sql_open(str(db), "ro=1")
    assert "opened" in out
    out = pl.sql_tables()
    assert "t" in out
    out = pl.sql_query("select", "name", "from", "t", "order", "by", "id", "json=1", "max=10")
    obj = json.loads(out)
    assert obj.get("columns") == ["name"] or "columns" in obj
    rows = obj.get("rows") or []
    assert any(isinstance(x, dict) for x in rows)


def test_git_plugin(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    # Initialize a repo and commit one file
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    env = {"QJSON_GIT_ROOT": str(repo)}
    r = run_exec("/git_status short=1", env=env)
    assert r.returncode == 0
    assert "##" in r.stdout or "On branch" in r.stdout

    r = run_exec("/git_log 1", env=env)
    assert "init" in r.stdout

    # Change file to produce a diff
    (repo / "f.txt").write_text("xx\n", encoding="utf-8")
    r = run_exec("/git_diff f.txt", env=env)
    assert "f.txt" in r.stdout


def test_api_plugin_gated():
    r = run_exec("/api_get https://example.com")
    assert "network disabled" in r.stdout
