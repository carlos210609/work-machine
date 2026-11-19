"""Regression tests for Work Machine's durable mission state."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugins.work_machine.mission import MissionError, MissionStore


class MissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "mission.sqlite3"
        self.store = MissionStore(self.path)
        self.owner = "conversation-1"
        self.plan = [
            {"title": "Implement", "acceptance": "Code is committed and readable"},
            {"title": "Test", "acceptance": "A test command reports passing results"},
        ]
        self.mid = self.store.create(self.owner, "Example goal", self.plan, 3)["id"]

    def test_durable_resume_and_completion(self):
        first = self.store.next_step(self.owner, self.mid)
        self.assertEqual(first["step"]["ordinal"], 1)
        resumed = MissionStore(self.path).next_step(self.owner, self.mid)
        self.assertTrue(resumed["resumed"])
        self.assertEqual(first["step"]["id"], resumed["step"]["id"])
        with self.assertRaises(MissionError):
            self.store.finish(self.owner, self.mid, "Premature completion is not permitted")
        self.store.complete_step(self.owner, self.mid, first["step"]["id"], "src/app.py committed in branch")
        second = self.store.next_step(self.owner, self.mid)
        self.assertEqual(second["step"]["ordinal"], 2)
        self.store.complete_step(self.owner, self.mid, second["step"]["id"], "python -m unittest: passed")
        self.assertEqual(self.store.status(self.owner, self.mid)["status"], "ready_for_review")
        final = self.store.finish(self.owner, self.mid, "Reviewed both pieces of evidence")
        self.assertEqual(final["status"], "completed")
        self.assertEqual([x["status"] for x in final["steps"]], ["done", "done"])
        self.assertIn("events", final)

    def test_failed_step_retry_budget(self):
        for attempt in range(3):
            active = self.store.next_step(self.owner, self.mid)
            self.store.fail_step(self.owner, self.mid, active["step"]["id"], "Temporary failure")
        self.assertEqual(self.store.status(self.owner, self.mid)["status"], "blocked")
        with self.assertRaises(MissionError):
            self.store.next_step(self.owner, self.mid)

    def test_conversation_isolation(self):
        with self.assertRaises(MissionError):
            self.store.status("other-conversation", self.mid)
        self.assertEqual(self.store.list_missions("other-conversation"), [])

    def test_validation(self):
        with self.assertRaises(MissionError):
            self.store.create(self.owner, "Bad", [], 2)
        with self.assertRaises(MissionError):
            self.store.create(self.owner, "Bad", self.plan, 101)
        with self.assertRaises(MissionError):
            self.store.create(self.owner, "Bad", [{"title": "x", "acceptance": "short"}])
        with self.assertRaises(MissionError):
            self.store.complete_step(self.owner, self.mid, 999, "Evidence not possible yet")

    def test_cancellation(self):
        self.store.cancel(self.owner, self.mid)
        self.assertEqual(self.store.status(self.owner, self.mid)["status"], "cancelled")
        with self.assertRaises(MissionError):
            self.store.next_step(self.owner, self.mid)


if __name__ == "__main__":
    unittest.main()
