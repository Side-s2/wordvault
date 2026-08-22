"""阅读页缓存、记录与分段的单元测试。"""

import tempfile
import unittest
from pathlib import Path

from wordvault.db import Database
from wordvault.views.reading_view import ReadingView


class _Page:
    def update(self):
        return None


class _Ctx:
    def __init__(self, db):
        self.page = _Page()
        self.db = db
        self.provider = None

    def snack(self, message, error=False):
        return None


class ReadingDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _article(self, aid, section_id="world", title="T"):
        return {
            "id": aid,
            "title": title,
            "source": "The Guardian",
            "section": "World news",
            "section_id": section_id,
            "url": f"https://example.com/{aid}",
            "body": "x" * 300,
            "published_at": "2026-08-22T00:00:00Z",
        }

    def test_section_filter_and_unopened_clear(self):
        self.db.upsert_article(self._article("a1", "world"))
        self.db.upsert_article(self._article("a2", "culture"))
        self.assertEqual(len(self.db.list_articles("world")), 1)
        self.assertEqual(len(self.db.list_articles()), 2)
        self.db.mark_article_opened("a1")
        removed = self.db.clear_unopened_articles()
        self.assertEqual(removed, 1)
        self.assertEqual(len(self.db.list_articles()), 1)
        self.assertEqual(len(self.db.reading_history()), 1)

    def test_finish_and_delete_record(self):
        self.db.upsert_article(self._article("a1"))
        self.db.mark_article_opened("a1")
        self.db.mark_article_finished("a1")
        self.assertTrue(self.db.get_article("a1")["finished"])
        self.db.delete_article("a1")
        self.assertIsNone(self.db.get_article("a1"))

    def test_paragraph_text_adds_blank_line(self):
        body = (
            "First sentence. Second sentence. Third sentence. "
            "Fourth sentence. Fifth sentence. Sixth sentence."
        )
        text = ReadingView._paragraph_text(body)
        self.assertEqual(text.count("\n\n"), 1)
        self.assertIn("Second sentence.", text)


if __name__ == "__main__":
    unittest.main()
