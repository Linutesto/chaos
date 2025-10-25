import os
import json
import tempfile
import unittest

from qjson_agents.cli import _arm_webopen_from_results
from qjson_agents.agent import Agent


class FakeOllamaClient:
    def __init__(self, needle: str):
        self.needle = needle

    def chat(self, *, model: str, messages: list[dict], options: dict | None = None, stream: bool = False) -> dict:
        text = "\n".join(str(m.get("content", "")) for m in messages)
        found = self.needle in text
        reply = f"FOUND:{self.needle}" if found else "NOT_FOUND"
        return {"message": {"role": "assistant", "content": reply}}


class WebOpenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["QJSON_AGENTS_HOME"] = self.tmp.name
        self.page_path = os.path.join(self.tmp.name, "page.txt")
        self.needle = "WEBOPEN_NEEDLE_9000"
        with open(self.page_path, "w", encoding="utf-8") as fh:
            fh.write(f"Hello {self.needle} this is page content\n")
        self.results = [
            {"title": "Local Page", "url": self.page_path, "snippet": "local"}
        ]
        self.agent = Agent({
            "agent_id": "WebOpenAgent",
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
        })

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_arm_webopen_and_inject(self):
        payload = json.dumps(self.results)
        msg = _arm_webopen_from_results(1, payload)
        self.assertIn("Loaded", msg)
        client = FakeOllamaClient(self.needle)
        reply = self.agent.chat_turn("Use /open content.", client=client, model_override="mock-llm")
        self.assertTrue(reply.startswith("FOUND:"))

    def test_crawlopen_uses_cache_and_injects(self):
        payload = json.dumps(self.results)
        os.environ["QJSON_WEBRESULTS_CACHE"] = payload
        # Simulate /open flow by arming from cache populated by /find or plugin /crawl
        msg = _arm_webopen_from_results(1, os.environ["QJSON_WEBRESULTS_CACHE"])
        self.assertIn("Loaded", msg)
        client = FakeOllamaClient(self.needle)
        reply = self.agent.chat_turn("Use /open content.", client=client, model_override="mock-llm")
        self.assertTrue(reply.startswith("FOUND:"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
