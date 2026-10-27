"""Verify which cycle the worker loop works on."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.workers import next_issue


class CurrentCycleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / "project"
        patcher = patch.object(next_issue, "WORKFLOW", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def cycle(self, name, *statuses):
        issues = self.root / ".scratch/project" / name / "issues"
        issues.mkdir(parents=True)
        for number, status in enumerate(statuses, 1):
            (issues / f"{number:02d}-issue.md").write_text(f"**Status:** {status}\n**Blocked by:** None\n")
        return issues.parent

    def test_an_unfinished_cycle_comes_before_a_newer_one(self):
        old = self.cycle("2026-10-22-old", "done", "in progress", "open")
        self.cycle("2026-10-24-new", "open", "open")
        self.assertEqual(next_issue.current_cycle(self.project), old)

    def test_a_finished_cycle_gives_way_to_the_next(self):
        self.cycle("2026-10-22-old", "done", "done")
        new = self.cycle("2026-10-24-new", "open", "open")
        self.assertEqual(next_issue.current_cycle(self.project), new)

    def test_a_review_folder_without_issues_is_not_a_cycle_to_work(self):
        old = self.cycle("2026-10-22-old", "done", "open")
        (self.root / ".scratch/project/2026-10-26-review/mocks").mkdir(parents=True)
        self.assertEqual(next_issue.current_cycle(self.project), old)


if __name__ == "__main__":
    unittest.main()
