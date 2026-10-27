#!/usr/bin/env python3
"""Check that a project repo provides what the workflow reads from it.

The contract is .agents/context/project-setup.md. Missing required parts
are errors (exit 1); a doubtful part is a warning. Run from this repo:

    python3 tools/project/check_contract.py ../<project>
"""

import argparse
from pathlib import Path
import re
import sys

WORKFLOW = Path(__file__).resolve().parents[2]
REQUIRED = {
    "AGENTS.md": "what the project is, its rules and pointers",
    ".agents/context/domain.md": "where the domain model lives and where decisions go",
    ".agents/context/decisions.md": "the iteration log",
    ".agents/context/status.md": "what's built, agreed and next",
    ".agents/context/engineering.md": "the check command, code map and tests, evidence",
    "docs/README.md": "what's where in docs/",
    "docs/review.md": "the current build's review",
}
# Words the engineering doc's required parts are found by.
ENGINEERING = {"check command": r"\bcheck", "tests": r"\btests?\b", "evidence": r"\bevidence|\bcaptures?\b"}
ROW = re.compile(r"^\|\s*([a-z][\w-]*)\s*\|\s*`([^`]+)`", re.IGNORECASE)


def check(project):
    """Return (errors, warnings) for the project at this path."""
    errors, warnings = [], []
    if not (project / ".git").exists():
        errors.append("not a git repo")
    for path, what in REQUIRED.items():
        if not (project / path).is_file():
            errors.append(f"missing {path} ({what})")
    claude = project / "CLAUDE.md"
    if not (claude.is_symlink() and claude.resolve() == (project / "AGENTS.md").resolve()):
        errors.append("CLAUDE.md is not a symlink to AGENTS.md")
    engineering = project / ".agents/context/engineering.md"
    if engineering.is_file():
        text = engineering.read_text(encoding="utf-8").lower()
        for part, pattern in ENGINEERING.items():
            if not re.search(pattern, text):
                warnings.append(f"engineering.md doesn't seem to say its {part}")
    publishing = project / ".agents/context/publishing.md"
    if publishing.is_file():
        rows = [ROW.match(line.strip()) for line in publishing.read_text(encoding="utf-8").splitlines()]
        rows = [row for row in rows if row and row.group(1).lower() != "mocks"]
        if not rows:
            errors.append("publishing.md lists no output (| <output> | `<folder>/` |)")
        if any(row.group(1).lower() == "docs" for row in rows) and not (project / "mkdocs.yml").is_file():
            warnings.append("a docs output but no mkdocs.yml")
    ignored = (project / ".gitignore").read_text(encoding="utf-8") if (project / ".gitignore").is_file() else ""
    if publishing.is_file() and not ignored.strip():
        warnings.append("outputs but no .gitignore for their build folder")
    if WORKFLOW.name in "".join(p.read_text(encoding="utf-8", errors="replace")
                                for p in [project / "AGENTS.md"] if p.is_file()):
        warnings.append(f"AGENTS.md names the workflow repo ({WORKFLOW.name}); a project never does")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("project", help="the project's repo, relative to this one (../<project>)")
    args = parser.parse_args()
    project = (WORKFLOW / args.project).resolve()
    if not project.is_dir():
        print(f"No such folder: {project}", file=sys.stderr)
        return 1
    errors, warnings = check(project)
    for error in errors:
        print(f"error: {error}")
    for warning in warnings:
        print(f"warning: {warning}")
    print(f"{project.name}: {'meets the contract' if not errors else f'{len(errors)} missing'}"
          f"{f', {len(warnings)} to check' if warnings else ''}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
