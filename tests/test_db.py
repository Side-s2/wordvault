import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from wordvault.db import Database, Example, Meaning


class DbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_add_duplicate_and_search(self):
        w = self.db.add_word(
            "Apple",
            phonetic="[ˈæpl]",
            meanings=[Meaning(pos="n.", text="苹果")],
            examples=[Example(en="I like apples.", zh="我喜欢苹果。")],
            source="offline",
        )
        self.assertIsNotNone(w)
        self.assertIsNone(self.db.add_word("apple", meanings=[Meaning("n.", "苹果")]))
        self.assertEqual(self.db.count_words(), 1)
        found = self.db.search_words("苹果")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].word, "Apple")

    def test_created_at_recorded(self):
        before = datetime.now()
        w = self.db.add_word("test", meanings=[Meaning("n.", "测试")])
        after = datetime.now()
        created = datetime.fromisoformat(w.created_at)
        self.assertLess(abs((created - before).total_seconds()), 2)
        self.assertLess(abs((after - created).total_seconds()), 2)

    def test_update_and_delete_cascade(self):
        w = self.db.add_word("run", meanings=[Meaning("v.", "跑")])
        ok = self.db.update_word(
            w.id,
            "run",
            "/rʌn/",
            [Meaning("v.", "奔跑"), Meaning("n.", "跑步")],
            [],
        )
        self.assertTrue(ok)
        self.assertEqual(len(self.db.get_word(w.id).meanings), 2)
        self.assertTrue(self.db.delete_word(w.id))
        self.assertIsNone(self.db.get_word(w.id))

    def test_review_log_and_volume(self):
        w = self.db.add_word("go", meanings=[Meaning("v.", "去")])
        state = self.db.ensure_state(w.id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state.update(
            reps=1,
            correct=1,
            streak=1,
            acc_ema=1.0,
            interval_days=1.0,
            due_at=(datetime.now() + timedelta(days=1)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            last_reviewed_at=now,
            proficiency=0.3,
        )
        self.db.save_review(
            w.id, state, "correct", "去", "去", 800, "choice", now
        )
        volume = self.db.total_volume()
        self.assertEqual(volume["total"], 1)
        self.assertEqual(volume["correct"], 1)
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(self.db.day_counts(today)["reviews"], 1)

    def test_distribution_and_due_overview(self):
        w1 = self.db.add_word("a1", meanings=[Meaning("n.", "一")])
        w2 = self.db.add_word("a2", meanings=[Meaning("n.", "二")])
        self.db.ensure_state(w1.id)
        self.db.ensure_state(w2.id)
        dist = self.db.proficiency_distribution()
        self.assertEqual(dist["未开始"], 2)
        overview = self.db.due_overview()
        self.assertEqual(overview["new_today"], 2)

    def test_settings_defaults(self):
        self.assertEqual(self.db.get_setting("new_daily_limit"), "20")
        self.assertEqual(self.db.get_int_setting("new_daily_limit"), 20)
        self.db.set_setting("new_daily_limit", "30")
        self.assertEqual(self.db.get_int_setting("new_daily_limit"), 30)

    def test_export_import_roundtrip_merge(self):
        self.db.add_word(
            "hello",
            meanings=[Meaning("int.", "你好")],
            examples=[Example("Hello!", "你好！")],
            source="offline",
        )
        payload = self.db.export_payload()
        db2 = Database(Path(self.tmp.name) / "test2.db")
        stats = db2.import_payload(payload, mode="merge")
        self.assertEqual(stats["added"], 1)
        self.assertEqual(db2.count_words(), 1)
        self.assertEqual(db2.get_word(1).examples[0].zh, "你好！")
        db2.close()

    def test_import_replace_clears_first(self):
        self.db.add_word("old", meanings=[Meaning("adj.", "旧的")])
        payload = {
            "words": [
                {
                    "id": 1,
                    "word": "new",
                    "phonetic": "",
                    "meanings": json.dumps([{"pos": "adj.", "text": "新的"}]),
                    "examples": "[]",
                    "source": "manual",
                    "created_at": "2026-08-13 10:00:00",
                    "updated_at": "2026-08-13 10:00:00",
                }
            ],
            "states": [],
            "logs": [],
        }
        stats = self.db.import_payload(payload, mode="replace")
        self.assertEqual(stats["added"], 1)
        self.assertEqual(self.db.count_words(), 1)
        self.assertEqual(self.db.list_words()[0].word, "new")

    def test_import_merge_skips_conflicting_rows_safely(self):
        self.db.add_word("hello", meanings=[Meaning("int.", "你好")])
        payload = {
            "words": [
                {
                    "id": 99,
                    "word": "hello",
                    "phonetic": "",
                    "meanings": "[]",
                    "examples": "[]",
                    "source": "manual",
                    "created_at": "2026-08-13 10:00:00",
                    "updated_at": "2026-08-13 10:00:00",
                }
            ],
            "states": [{"word_id": 99, "reps": 1}],
            "logs": [{"id": 1, "word_id": 99, "reviewed_at": "2026-08-13 10:00:00"}],
        }
        stats = self.db.import_payload(payload, mode="merge")
        self.assertEqual(stats["added"], 0)
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(self.db.count_words(), 1)


if __name__ == "__main__":
    unittest.main()
