import os
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from qjson_agents.agent import Agent
from qjson_agents.plugins.langsearch_crawler import LangSearchCrawlerPlugin


class FakeOllamaClient:
    def __init__(self, needle: str):
        self.needle = needle

    def chat(self, *, model: str, messages: list[dict], options: dict | None = None, stream: bool = False) -> dict:
        text = "\n".join(str(m.get("content", "")) for m in messages)
        found = self.needle in text
        reply = f"FOUND:{self.needle}" if found else "NOT_FOUND"
        return {"message": {"role": "assistant", "content": reply}}


class CrawlInjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["QJSON_AGENTS_HOME"] = self.tmp.name
        # Create a local file that will be discovered by local fallback
        self.needle = "CRAWL_NEEDLE_777"
        with open(os.path.join(self.tmp.name, "note.md"), "w", encoding="utf-8") as fh:
            fh.write(f"This line has {self.needle}\n")
        self.manifest = {
            "agent_id": "CrawlAgent",
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

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_crawl_sets_injection_and_chat_uses_it(self):
        # Ensure we have no API key to trigger web fallback, and patch fallback
        os.environ.pop("LANGSEARCH_API_KEY", None)
        plugin = LangSearchCrawlerPlugin(tools={})
        with patch("qjson_agents.plugins.langsearch_crawler._fallback_googlesearch", return_value=[{"name": "stub", "url": "https://stub", "snippet": self.needle}]):
            out = plugin.crawl("CRAWL_NEEDLE_777")
            self.assertIn("Result 1", out)
            # Env var should be set
            ws = os.environ.get("QJSON_WEBSEARCH_RESULTS_ONCE")
            self.assertTrue(ws)
            arr = json.loads(ws)
            self.assertTrue(any(self.needle in (it.get("snippet") or "") for it in arr))
            # Now chat_turn should see the injected block and the mock client finds the needle
            client = FakeOllamaClient(self.needle)
            reply = self.agent.chat_turn("Use the latest crawl results.", client=client, model_override="mock-llm")
            self.assertTrue(reply.startswith("FOUND:"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
