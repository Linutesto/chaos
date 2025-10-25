import unittest
from types import SimpleNamespace

from qjson_agents.cli import _perform_websearch


class CLIPerformWebsearchTests(unittest.TestCase):
    def test_default_api_path_normalizes(self):
        def _google_web_search(*, query: str):
            return {
                "results": [
                    {"title": "A", "url": "https://a", "snippet": "s1"},
                    {"name": "B", "url": "https://b", "summary": "s2"},
                ]
            }

        default_api = SimpleNamespace(google_web_search=_google_web_search)
        out = _perform_websearch("qjson", default_api=default_api)
        self.assertEqual(out.get("query"), "qjson")
        self.assertEqual(len(out.get("results") or []), 2)
        r0 = out["results"][0]
        self.assertEqual(r0["title"], "A")
        self.assertEqual(r0["url"], "https://a")
        self.assertEqual(r0["snippet"], "s1")

    def test_fallback_injection_function(self):
        def _fallback(query: str):
            return ["https://x", "https://y"]

        out = _perform_websearch("qjson", default_api=None, fallback=_fallback)
        self.assertEqual(out.get("query"), "qjson")
        res = out.get("results") or []
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["url"], "https://x")
        self.assertEqual(res[0]["title"], "https://x")


if __name__ == "__main__":
    unittest.main(verbosity=2)

