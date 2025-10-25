
import os
import sys
from pathlib import Path
import subprocess

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_linkup_plugin(monkeypatch):
    """
    Tests the plugin system by creating a dummy plugin and checking if it's loaded and executed.
    """
    plugin_content = """
from __future__ import annotations
from typing import Any, Dict, Callable
from qjson_agents.plugin_manager import Plugin

class DummyLinkupPlugin(Plugin):
    def get_commands(self) -> Dict[str, Callable[..., Any]]:
        return {
            "/test_linkup": self.test_linkup,
        }

    def test_linkup(self) -> str:
        return "Linkup plugin test successful!"
"""
    plugin_path = Path("qjson_agents/plugins/dummy_plugin.py")
    try:
        with open(plugin_path, "w") as f:
            f.write(plugin_content)

        # Mock input to avoid hanging
        monkeypatch.setattr('sys.stdin', open(os.devnull))

        # Run the chat command with the plugin command
        manifest_path = "manifests/lila.json"
        agent_id = "Lila-v∞"
        command = f"python -m qjson_agents.cli chat --id {agent_id} --manifest {manifest_path} --once /test_linkup"
        
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        assert "Linkup plugin test successful!" in result.stdout

    finally:
        # Clean up the dummy plugin
        if os.path.exists(plugin_path):
            os.remove(plugin_path)
