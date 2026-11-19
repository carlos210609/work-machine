"""Hermes plugin integration smoke tests (without importing the full runtime)."""
from __future__ import annotations

import json
import unittest

from plugins.work_machine import register, work_machine_goal


class FakeContext:
    def __init__(self):
        self.tools = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)


class PluginTests(unittest.TestCase):
    def test_registers_a_native_hermes_tool(self):
        ctx = FakeContext()
        register(ctx)
        self.assertEqual(len(ctx.tools), 1)
        tool = ctx.tools[0]
        self.assertEqual(tool["name"], "work_machine_goal")
        self.assertEqual(tool["toolset"], "work_machine")
        self.assertEqual(tool["schema"]["name"], "work_machine_goal")
        self.assertEqual(tool["schema"]["parameters"]["required"], ["action"])
        self.assertTrue(callable(tool["handler"]))

    def test_unscoped_calls_fail_closed(self):
        out = json.loads(work_machine_goal({"action": "list"}))
        self.assertFalse(out["ok"])
        self.assertIn("context", out["error"])

    def test_invalid_input_fails_closed(self):
        out = json.loads(work_machine_goal(None))
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()
