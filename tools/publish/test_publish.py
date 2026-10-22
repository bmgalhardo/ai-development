"""Verify the publisher reads a game's outputs and builds its menu pages."""

from pathlib import Path
import tempfile
import unittest

from tools.publish.publish import game_menu, index, outputs, title


class PublishTests(unittest.TestCase):
    def test_outputs_and_title_come_from_the_game_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / '.agents/context').mkdir(parents=True)
            (game / '.agents/context/publishing.md').write_text(
                '| Output | Prepared files |\n|---|---|\n'
                '| game | `artifacts/artifact-site/` (`tools/package_artifact.py`) |\n'
                '| Docs | `artifacts/docs-site/` |\n'
                '| review | built elsewhere |\n')
            (game / 'AGENTS.md').write_text('# A Little Sky Time: agent notes\n')
            self.assertEqual(outputs(game), {'game': game / 'artifacts/artifact-site/',
                                             'docs': game / 'artifacts/docs-site/'})
            self.assertEqual(title(game), 'A Little Sky Time')

    def test_menus_link_each_output_and_game(self):
        entry = {'title': 'Sky & Time', 'outputs': ['game', 'mocks'], 'published': '2026-10-22 16:00'}
        menu = game_menu('sky', entry)
        self.assertIn('<a href="game/">Game</a>', menu)
        self.assertIn('<a href="mocks/">Mocks</a>', menu)
        self.assertNotIn('docs/', menu)
        self.assertIn('Sky &amp; Time', menu)
        self.assertIn('<a href="sky/">Sky &amp; Time</a>', index({'sky': entry}))


if __name__ == '__main__':
    unittest.main()
