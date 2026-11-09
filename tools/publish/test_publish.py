"""Verify the publisher reads a project's outputs and builds its menu pages."""

import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.publish import publish as publisher
from tools.publish.publish import project_menu, index, outputs, publish, title


class FakeServer:
    """Records uploads and deletions; holds projects.json."""
    url = "https://server"

    def __init__(self, projects=None):
        self.projects = projects or {}
        self.uploaded, self.deleted, self.calls = [], [], 0

    def upload(self, folder, slug, name):
        self.calls += 1
        self.uploaded.append(name)
        return 1

    def request(self, method, path, data=None, headers=None, missing_ok=False):
        self.calls += 1
        if method == "GET" and path == "/projects.json":
            return json.dumps(self.projects).encode()
        if method == "DELETE":
            self.deleted.append(path)
        return b""

    def put(self, path, data):
        self.calls += 1
        if path == "/projects.json":
            self.projects = json.loads(data)


class PublishTests(unittest.TestCase):
    def test_outputs_and_title_come_from_the_project_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            (app / '.agents/context').mkdir(parents=True)
            (app / '.agents/context/publishing.md').write_text(
                '| Output | Prepared files |\n|---|---|\n'
                '| app | `artifacts/artifact-site/` (`tools/package_artifact.py`) |\n'
                '| Docs | `artifacts/docs-site/` |\n'
                '| review | built elsewhere |\n')
            (app / 'AGENTS.md').write_text('# A Little App: agent notes\n')
            self.assertEqual(outputs(app), {'app': app / 'artifacts/artifact-site/',
                                            'docs': app / 'artifacts/docs-site/'})
            self.assertEqual(title(app), 'A Little App')

    def test_menus_link_each_output_and_mocks(self):
        entry = {'title': 'Notes & Tasks', 'outputs': ['app', 'mocks'], 'published': '2026-10-22 16:00'}
        menu = project_menu('notes', entry)
        self.assertIn('<a href="app/">App</a>', menu)
        self.assertIn('<a href="mocks/">Mocks</a>', menu)
        self.assertNotIn('docs/', menu)
        self.assertIn('Notes &amp; Tasks', menu)
        self.assertIn('<a href="notes/">Notes &amp; Tasks</a>', index({'notes': entry}))



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

    def mock(self, cycle='2026-10-27-next', name='2026-10-27-look'):
        folder = self.root / '.scratch/project' / cycle / 'mocks' / name
        folder.mkdir(parents=True)
        (folder / 'index.html').write_text('<p>')

    def test_nothing_to_publish_never_contacts_the_server(self):
        server = FakeServer()
        self.assertEqual(publish(self.project, None, server, self.staging), 0)
        self.assertEqual(publish(self.project, ['mocks'], server, self.staging), 0)
        self.assertEqual(server.calls, 0)

    def test_a_symlink_in_an_output_stops_before_uploading(self):
        self.prepare('app')
        secret = self.root / 'secret'
        secret.write_text('key')
        (self.project / 'out/app/key.txt').symlink_to(secret)
        server = FakeServer()
        with self.assertRaises(SystemExit):
            publish(self.project, None, server, self.staging)
        self.assertEqual(server.uploaded, [])

    def test_a_symlink_in_a_mock_stops_before_uploading(self):
        self.mock()
        secret = self.root / 'secret'
        secret.write_text('key')
        (self.root / '.scratch/project/2026-10-27-next/mocks/2026-10-27-look/key.txt').symlink_to(secret)
        server = FakeServer()
        with self.assertRaises(SystemExit):
            publish(self.project, ['mocks'], server, self.staging)
        self.assertEqual(server.uploaded, [])

    def test_the_review_publishes_mocks_and_keeps_the_build(self):
        self.prepare('app', 'docs')
        self.mock()
        server = FakeServer({'project': {'outputs': ['app', 'docs'], 'title': 'Project'}})
        self.assertEqual(publish(self.project, ['mocks'], server, self.staging), 0)
        self.assertEqual(server.uploaded, ['mocks'])
        self.assertEqual(server.deleted, [])
        self.assertEqual(server.projects['project']['outputs'], ['app', 'docs', 'mocks'])

    def test_the_build_publishes_its_outputs_and_keeps_the_mocks(self):
        self.prepare('docs')
        server = FakeServer({'project': {'outputs': ['app', 'docs', 'mocks'], 'title': 'Project'}})
        self.assertEqual(publish(self.project, None, server, self.staging), 0)
        self.assertEqual(server.uploaded, ['docs'])
        self.assertEqual(server.deleted, ['/project/app/'])
        self.assertEqual(server.projects['project']['outputs'], ['docs', 'mocks'])

    def test_any_output_name_is_published_and_listed(self):
        self.prepare('docs', 'examples')
        server = FakeServer({'project': {'outputs': ['docs', 'mocks'], 'title': 'Project'}})
        self.assertEqual(publish(self.project, None, server, self.staging), 0)
        self.assertEqual(server.uploaded, ['docs', 'examples'])
        self.assertEqual(server.projects['project']['outputs'],
                         ['docs', 'examples', 'mocks'])
        self.assertIn('<a href="examples/">Examples</a>', project_menu('project', server.projects['project']))

    def test_without_a_server_it_stops_before_uploading(self):
        self.prepare('docs')
        self.assertEqual(publish(self.project, None, None, self.staging), 1)

    def test_the_server_comes_from_the_environment_or_dotenv(self):
        with patch.dict('os.environ', {}, clear=True), patch.object(publisher, 'WORKFLOW', self.root):
            self.assertIsNone(publisher.server_url())
            (self.root / '.env').write_text('# local\nPUBLISH_URL="https://from.env"\n')
            self.assertEqual(publisher.server_url(), 'https://from.env')
        with patch.dict('os.environ', {'PUBLISH_URL': 'https://from.environment'}):
            self.assertEqual(publisher.server_url(), 'https://from.environment')

    def test_every_cycle_in_review_publishes_its_mocks(self):
        self.mock('2026-10-20-built', '2026-10-20-old')
        (self.root / '.scratch/project/2026-10-20-built/issues').mkdir()
        (self.root / '.scratch/project/2026-10-20-built/issues/01-a.md').write_text('# A')
        self.mock('2026-10-27-balance', '2026-10-28-cards')
        self.mock('2026-10-29-research', '2026-10-29-chart')
        server = FakeServer()
        self.assertEqual(publish(self.project, ['mocks'], server, self.staging), 0)
        out = self.staging / 'mocks'
        self.assertTrue((out / '2026-10-27-balance/2026-10-28-cards/index.html').is_file())
        self.assertTrue((out / '2026-10-29-research/2026-10-29-chart/index.html').is_file())
        self.assertFalse((out / '2026-10-20-built').exists())
        menu = (out / 'index.html').read_text()
        self.assertLess(menu.index('2026-10-29-research'), menu.index('2026-10-27-balance'))

    def test_a_project_without_mocks_publishes_none(self):
        self.prepare('docs')
        (self.root / '.scratch/project/2026-10-27-next').mkdir(parents=True)
        server = FakeServer()
        self.assertEqual(publish(self.project, ['mocks'], server, self.staging), 0)
        self.assertEqual(server.calls, 0)

    def test_the_documented_command_runs_as_a_script(self):
        script = Path(publisher.__file__)
        result = subprocess.run([sys.executable, script, '--help'], cwd=publisher.WORKFLOW,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
