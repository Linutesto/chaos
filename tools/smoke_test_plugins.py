#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_exec(cmd: str, env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, "-m", "qjson_agents.cli", "exec", cmd, "--id", "SmokeAgent"],
        capture_output=True,
        text=True,
        env=e,
    )


def assert_in(needle: str, hay: str, ctx: str) -> None:
    if needle not in hay:
        print(f"[FAIL] missing '{needle}' in {ctx}\n---\n{hay}\n---")
        raise SystemExit(1)


def test_fs(tmp: Path) -> None:
    base = tmp / "fsroot"
    base.mkdir(parents=True, exist_ok=True)
    f1 = base / "a.txt"
    f1.write_text("hello", encoding="utf-8")
    env = {"QJSON_FS_ROOTS": str(base)}
    r = run_exec(f"/fs_list {base} glob=*.txt max=10", env=env)
    assert r.returncode == 0
    assert_in("a.txt", r.stdout, "fs_list")
    r = run_exec(f"/fs_read {f1} max_bytes=100", env=env)
    assert_in("[fs] read", r.stdout, "fs_read")
    assert_in("hello", r.stdout, "fs_read")
    r = run_exec(f"/fs_write {base/'b.txt'} hi", env=env)
    assert_in("writes disabled", r.stdout, "fs_write gated")
    env_w = env | {"QJSON_FS_WRITE": "1"}
    r = run_exec(f"/fs_write {base/'b.txt'} hi", env=env_w)
    assert_in("wrote", r.stdout, "fs_write")


def test_exec() -> None:
    r = run_exec("/py print(1+2)")
    assert_in("disabled", r.stdout, "py gated")
    r = run_exec("/py print(1+2)", env={"QJSON_ALLOW_EXEC": "1", "QJSON_EXEC_TIMEOUT": "3"})
    if r.returncode != 0:
        print(r.stdout); print(r.stderr)
        raise SystemExit(1)
    assert_in("[py] exit=0", r.stdout, "py ok")
    assert_in("3", r.stdout, "py output")


def test_sqlite(tmp: Path) -> None:
    # import by path to avoid packaging issues
    import importlib.util as _ilu
    p = ROOT / "qjson_agents" / "plugins" / "db_plugin.py"
    spec = _ilu.spec_from_file_location("db_plugin", str(p))
    mod = _ilu.module_from_spec(spec)  # type: ignore
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    SQLitePlugin = getattr(mod, "SQLitePlugin")
    db = tmp / "test.db"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute("create table t(id integer, name text);")
    con.executemany("insert into t(id,name) values(?,?)", [(1, "a"), (2, "b")])
    con.commit(); con.close()
    pl = SQLitePlugin()
    out = pl.sql_open(str(db), "ro=1")
    assert_in("opened", out, "sql_open")
    out = pl.sql_tables()
    assert_in("t", out, "sql_tables")
    out = pl.sql_query("select", "name", "from", "t", "order", "by", "id", "json=1", "max=10")
    obj = json.loads(out)
    assert "columns" in obj and "rows" in obj
    assert obj["columns"][0] == "name"


def test_git(tmp: Path) -> None:
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    env = {"QJSON_GIT_ROOT": str(repo)}
    r = run_exec("/git_status short=1", env=env)
    assert r.returncode == 0
    if "##" not in r.stdout and "On branch" not in r.stdout:
        print(r.stdout); raise SystemExit(1)
    r = run_exec("/git_log 1", env=env)
    assert_in("init", r.stdout, "git_log")
    (repo / "f.txt").write_text("xx\n", encoding="utf-8")
    r = run_exec("/git_diff f.txt", env=env)
    assert_in("f.txt", r.stdout, "git_diff")


def test_api_gated() -> None:
    r = run_exec("/api_get https://example.com")
    assert_in("network disabled", r.stdout, "api gated")


def main() -> None:
    tmp = Path.cwd() / "tmp_smoke"
    tmp.mkdir(exist_ok=True)
    test_fs(tmp)
    test_exec()
    test_sqlite(tmp)
    test_git(tmp)
    test_api_gated()
    print("[OK] plugin smoke tests passed")


if __name__ == "__main__":
    main()
