Plugin API — Writing Slash Command Plugins

Overview
Plugins let you register additional slash commands available in chat and in the `exec` subcommand. Plugins are regular Python modules placed under `qjson_agents/plugins/` that expose a `Plugin` subclass with a `get_commands()` map.

Base class
```
from typing import Any, Callable, Dict

class Plugin:
    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {}
```

Registration
- The plugin loader (`qjson_agents/plugin_manager.py`) imports modules from `qjson_agents/plugins/` and collects instances of `Plugin`.
- Each plugin must return a mapping of `"/yourcmd"` → callable.
- Callables receive the raw parts after the command token: e.g., `/foo a b` calls `foo('a','b')`.

Example: /crawl plugin
```
class LangSearchCrawlerPlugin(Plugin):
    """A plugin for performing web searches and crawling using the LangSearch API."""

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {
            "/crawl": self.crawl,
        }

    def crawl(self, *query_parts: str) -> str:
        # 1) Decide mode (URL seeds vs query)
        # 2) Perform search or BFS crawl
        # 3) Index outlines into the current agent (QJSON_AGENT_ID)
        # 4) Arm /open cache: QJSON_WEBRESULTS_CACHE, QJSON_WEBSEARCH_RESULTS_ONCE
        # 5) Return a human-formatted summary for the console
        ...
```

Environment conventions
- `QJSON_AGENT_ID` is set by the CLI when entering chat/exec; use it to index results for the active agent.
- Arm next‑turn injection by setting `QJSON_WEBSEARCH_RESULTS_ONCE` (JSON array) and a sticky cache `QJSON_WEBRESULTS_CACHE`.
- Set a header label in `QJSON_WEBSEARCH_HEADER` (e.g., "### Search Results (Plugin)") if you want a custom banner.

CLI interop
- In `chat`, plugins are executed after core engine commands (`/engine`, `/find`, `/open`).
- In `exec`, plugins are executed after core engine commands; output is printed to stdout.

Best practices
- Keep outputs concise and rely on the agent’s next turn for aggregation.
- Prefer HTML→outline→index when ingesting pages to avoid bloated prompts.
- Use the unified cache keys so `/open N` works across plugins.

