"""Exercise the public API with tracker and runner files, never real workers."""

import fcntl
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from .app import create_app


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cycle = self.root / ".scratch" / "project" / "2026-10-25-cycle"
        (self.cycle / "issues").mkdir(parents=True)
        self.artifacts = self.root / ".scratch" / "project" / "runner"
        self.artifacts.mkdir(parents=True)
        self.logs = self.cycle / "work"
        self.logs.mkdir()
        self.client = TestClient(create_app(self.root))
        self.addCleanup(self.client.close)

    def issue(self, number, status, blockers="none"):
        path = self.cycle / "issues" / f"{number}-feature.md"
        path.write_text(f"# Issue {number}: Feature\n\n**Status:** {status}\n"
                        f"**Blocked by:** {blockers}\n\n## Progress\nChecks passed.\n\n## Comments\nNone\n")
        return str(path.relative_to(self.root))

    def board(self):
        response = self.client.get("/api/board", params={"project": "project", "cycle": self.cycle.name})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_board_agrees_with_runner_dependencies_and_special_build_rule(self):
        self.issue("01", "done")
        self.issue("02", "blocked")
        self.issue("03", "open", "01, 02")
        self.issue("04", "open", "01, 02, 03")
        cards = self.board()["issues"]
        self.assertEqual([card["stage"] for card in cards], ["done", "blocked", "waiting", "waiting"])
        self.assertEqual(cards[2]["blockers"], ["02"])
        self.issue("03", "done")
        self.assertEqual(self.board()["issues"][-1]["stage"], "ready")

    def test_review_does_not_release_dependencies(self):
        self.issue("01", "in review")
        self.issue("02", "open", "01")
        self.issue("03", "open", "01, 02")
        cards = self.board()["issues"]
        self.assertEqual([card["stage"] for card in cards], ["reviewing", "waiting", "waiting"])
        self.assertEqual(cards[0]["progress"], "Checks passed.")

    def test_ready_issue_does_not_depend_on_another_active_issue(self):
        self.issue("01", "in progress")
        self.issue("02", "open")
        self.issue("03", "open", "01, 02")
        self.assertEqual(self.board()["issues"][1]["stage"], "ready")

    def test_running_parallel_reviews_and_finished_history_are_not_double_counted(self):
        identity = self.issue("01", "in review")
        records = [{"attempt": axis, "issue": identity, "role": "review", "axis": axis,
                    "provider": "codex", "started_at": "2026-10-25T00:00:00+00:00"}
                   for axis in ("standards", "spec")]
        (self.artifacts / "current.json").write_text(json.dumps(records))
        with (self.artifacts / "runner.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            board = self.board()
            self.assertTrue(board["runner"]["active"])
            self.assertEqual(len(board["issues"][0]["active_attempts"]), 2)
        records = [{**row, "duration_seconds": 25, "outcome": "reviewed"} for row in records]
        (self.logs / "attempts.jsonl").write_text("\n".join(map(json.dumps, records)))
        (self.artifacts / "current.json").write_text(json.dumps(records))
        board = self.board()
        self.assertFalse(board["runner"]["active"])
        self.assertEqual(len(board["issues"][0]["attempts"]), 2)
        self.assertEqual(board["issues"][0]["total_attempt_seconds"], 50)

    def test_unfinished_attempt_without_lock_is_not_reported_running(self):
        identity = self.issue("01", "in progress")
        (self.artifacts / "current.json").write_text(json.dumps([
            {"attempt": "old", "issue": identity, "started_at": "2020-01-01T00:00:00+00:00"}]))
        card = self.board()["issues"][0]
        self.assertEqual(card["active_attempts"], [])
        self.assertEqual(card["total_attempt_seconds"], 0)

    def test_partial_artifacts_leave_the_issue_board_available(self):
        self.issue("01", "done")
        (self.artifacts / "current.json").write_text("[")
        (self.logs / "attempts.jsonl").write_text('{"attempt":')
        board = self.board()
        self.assertEqual(board["issues"][0]["stage"], "done")
        self.assertEqual(len(board["warnings"]), 2)

    def test_old_cycle_does_not_inherit_current_attempts(self):
        self.issue("01", "done")
        (self.artifacts / "current.json").write_text(json.dumps([
            {"attempt": "new", "issue": ".scratch/project/new-cycle/issues/01-feature.md"}]))
        with (self.artifacts / "runner.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            board = self.board()
            self.assertTrue(board["runner"]["active"])
            self.assertEqual(board["runner"]["attempts"], [])
            self.assertEqual(board["issues"][0]["attempts"], [])

    def test_catalog_empty_workspace_and_selection_validation(self):
        self.assertEqual(self.client.get("/api/catalog").json(), [{"project": "project", "cycles": [self.cycle.name]}])
        self.assertEqual(self.client.get("/api/board", params={"project": "../project", "cycle": ".."}).status_code, 404)
        self.assertEqual(self.client.get("/api/board").status_code, 422)
        self.assertEqual(self.client.post("/api/board").status_code, 405)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/static/board.js").status_code, 200)
        self.assertEqual(self.client.get("/.scratch/project/runner/current.json").status_code, 404)

    def test_issue_mid_write_is_retryable(self):
        path = self.issue("01", "open")
        (self.root / path).write_text("# unfinished write")
        response = self.client.get("/api/board", params={"project": "project", "cycle": self.cycle.name})
        self.assertEqual(response.status_code, 503)

    def test_review_reports_match_issue_and_preserve_full_comments(self):
        self.issue("01", "in review")
        self.issue("02", "open", "01")
        reviews = self.cycle / "reviews"
        reviews.mkdir()
        content = "# Standards\n\nReviewer: codex (CLI default), at abc123.\n\nFix <script>alert(1)</script>.\n"
        (reviews / "01-standards.md").write_text(content)
        (reviews / "02-spec.md").write_text("Reviewer: claude (sonnet), at def456.\n\nCheck the spec.")
        cards = self.board()["issues"]
        self.assertEqual(cards[0]["reviews"][0], {"axis": "standards", "status": "available",
                                                "provider": "codex", "content": content})
        self.assertEqual(cards[0]["reviews"][1]["status"], "missing")
        self.assertEqual(cards[1]["reviews"][1]["provider"], "claude")

    def test_missing_review_directory_is_not_a_board_error(self):
        self.issue("01", "open")
        board = self.board()
        self.assertEqual([report["status"] for report in board["issues"][0]["reviews"]], ["missing", "missing"])
        self.assertEqual(board["warnings"], [])

    def test_reads_leave_all_tracker_and_artifact_bytes_unchanged(self):
        self.issue("01", "done")
        (self.logs / "attempts.jsonl").write_text("")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.board()
        self.assertEqual({path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}, before)


if __name__ == "__main__":
    unittest.main()
