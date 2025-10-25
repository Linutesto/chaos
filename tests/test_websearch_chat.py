import os
import tempfile
import unittest

from qjson_agents.agent import Agent


class FakeOllamaClient:
    def __init__(self, needle: str):
        self.needle = needle

    def chat(self, *, model: str, messages: list[dict], options: dict | None = None, stream: bool = False) -> dict:
        text = "\n".join(str(m.get("content", "")) for m in messages)
        found = self.needle in text
        reply = f"FOUND:{self.needle}" if found else "NOT_FOUND"
        return {"message": {"role": "assistant", "content": reply}}


class WebSearchInjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["QJSON_AGENTS_HOME"] = self.tmp.name

        self.manifest = {
            "agent_id": "WebSearchAgent",
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

    def test_websearch_env_injection(self):
        # Arm one-shot websearch injection with a unique needle in snippet
        needle = "WEB_NEEDLE_12345"
        results = [
            {"title": "r1", "url": "https://example/1", "snippet": f"contains {needle}"},
            {"title": "r2", "url": "https://example/2", "snippet": "other"},
        ]
        os.environ["QJSON_WEBSEARCH_RESULTS_ONCE"] = __import__("json").dumps(results)
        os.environ["QJSON_WEBSEARCH_HEADER"] = "### Web Search Results (test)"

        client = FakeOllamaClient(needle)
        reply = self.agent.chat_turn(
            "Check if needle is present via websearch.",
            client=client,
            model_override="mock-llm",
        )
        self.assertTrue(reply.startswith("FOUND:"), f"Expected FOUND:, got: {reply}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

