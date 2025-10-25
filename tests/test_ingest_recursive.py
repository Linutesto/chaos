import os
import tempfile
import unittest
from pathlib import Path

from qjson_agents.agent import Agent
from qjson_agents.ingest_manager import (
    ingest_path_recursive,
    ingest_path_py_recursive,
    scan_path,
)
from qjson_agents.memory import agent_dir, tail_jsonl


class IngestRecursiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["QJSON_AGENTS_HOME"] = self.tmp.name

        # Minimal valid manifest
        self.manifest = {
            "agent_id": "IngestAgent",
            "origin": "Test",
            "creator": "unittest",
            "roles": ["tester"],
            "features": {
                "recursive_memory": True,
                "fractal_state": True,
                "autonomous_reflection": False,
                "emergent_behavior": "deterministic",
                "chaos_alignment": "low",
                "symbolic_interface": "text",
            },
            "core_directives": ["Be correct", "Stay local"],
            "runtime": {"model": "mock-llm"},
        }
        self.agent = Agent(self.manifest)

        # Create a directory tree with allowed and disallowed files
        self.data_dir = Path(self.tmp.name) / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "a.json").write_text("{\"k\": 1}", encoding="utf-8")
        (self.data_dir / "b.yson").write_text("key: value\n", encoding="utf-8")
        (self.data_dir / "c.ysonx").write_text("#@meta: test\nfoo: bar\n", encoding="utf-8")
        (self.data_dir / "d.txt").write_text("hello world\n", encoding="utf-8")
        (self.data_dir / "e.md").write_text("# Title\nbody\n", encoding="utf-8")
        (self.data_dir / "skip.bin").write_text("xxxx", encoding="utf-8")
        sub = self.data_dir / "sub"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "f.txt").write_text("nested\n", encoding="utf-8")
        # Python file for /inject_py
        (self.data_dir / "code.py").write_text("def f():\n    return 42\n", encoding="utf-8")

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_scan_path_counts(self):
        allowed = scan_path(str(self.data_dir), [".json", ".yson", ".ysonx", ".txt", ".md"], recursive=True)
        # Expect: a.json, b.yson, c.ysonx, d.txt, e.md, sub/f.txt  -> 6 files
        self.assertEqual(len(allowed), 6)

    def test_ingest_path_recursive(self):
        mem_path = agent_dir(self.agent.agent_id) / "memory.jsonl"
        before = len(tail_jsonl(mem_path, 1024))
        n = ingest_path_recursive(str(self.data_dir), self.agent.agent_id, truncate_limit=None)
        # Expect 6 system messages added
        self.assertEqual(n, 6)
        after_tail = tail_jsonl(mem_path, 16)
        self.assertGreaterEqual(len(after_tail), before + n)
        # Last message should have meta.source == 'inject'
        last = after_tail[-1]
        self.assertEqual(last.get("role"), "system")
        self.assertEqual((last.get("meta") or {}).get("source"), "inject")

    def test_ingest_path_py_recursive(self):
        mem_path = agent_dir(self.agent.agent_id) / "memory.jsonl"
        before = len(tail_jsonl(mem_path, 1024))
        n = ingest_path_py_recursive(str(self.data_dir), self.agent.agent_id, truncate_limit=None)
        # Expect 1 python file ingested
        self.assertEqual(n, 1)
        after_tail = tail_jsonl(mem_path, 8)
        self.assertGreaterEqual(len(after_tail), before + n)
        last = after_tail[-1]
        self.assertEqual(last.get("role"), "system")
        self.assertEqual((last.get("meta") or {}).get("source"), "inject_py")


if __name__ == "__main__":
    unittest.main(verbosity=2)

