import math
import unittest
from datetime import datetime, timedelta

from wordvault.scheduler import (
    apply_review,
    build_queue,
    decayed_proficiency,
    proficiency_from,
    review_priority,
    tier_of,
)


def fresh_state(now: datetime, **overrides) -> dict:
    state = {
        "reps": 0,
        "correct": 0,
        "streak": 0,
        "lapses": 0,
        "acc_ema": 0.0,
        "ease": 2.5,
        "interval_days": 0.0,
        "due_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "last_reviewed_at": None,
        "proficiency": 0.0,
    }
    state.update(overrides)
    return state


class ProficiencyTests(unittest.TestCase):
    def test_bounds(self):
        self.assertAlmostEqual(proficiency_from(1.0, 60, 0), 1.0)
        self.assertEqual(proficiency_from(0.0, 0, 5), 0.0)
        self.assertGreaterEqual(proficiency_from(2.0, 999, 0), 0.0)
        self.assertLessEqual(proficiency_from(2.0, 999, 0), 1.0)

    def test_tiers(self):
        self.assertEqual(tier_of(0.0), "生疏")
        self.assertEqual(tier_of(0.36), "学习中")
        self.assertEqual(tier_of(0.61), "熟练")
        self.assertEqual(tier_of(0.86), "已掌握")

    def test_decay_half_life(self):
        now = datetime(2026, 8, 13, 12, 0, 0)
        last = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        state = fresh_state(
            now,
            reps=5,
            proficiency=1.0,
            interval_days=10.0,
            last_reviewed_at=last,
        )
        expected = math.exp(-math.log(2) * 10 / 15)
        self.assertAlmostEqual(decayed_proficiency(state, now), expected, places=4)

    def test_decay_zero_for_new_words(self):
        now = datetime(2026, 8, 13)
        self.assertEqual(decayed_proficiency(fresh_state(now), now), 0.0)


class IntervalTests(unittest.TestCase):
    def test_correct_ladder(self):
        now = datetime(2026, 8, 13, 8, 0, 0)
        state = fresh_state(now)
        expected = [1, 2, 4, 8, 15]
        for i, interval in enumerate(expected, start=1):
            state = apply_review(state, "correct", now)
            self.assertEqual(state["interval_days"], interval)
            self.assertEqual(state["streak"], i)

    def test_wrong_resets(self):
        now = datetime(2026, 8, 13, 8, 0, 0)
        state = fresh_state(now)
        state = apply_review(state, "correct", now)
        state = apply_review(state, "correct", now)
        state = apply_review(state, "wrong", now)
        self.assertEqual(state["interval_days"], 1.0)
        self.assertEqual(state["streak"], 0)
        self.assertEqual(state["lapses"], 1)

    def test_ema_and_proficiency_growth(self):
        now = datetime(2026, 8, 13, 8, 0, 0)
        state = fresh_state(now)
        state = apply_review(state, "correct", now)
        self.assertAlmostEqual(state["acc_ema"], 1.0)
        state = apply_review(state, "wrong", now)
        self.assertAlmostEqual(state["acc_ema"], 0.75)
        for _ in range(6):
            state = apply_review(state, "correct", now)
        self.assertGreater(state["proficiency"], 0.35)


class PriorityTests(unittest.TestCase):
    def test_unfamiliar_and_overdue_wins(self):
        now = datetime(2026, 8, 13, 12, 0, 0)
        stale_due = (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
        unfamiliar = fresh_state(
            now,
            reps=2,
            proficiency=0.2,
            interval_days=3.0,
            due_at=stale_due,
            last_reviewed_at=stale_due,
        )
        mastered = fresh_state(
            now,
            reps=12,
            proficiency=0.95,
            interval_days=60.0,
            due_at=now.strftime("%Y-%m-%d %H:%M:%S"),
            last_reviewed_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.assertGreater(
            review_priority(unfamiliar, now), review_priority(mastered, now)
        )

    def test_long_overdue_mastered_eventually_surfaces(self):
        now = datetime(2026, 8, 13, 12, 0, 0)
        due_200d = (now - timedelta(days=200)).strftime("%Y-%m-%d %H:%M:%S")
        mastered_old = fresh_state(
            now,
            reps=15,
            proficiency=0.95,
            interval_days=60.0,
            due_at=due_200d,
            last_reviewed_at=due_200d,
        )
        fresh_due = fresh_state(
            now,
            reps=1,
            proficiency=0.05,
            interval_days=1.0,
            due_at=now.strftime("%Y-%m-%d %H:%M:%S"),
            last_reviewed_at=(now - timedelta(days=1)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        )
        self.assertGreater(
            review_priority(mastered_old, now), review_priority(fresh_due, now)
        )


class StubDb:
    def __init__(self, new_rows, due_rows):
        self.new_rows = new_rows
        self.due_rows = due_rows

    def get_pending_new(self, limit):
        return self.new_rows[:limit]

    def get_due_reviews(self):
        return self.due_rows


class QueueTests(unittest.TestCase):
    def test_limits_and_new_first(self):
        now = datetime(2026, 8, 13, 12, 0, 0)
        new_rows = [
            {"word_id": 1},
            {"word_id": 2},
            {"word_id": 3},
        ]
        due_rows = [
            {
                "word_id": 11,
                "reps": 1,
                "proficiency": 0.2,
                "interval_days": 1.0,
                "due_at": (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                "last_reviewed_at": (now - timedelta(days=2)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            },
            {
                "word_id": 12,
                "reps": 1,
                "proficiency": 0.2,
                "interval_days": 1.0,
                "due_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "last_reviewed_at": (now - timedelta(days=1)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            },
        ]
        db = StubDb(new_rows, due_rows)
        queue = build_queue(db, new_limit=2, total_limit=3, now=now)
        self.assertEqual(queue["new"], [1, 2])
        self.assertEqual(queue["review"], [11])

    def test_new_words_not_starved_when_review_backlog(self):
        now = datetime(2026, 8, 13, 12, 0, 0)
        db = StubDb(
            [{"word_id": 1}],
            [
                {
                    "word_id": i,
                    "reps": 1,
                    "proficiency": 0.1,
                    "interval_days": 1.0,
                    "due_at": (now - timedelta(days=10)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "last_reviewed_at": (now - timedelta(days=11)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
                for i in range(100, 200)
            ],
        )
        queue = build_queue(db, new_limit=5, total_limit=30, now=now)
        self.assertEqual(queue["new"], [1])
        self.assertEqual(len(queue["review"]), 29)
        self.assertLessEqual(len(queue["new"]) + len(queue["review"]), 30)


if __name__ == "__main__":
    unittest.main()
