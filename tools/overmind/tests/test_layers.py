"""The package's layers, from the bottom: `core` imports only itself; each feature (`runner`, `dashboard`,
`memory`) imports only `core` and itself; `cli`, the only interface, may import anything and nothing imports it.
`memory` stands alone: it does not even import `core`."""

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


FEATURES = ("runner", "dashboard", "memory")


def top(module):
    return module.split(".")[0]


class LayerTests(unittest.TestCase):
    def check(self, folder, allowed):
        files = [PACKAGE / f"{folder}.py"] if (PACKAGE / f"{folder}.py").is_file() else (PACKAGE / folder).rglob("*.py")
        for path in files:
            with self.subTest(path=str(path.relative_to(PACKAGE))):
                self.assertEqual({m for m in imports(path) if m and top(m) not in allowed}, set())

    def test_core_imports_only_itself(self):
        self.check("core", {"core"})

    def test_each_feature_imports_only_core_and_itself(self):
        for feature in FEATURES:
            self.check(feature, {"core", feature})

    def test_memory_does_not_even_import_core(self):
        self.check("memory", {"memory"})

    def test_every_module_belongs_to_a_layer(self):
        layers = {"core", "cli", *FEATURES}
        loose = {path.relative_to(PACKAGE).parts[0] for path in PACKAGE.rglob("*.py")} - layers - {"__init__.py"}
        self.assertEqual(loose, set())


if __name__ == "__main__":
    unittest.main()
