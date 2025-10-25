
from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, List

class Plugin:
    """Base class for plugins."""

    def __init__(self, tools: Dict[str, Callable[..., Any]] = None):
        self.tools = tools if tools is not None else {}

    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        """
        Returns a dictionary of commands provided by the plugin.
        The keys are the command names (e.g., '/linkup') and the values
        are the callable methods that implement the command.
        """
        return {}

def load_plugins(tools: Dict[str, Callable[..., Any]] = None) -> List[Plugin]:
    """
    Discovers and loads plugins from the 'plugins' directory.
    """
    plugins_dir = Path(__file__).parent / "plugins"
    loaded_plugins: List[Plugin] = []

    for _, name, _ in pkgutil.iter_modules([str(plugins_dir)]):
        try:
            module = importlib.import_module(f"qjson_agents.plugins.{name}")
            for _, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, Plugin)
                    and obj is not Plugin
                ):
                    loaded_plugins.append(obj(tools=tools))
        except Exception as e:
            print(f"Failed to load plugin {name}: {e}")

    return loaded_plugins
