"""Verify debt appears from its source register and keeps working board links."""

from pathlib import Path
import tempfile
import unittest

from tools.review.render_review import Board


class DebtBoardTests(unittest.TestCase):
    def test_register_supplies_review_and_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cycle = root / '2026-10-22-test'
            (cycle / 'issues').mkdir(parents=True)
            (cycle / 'issues/01-feature.md').write_text('# Feature\n')
            (cycle / 'review.md').write_text('# Review\n\n## Code debt\n\nStale summary\n\n## Feedback\n\nUser feedback\n')
            (cycle / 'debt.md').write_text('# Register\n\nD01: Extract simulation work. [Source](issues/01-feature.md)\n')
            board = Board(root, root, {})
            board.build()
            self.assertIn('debt', board.pages)
            review = board.rewritten(board.pages['review'])
            self.assertIn('D01: Extract simulation work.', review)
            self.assertNotIn('Stale summary', review)
            self.assertIn('## Feedback\n\nUser feedback', review)
            self.assertIn('[Source](#issues/01-feature)', review)
            self.assertEqual(list(board.warnings()), [])
            self.assertIn({'key': 'debt', 'label': 'Code debt'}, board.tree[0]['children'])
            (cycle / 'debt.md').write_text('# Register\n\nD01: resolved\n')
            updated = Board(root, root, {})
            updated.build()
            self.assertIn('D01: resolved', updated.pages['review'].text)
            self.assertNotIn('Extract simulation work', updated.pages['review'].text)

    def test_existing_cycles_without_register_keep_their_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cycle = root / '2026-10-22-test'
            cycle.mkdir()
            text = '# Review\n\n## Code debt\n\nExisting findings\n'
            (cycle / 'review.md').write_text(text)
            board = Board(root, root, {})
            board.build()
            self.assertEqual(board.pages['review'].text, text)
            self.assertNotIn('debt', board.pages)


if __name__ == '__main__':
    unittest.main()
