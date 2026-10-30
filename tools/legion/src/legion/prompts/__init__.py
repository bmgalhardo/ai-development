"""The session prompts, one template file per role: implement, review and fix."""

from pathlib import Path


class Prompts:
    folder = Path(__file__).parent

    def render(self, role, **values):
        """The role's prompt, with `{name}` placeholders filled from the values."""
        return (self.folder / f"{role}.txt").read_text(encoding="utf-8").strip().format(**values)
