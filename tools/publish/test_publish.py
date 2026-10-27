"""Verify the publisher reads a game's outputs and builds its menu pages."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.publish import publish as publisher
from tools.publish.publish import game_menu, index, outputs, publish, title


class FakeServer:
    """Records uploads and deletions; holds games.json."""
    url = "https://server"

    def __init__(self, games=None):
        self.games = games or {}
        self.uploaded, self.deleted, self.calls = [], [], 0

    def upload(self, folder, slug, name):
        self.calls += 1
        self.uploaded.append(name)
        return 1

    def request(self, method, path, data=None, headers=None, missing_ok=False):
        self.calls += 1
        if method == "GET" and path == "/games.json":
            return json.dumps(self.games).encode()
        if method == "DELETE":
            self.deleted.append(path)
        return b""

    def put(self, path, data):
        self.calls += 1
        if path == "/games.json":
            self.games = json.loads(data)


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



class PublishRunTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / 'project'
        (self.project / '.agents/context').mkdir(parents=True)
        (self.project / 'AGENTS.md').write_text('# Project: agent notes\n')
        self.staging = self.root / 'staging'
        self.staging.mkdir()
        patcher = patch.object(publisher, 'WORKFLOW', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def prepare(self, *names):
        rows = ''.join(f'| {name} | `out/{name}/` |\n' for name in names)
        (self.project / '.agents/context/publishing.md').write_text(rows)
        for name in names:
            (self.project / 'out' / name).mkdir(parents=True)
            (self.project / 'out' / name / 'index.html').write_text('<p>')

    def mock(self):
        folder = self.root / '.scratch/project/2026-10-27-next/mocks/2026-10-27-look'
        folder.mkdir(parents=True)
        (folder / 'index.html').write_text('<p>')

    def test_nothing_to_publish_never_contacts_the_server(self):
        server = FakeServer()
        self.assertEqual(publish(self.project, ['game', 'docs'], server, self.staging), 0)
        self.assertEqual(publish(self.project, ['mocks'], server, self.staging), 0)
        self.assertEqual(server.calls, 0)

    def test_the_review_publishes_mocks_and_keeps_the_build(self):
        self.prepare('game', 'docs')
        self.mock()
        server = FakeServer({'project': {'outputs': ['game', 'docs'], 'title': 'Project'}})
        self.assertEqual(publish(self.project, ['mocks'], server, self.staging), 0)
        self.assertEqual(server.uploaded, ['mocks'])
        self.assertEqual(server.deleted, [])
        self.assertEqual(server.games['project']['outputs'], ['game', 'docs', 'mocks'])

    def test_the_build_publishes_its_outputs_and_keeps_the_mocks(self):
        self.prepare('docs')
        server = FakeServer({'project': {'outputs': ['game', 'docs', 'mocks'], 'title': 'Project'}})
        self.assertEqual(publish(self.project, ['game', 'docs'], server, self.staging), 0)
        self.assertEqual(server.uploaded, ['docs'])
        self.assertEqual(server.deleted, ['/project/game/'])
        self.assertEqual(server.games['project']['outputs'], ['docs', 'mocks'])

    def test_a_project_without_mocks_publishes_none(self):
        self.prepare('docs')
        (self.root / '.scratch/project/2026-10-27-next').mkdir(parents=True)
        server = FakeServer()
        self.assertEqual(publish(self.project, ['mocks'], server, self.staging), 0)
        self.assertEqual(server.calls, 0)


if __name__ == '__main__':
    unittest.main()
