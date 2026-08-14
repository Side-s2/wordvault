"""数据库层：清空数据与云端合并导入的单元测试。"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from wordvault.db import Database, Meaning


def _state_payload(
    word_id: int,
    reps: int = 1,
    due_days: int = 1,
    reviewed_days_ago: int = 0,
) -> dict:
    now = datetime.now()
    return {
        "word_id": word_id,
        "reps": reps,
        "correct": reps,
        "streak": reps,
        "lapses": 0,
        "acc_ema": 1.0,
        "ease": 2.5,
        "interval_days": float(due_days),
        "due_at": (now + timedelta(days=due_days)).strftime("%Y-%m-%d %H:%M:%S"),
        "last_reviewed_at": (
            now - timedelta(days=reviewed_days_ago)
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "proficiency": 0.5,
    }


class CloudSyncDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_delete_all_data_keeps_settings(self):
        w = self.db.add_word("apple", meanings=[Meaning("n.", "苹果")])
        self.db.set_setting("theme_mode", "dark")
        state = self.db.ensure_state(w.id)
        state.update(**_state_payload(w.id))
        self.db.save_review(
            w.id, state, "correct", "苹果", "苹果", 600, "choice",
            state["last_reviewed_at"],
        )
        stats = self.db.delete_all_data()
        self.assertEqual(stats["words"], 1)
        self.assertEqual(stats["logs"], 1)
        self.assertEqual(self.db.count_words(), 0)
        self.assertEqual(self.db.total_volume()["total"], 0)
        self.assertEqual(self.db.get_setting("theme_mode"), "dark")

    def test_sync_remaps_cross_device_ids(self):
        local = self.db.add_word("apple", meanings=[Meaning("n.", "苹果")])
        self.db.add_word("cherry", meanings=[Meaning("n.", "樱桃")])
        payload = {
            "words": [
                {
                    "id": 10,
                    "word": "apple",
                    "phonetic": "/ˈæpl/",
                    "meanings": json.dumps(
                        [{"pos": "n.", "text": "苹果（云端）"}]
                    ),
                    "examples": "[]",
                    "source": "manual",
                    "created_at": "2026-08-01 10:00:00",
                    "updated_at": "2026-08-02 10:00:00",
                },
                {
                    "id": 11,
                    "word": "banana",
                    "phonetic": "",
                    "meanings": json.dumps([{"pos": "n.", "text": "香蕉"}]),
                    "examples": "[]",
                    "source": "manual",
                    "created_at": "2026-08-01 10:00:00",
                    "updated_at": "2026-08-01 10:00:00",
                },
            ],
            "states": [
                _state_payload(10, reps=3, due_days=2),
                _state_payload(11, reps=1, due_days=1),
            ],
            "logs": [
                {
                    "id": 100,
                    "word_id": 10,
                    "reviewed_at": "2026-08-10 10:00:00",
                    "result": "correct",
                    "answer": "",
                    "correct_answer": "",
                    "ms": 500,
                    "proficiency_after": 0.6,
                    "interval_after": 2.0,
                    "mode": "choice",
                }
            ],
        }
        stats = self.db.import_payload(payload, mode="sync")
        self.assertEqual(stats["added"], 1)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(stats["logs"], 1)

        apple = self.db.get_word(local.id)
        self.assertEqual(apple.phonetic, "/ˈæpl/")
        self.assertEqual(apple.meanings[0].text, "苹果（云端）")

        banana = next(w for w in self.db.list_words() if w.word == "banana")
        self.assertNotEqual(banana.id, 11)
        self.assertEqual(self.db.ensure_state(banana.id)["reps"], 1)

        # 本地独有的词不受影响
        self.assertEqual(self.db.count_words(), 3)

        # 重复导入不重复写复习日志
        again = self.db.import_payload(payload, mode="sync")
        self.assertEqual(again["logs"], 0)
        self.assertEqual(self.db.total_volume()["total"], 1)


if __name__ == "__main__":
    unittest.main()
