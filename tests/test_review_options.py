"""复习页四选一选项构造的单元测试。"""

import tempfile
import unittest
from pathlib import Path

from wordvault.db import Database, Meaning
from wordvault.views.review_view import ReviewView


class _Page:
    def update(self):
        return None


class _Ctx:
    def __init__(self, db):
        self.page = _Page()
        self.db = db


class ReviewOptionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")
        self.view = ReviewView(_Ctx(self.db))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _seed_multi(self):
        self.db.add_word(
            "apple", meanings=[Meaning("n.", "苹果"), Meaning("n.", "苹果树")]
        )
        self.db.add_word(
            "run", meanings=[Meaning("v.", "奔跑"), Meaning("n.", "跑步")]
        )
        self.db.add_word(
            "book", meanings=[Meaning("n.", "书籍"), Meaning("v.", "预订")]
        )
        self.db.add_word(
            "water", meanings=[Meaning("n.", "水"), Meaning("v.", "浇水")]
        )
        self.db.add_word(
            "school", meanings=[Meaning("n.", "学校"), Meaning("n.", "学派")]
        )
        return next(w for w in self.db.list_words() if w.word == "apple")

    def test_options_homogeneous_and_correct_complete(self):
        word = self._seed_multi()
        options = self.view._make_options(word)
        self.assertEqual(len(options), 4)
        correct = "n. 苹果；n. 苹果树"
        self.assertIn(correct, options)
        correct_texts = {m.text for m in word.meanings}
        for option in options:
            if option == correct:
                continue
            parts = option.split("；")
            self.assertEqual(len(parts), 2)
            for part in parts:
                self.assertIn(" ", part)
            for text in correct_texts:
                self.assertNotIn(text, option)
        self.assertEqual(len(set(options)), 4)

    def test_single_meaning_target_uses_single_part_distractors(self):
        self.db.add_word("go", meanings=[Meaning("v.", "去")])
        self.db.add_word("come", meanings=[Meaning("v.", "来")])
        self.db.add_word("sit", meanings=[Meaning("v.", "坐")])
        self.db.add_word("stand", meanings=[Meaning("v.", "站立")])
        word = next(w for w in self.db.list_words() if w.word == "go")
        options = self.view._make_options(word)
        self.assertEqual(len(options), 4)
        self.assertIn("v. 去", options)
        self.assertTrue(all("；" not in option for option in options))

    def test_missing_meanings_returns_none(self):
        word = self.db.add_word("zzz", meanings=[])
        self.assertIsNone(self.view._make_options(word))


if __name__ == "__main__":
    unittest.main()
