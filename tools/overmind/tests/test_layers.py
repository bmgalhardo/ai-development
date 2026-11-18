"""The package's layers: `cli` is the only interface, and `memory` stands alone."""

import ast
from pathlib import Path
import unittest

PACKAGE = Path(__file__).resolve().parents[1] / "src/overmind"


def imports(path):
    """The overmind modules a file imports, as dotted names relative to the package (`cli`, `memory.store`)."""
    folder = path.relative_to(PACKAGE).parent.parts
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(folder[:len(folder) - node.level + 1])
                found.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module and node.module.startswith("overmind"):
                found.add(node.module.removeprefix("overmind").lstrip("."))
        elif isinstance(node, ast.Import):
            found.update(a.name.removeprefix("overmind").lstrip(".") for a in node.names
                         if a.name.startswith("overmind"))
    return found


class LayerTests(unittest.TestCase):
    def test_nothing_outside_cli_imports_cli(self):
        for path in PACKAGE.rglob("*.py"):
            if path.relative_to(PACKAGE).parts[0] != "cli":
                with self.subTest(path=path.relative_to(PACKAGE)):
                    self.assertFalse({m for m in imports(path) if m == "cli" or m.startswith("cli.")})

    def test_memory_imports_only_itself(self):
        for path in (PACKAGE / "memory").rglob("*.py"):
            with self.subTest(path=path.relative_to(PACKAGE)):
                self.assertEqual({m for m in imports(path) if not m.startswith("memory")}, set())


if __name__ == "__main__":
    unittest.main()
