import os
import tempfile
import unittest
from pathlib import Path

from qjson_agents.agent import Agent
from qjson_agents.ingest_manager import ingest_files_to_memory
from qjson_agents.memory import agent_dir, tail_jsonl


class FakeOllamaClient:
    def __init__(self, needle: str):
        self.needle = needle

    def chat(self, *, model: str, messages: list[dict], options: dict | None = None, stream: bool = False) -> dict:
        text = "\n".join(str(m.get("content", "")) for m in messages)
        found = self.needle in text
        reply = f"FOUND:{self.needle}" if found else "NOT_FOUND"
        return {"message": {"role": "assistant", "content": reply}}

    def tags(self):
        return [{"name": "mock-llm"}]


class ChatIngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["QJSON_AGENTS_HOME"] = self.tmp.name

        # Minimal valid manifest
        self.manifest = {
            "agent_id": "TestAgent",
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
            "core_directives": [
                "Be correct",
                "Stay local",
            ],
            "runtime": {"model": "mock-llm"},
        }
        self.agent = Agent(self.manifest)

        # Create a sample document to ingest
        self.doc_path = Path(self.tmp.name) / "doc.txt"
        self.needle = "XYZ_UNIQUE_TEST_PHRASE"
        self.doc_path.write_text(f"This is a test file containing {self.needle}.", encoding="utf-8")

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_ingest_metadata_written(self):
        n = ingest_files_to_memory([str(self.doc_path)], self.agent.agent_id, truncate_limit=None, source="inject")
        self.assertEqual(n, 1)
        mem_path = agent_dir(self.agent.agent_id) / "memory.jsonl"
        tail = tail_jsonl(mem_path, 4)
        self.assertTrue(tail, "memory.jsonl should have entries after ingestion")
        last = tail[-1]
        self.assertEqual(last.get("role"), "system")
        meta = last.get("meta") or {}
        self.assertEqual(meta.get("source"), "inject")
        self.assertIn(str(self.doc_path), last.get("content", ""))

    def test_chat_sees_injected_content_via_extra_system(self):
        ingest_files_to_memory([str(self.doc_path)], self.agent.agent_id, truncate_limit=None, source="inject")
        # Build extra_system block from last system message
        mem_path = agent_dir(self.agent.agent_id) / "memory.jsonl"
        sys_msgs = [m for m in tail_jsonl(mem_path, 16) if m.get("role") == "system"]
        self.assertTrue(sys_msgs, "Expected at least one system message after ingestion")
        extra_system = sys_msgs[-1].get("content", "")

        client = FakeOllamaClient(self.needle)
        reply = self.agent.chat_turn(
            "Please confirm the presence of the unique phrase.",
            client=client,
            model_override="mock-llm",
            extra_system=extra_system,
        )
        self.assertTrue(reply.startswith("FOUND:"), f"Expected FOUND: reply, got: {reply}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

