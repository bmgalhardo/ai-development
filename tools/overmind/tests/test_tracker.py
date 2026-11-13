"""Which cycle and issue the workers take, read from tracker files in a temporary workflow root."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from overmind.tracker import Tracker, TrackerError


class TrackerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.tracker = Tracker.for_project(self.root, "project")

    def cycle(self, name, *issues):
        """Write a cycle; each issue is a status, or (status, blockers)."""
        folder = self.root / ".scratch/project" / name / "issues"
        folder.mkdir(parents=True)
        for number, issue in enumerate(issues, 1):
            status, blockers = issue if isinstance(issue, tuple) else (issue, "None")
            (folder / f"{number:02d}-issue.md").write_text(f"**Status:** {status}\n**Blocked by:** {blockers}\n")
        return folder.parent

    def next_number(self, *issues):
        self.cycle("2026-10-22-test", *issues)
        issue = self.tracker.current_cycle().next_issue()
        return issue.number if issue else None

    def test_an_unfinished_cycle_comes_before_a_newer_one(self):
        old = self.cycle("2026-10-22-old", "done", "in progress", "open")
        self.cycle("2026-10-24-new", "open", "open")
        self.assertEqual(self.tracker.current_cycle().path, old)

    def test_a_finished_cycle_gives_way_to_the_next(self):
        self.cycle("2026-10-22-old", "done", "done")
        new = self.cycle("2026-10-24-new", "open", "open")
        self.assertEqual(self.tracker.current_cycle().path, new)

    def test_a_review_folder_without_issues_is_not_a_cycle_to_work(self):
        old = self.cycle("2026-10-22-old", "done", "open")
        (self.root / ".scratch/project/2026-10-26-review/mocks").mkdir(parents=True)
        self.assertEqual(self.tracker.current_cycle().path, old)

    def test_a_finished_last_cycle_is_still_current(self):
        last = self.cycle("2026-10-22-old", "done", "done")
        self.assertEqual(self.tracker.current_cycle().path, last)

    def test_an_issue_left_in_progress_comes_first(self):
        self.assertEqual(self.next_number("in review", "in progress", "open"), "02")

    def test_an_issue_in_review_comes_before_open_ones(self):
        self.assertEqual(self.next_number("open", "in review", "open"), "02")

    def test_an_open_issue_waits_for_its_blockers(self):
        self.assertIsNone(self.next_number("blocked", ("open", "01"), "open"))

    def test_an_issue_with_done_blockers_is_ready(self):
        self.assertEqual(self.next_number("done", ("open", "01"), ("open", "01, 02")), "02")

    def test_a_missing_blocker_keeps_an_issue_waiting(self):
        self.assertIsNone(self.next_number(("open", "07"), "open"))

    def test_the_build_waits_for_every_other_issue(self):
        self.assertIsNone(self.next_number("done", ("open", "07"), "open"))

    def test_the_build_is_ready_once_the_others_are_done_or_blocked(self):
        self.assertEqual(self.next_number("done", "blocked", ("open", "01, 02")), "03")

    def test_issues_waiting_for_each_other_are_stuck(self):
        self.cycle("2026-10-22-test", "done", ("open", "03"), ("open", "01, 02"))
        cycle = self.tracker.current_cycle()
        self.assertEqual(cycle.stuck(), {"02": ["03"], "03": ["02"]})
        self.assertIn("02 waits for 03; 03 waits for 02", cycle.stuck_message())

    def test_an_issue_waiting_for_a_missing_number_is_stuck(self):
        self.cycle("2026-10-22-test", ("open", "07"), "open")
        self.assertEqual(self.tracker.current_cycle().stuck(), {"01": ["07"], "02": ["01"]})

    def test_a_cycle_waiting_for_a_blocked_issue_is_not_stuck(self):
        self.cycle("2026-10-22-test", "blocked", ("open", "01"), "open")
        self.assertEqual(self.tracker.current_cycle().stuck(), {})

    def test_a_cycle_with_a_ready_issue_is_not_stuck(self):
        self.cycle("2026-10-22-test", "done", ("open", "01"), "open")
        self.assertEqual(self.tracker.current_cycle().stuck(), {})

    def test_an_issue_without_a_status_is_an_error(self):
        folder = self.cycle("2026-10-22-test", "open")
        (folder / "issues/02-broken.md").write_text("no status\n")
        with self.assertRaisesRegex(TrackerError, "02-broken.md: no \\*\\*Status:\\*\\* line"):
            self.tracker.current_cycle()

    def test_a_project_without_cycles_is_an_error(self):
        with self.assertRaisesRegex(TrackerError, "No cycle with issues"):
            self.tracker.current_cycle()

    def test_a_project_must_be_a_git_repo(self):
        (self.root / "plain").mkdir()
        with self.assertRaisesRegex(TrackerError, "is not a git repo"):
            Tracker.for_project(self.root, "plain")


if __name__ == "__main__":
    unittest.main()
