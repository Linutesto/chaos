import os
import requests
import io
import json
import sys
import types
import runpy
import unittest
from unittest.mock import patch, MagicMock


class LangSearchPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        # Import here to avoid import side effects before patches
        from qjson_agents.plugins.langsearch_crawler import LangSearchCrawlerPlugin

        self.Plugin = LangSearchCrawlerPlugin
        # Provide a minimal plugin instance
        self.plugin = self.Plugin(tools={})

    def test_format_results_happy_path(self):
        sample = {
            "data": {
                "webPages": {
                    "value": [
                        {
                            "name": "Example One",
                            "url": "https://example.com/1",
                            "snippet": "Snippet one",
                            "summary": "Summary one",
                        },
                        {
                            "name": "Example Two",
                            "url": "https://example.com/2",
                            "snippet": "Snippet two",
                        },
                    ]
                }
            }
        }
        out = self.plugin._format_results(sample)
        self.assertIn("Result 1", out)
        self.assertIn("Title: Example One", out)
        self.assertIn("URL: https://example.com/1", out)
        self.assertIn("Snippet: Snippet one", out)
        self.assertIn("Summary: Summary one", out)
        self.assertIn("Title: Example Two", out)

    def test_format_results_empty(self):
        out = self.plugin._format_results({})
        self.assertEqual(out, "No search results found.")

    def test_crawl_no_api_key(self):
        # With no API key, plugin should fall back to web (googlesearch) when available; patch it
        with patch.dict(os.environ, {}, clear=True):
            with patch("qjson_agents.plugins.langsearch_crawler._fallback_googlesearch", return_value=[{"name": "stub", "url": "https://x", "snippet": "s"}]):
                msg = self.plugin.crawl("test")
                self.assertIn("Result 1", msg)

    def test_crawl_success_via_mock(self):
        sample_response = {
            "data": {
                "webPages": {
                    "value": [
                        {"name": "X", "url": "https://x", "snippet": "s"}
                    ]
                }
            }
        }

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return sample_response

        with patch.dict(os.environ, {"LANGSEARCH_API_KEY": "dummy"}, clear=True):
            with patch("qjson_agents.plugins.langsearch_crawler.requests.post", return_value=_Resp()) as mock_post:
                out = self.plugin.crawl("language models")
                self.assertIn("Result 1", out)
                self.assertIn("language models", "language models")  # trivial guard
                mock_post.assert_called_once()

    def test_crawl_web_fallback_on_network_error(self):
        # Force a RequestException and rely on googlesearch fallback (patched)
        query = "WEB_NEEDLE_ABC"
        with patch.dict(os.environ, {"LANGSEARCH_API_KEY": "dummy"}, clear=False):
            with patch("qjson_agents.plugins.langsearch_crawler.requests.post", side_effect=requests.exceptions.RequestException("boom")):
                # Patch googlesearch fallback to return deterministic items
                with patch("qjson_agents.plugins.langsearch_crawler._fallback_googlesearch", return_value=[{"name": "stub", "url": "https://x", "snippet": query}]):
                    out = self.plugin.crawl(query)
                    self.assertIn("Result 1", out)


class SearchToolScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        # Create a stub default_api module providing google_web_search
        self.stub_mod = types.ModuleType("default_api")

        def google_web_search(*, query: str) -> dict:
            return {
                "query": query,
                "results": [
                    {"title": "Stub Result", "url": "https://stub.local"}
                ],
            }

        self.stub_mod.google_web_search = google_web_search  # type: ignore
        # Inject stub into sys.modules so tools/search_tool.py can import it
        sys.modules["default_api"] = self.stub_mod

    def tearDown(self) -> None:
        # Clean up injected module to minimize side effects for other tests
        try:
            del sys.modules["default_api"]
        except Exception:
            pass

    def test_search_tool_main_flow(self):
        # Execute the script via runpy with a fake argv and capture stdout
        script_path = os.path.join("tools", "search_tool.py")
        buf = io.StringIO()
        argv_backup = sys.argv[:]
        try:
            sys.argv = [script_path, "qjson agents"]
            with patch("sys.stdout", new=buf):
                runpy.run_path(script_path, run_name="__main__")
        finally:
            sys.argv = argv_backup
        out = buf.getvalue().strip()
        # Output should be a JSON object with our stub result
        payload = json.loads(out)
        self.assertEqual(payload.get("query"), "qjson agents")
        self.assertTrue(payload.get("results"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
