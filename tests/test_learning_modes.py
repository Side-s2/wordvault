"""学习类型（阅读/写作）、题型判定与拼写槽位的单元测试。"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from wordvault.db import Database, Meaning
from wordvault.scheduler import question_kind, tier_of
from wordvault.views.review_view import ReviewView


class _Page:
    def update(self):
        return None


class _Ctx:
    def __init__(self, db):
        self.page = _Page()
        self.db = db


class LearningModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_add_word_defaults_to_write_mode(self):
        w = self.db.add_word("apple", meanings=[Meaning("n.", "苹果")])
        self.assertEqual(w.learn_mode, "write")

    def test_update_word_changes_mode(self):
        w = self.db.add_word("apple", meanings=[Meaning("n.", "苹果")])
        self.db.update_word(
            w.id, "apple", "", [Meaning("n.", "苹果")], [], "read"
        )
        self.assertEqual(self.db.get_word(w.id).learn_mode, "read")

    def test_import_preserves_learn_mode(self):
        self.db.add_word(
            "banana", meanings=[Meaning("n.", "香蕉")], learn_mode="read"
        )
        payload = self.db.export_payload()
        db2 = Database(Path(self.tmp.name) / "t2.db")
        db2.import_payload(payload, mode="merge")
        self.assertEqual(db2.list_words()[0].learn_mode, "read")
        db2.close()

    def test_migration_adds_column_with_write_default(self):
        path = Path(self.tmp.name) / "old.db"
        conn = sqlite3.connect(str(path))
        conn.executescript(
            """
            CREATE TABLE words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE COLLATE NOCASE,
                phonetic TEXT NOT NULL DEFAULT '',
                meanings TEXT NOT NULL DEFAULT '[]',
                examples TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO words(word, phonetic, meanings, examples, source,
                              created_at, updated_at)
            VALUES ('old', '', '[]', '[]', 'manual', '2026-01-01 00:00:00',
                    '2026-01-01 00:00:00');
            """
        )
        conn.commit()
        conn.close()
        migrated = Database(path)
        self.assertEqual(migrated.list_words()[0].learn_mode, "write")
        migrated.close()


class QuestionKindTests(unittest.TestCase):
    def test_question_kind_stages(self):
        self.assertEqual(question_kind("write", 0), "choice")
        self.assertEqual(question_kind("write", 1), "choice")
        self.assertEqual(question_kind("write", 2), "spell")
        self.assertEqual(question_kind("read", 5), "choice")

    def test_write_mastery_threshold(self):
        self.assertEqual(tier_of(0.88, "read"), "已掌握")
        self.assertEqual(tier_of(0.88, "write"), "熟练")
        self.assertEqual(tier_of(0.91, "write"), "已掌握")


class SpellSlotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")
        self.view = ReviewView(_Ctx(self.db))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_build_units_and_fill(self):
        self.view._build_spell_units("mother-in-law")
        slots = [u for u in self.view.spell_units if u["kind"] == "slot"]
        fixed = [u for u in self.view.spell_units if u["kind"] == "fixed"]
        self.assertEqual(len(slots), 11)
        self.assertEqual([u["ch"] for u in fixed], ["-", "-"])
        for ch in "motherinlaw":
            self.view._fill_next_slot(ch)
        self.assertTrue(self.view._all_slots_filled())
        self.view._clear_last_slot()
        self.assertFalse(self.view._all_slots_filled())

    def test_spell_flow_marks_correct(self):
        w = self.db.add_word(
            "cat", meanings=[Meaning("n.", "猫")], learn_mode="write"
        )
        with self.db._lock:
            self.db._conn.execute(
                "UPDATE learning_state SET reps=2 WHERE word_id=?", (w.id,)
            )
            self.db._conn.commit()
        self.view.queue = [w.id]
        self.view.index = 0
        self.view._render_question()
        self.assertEqual(self.view.question_mode, "spell")
        for ch in "cat":
            self.view._fill_next_slot(ch)
        self.view.submit_spell()
        self.assertTrue(self.view.answered)
        self.assertEqual(self.view.correct_cnt, 1)


if __name__ == "__main__":
    unittest.main()
