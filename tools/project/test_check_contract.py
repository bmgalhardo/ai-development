"""Verify the contract check against small project repos."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.project.check_contract import REQUIRED, check


class ContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        for path in REQUIRED:
            (self.project / path).parent.mkdir(parents=True, exist_ok=True)
            (self.project / path).write_text("# x\n")
        (self.project / ".agents/context/engineering.md").write_text(
            "Check command: `pytest`. Tests in tests/. Evidence: an example run.\n")
        os.symlink("AGENTS.md", self.project / "CLAUDE.md")

    def test_a_minimal_project_meets_the_contract(self):
        self.assertEqual(check(self.project), ([], []))

    def test_missing_parts_are_errors(self):
        (self.project / "docs/review.md").unlink()
        (self.project / "CLAUDE.md").unlink()
        errors, _ = check(self.project)
        self.assertIn("missing docs/review.md (the current build's review)", errors)
        self.assertIn("CLAUDE.md is not a symlink to AGENTS.md", errors)

    def test_an_engineering_doc_without_evidence_is_a_warning(self):
        (self.project / ".agents/context/engineering.md").write_text("Check command: `pytest`; tests in tests/.\n")
        self.assertEqual(check(self.project), ([], ["engineering.md doesn't seem to say its evidence"]))

    def test_a_publishing_doc_needs_an_output(self):
        (self.project / ".agents/context/publishing.md").write_text("| Output | Prepared files |\n")
        (self.project / ".gitignore").write_text("site/\n")
        self.assertEqual(check(self.project)[0], ["publishing.md lists no output (| <output> | `<folder>/` |)"])
        (self.project / ".agents/context/publishing.md").write_text("| docs | `site/` |\n")
        self.assertEqual(check(self.project), ([], ["a docs output but no mkdocs.yml"]))


if __name__ == "__main__":
    unittest.main()
