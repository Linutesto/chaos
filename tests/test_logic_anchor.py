import os
import unittest
from pathlib import Path

from qjson_agents.qjson_types import load_manifest
from qjson_agents.logic.persona_runtime import on_message


class LogicAnchorTests(unittest.TestCase):
    def test_hookprobe_builds_anchor(self):
        mf = load_manifest(Path('personas/HookProbe.json'))
        st = {}
        out = on_message(st, 'summarize and give 3 next steps: test the desk cleanup', mf)
        self.assertIn('Understanding', out)
        self.assertIn('Proposed next steps', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)

