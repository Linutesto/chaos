
from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, List
import os

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

    allow_env = os.environ.get("QJSON_PLUGIN_ALLOW", "").strip()
    deny_env = os.environ.get("QJSON_PLUGIN_DENY", "").strip()
    allow_set = {s.strip() for s in allow_env.split(",") if s.strip()} if allow_env else set()
    deny_set = {s.strip() for s in deny_env.split(",") if s.strip()} if deny_env else set()

    for _, name, _ in pkgutil.iter_modules([str(plugins_dir)]):
        try:
            module = importlib.import_module(f"qjson_agents.plugins.{name}")
            for _, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, Plugin)
                    and obj is not Plugin
                ):
                    inst = obj(tools=tools)
                    # Apply allow/deny filtering at command level if configured
                    try:
                        cmds = inst.get_commands()
                        if isinstance(cmds, dict) and (allow_set or deny_set):
                            filtered: Dict[str, Callable[..., Any]] = {}
                            for cmd, fn in cmds.items():
                                key = str(cmd).strip()
                                # If allow list present, only admit exact matches
                                if allow_set and (key not in allow_set):
                                    continue
                                # Deny list removes matches
                                if deny_set and (key in deny_set):
                                    continue
                                filtered[key] = fn
                            # Override instance map if plugin stores it, or monkey-patch a wrapper
                            # Since base Plugin.get_commands() returns fresh dicts, we wrap get_commands
                            def _make_get_commands(fmap: Dict[str, Callable[..., Any]]):
                                return lambda: dict(fmap)
                            inst.get_commands = _make_get_commands(filtered)  # type: ignore
                    except Exception:
                        pass
                    loaded_plugins.append(inst)
        except Exception as e:
            print(f"Failed to load plugin {name}: {e}")

    return loaded_plugins
