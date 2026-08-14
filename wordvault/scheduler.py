"""熟练度评估与间隔复习调度算法（改进版 SM-2 + 公平队列）。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from wordvault.db import parse_dt


# 答对 n 次后的复习间隔（天），针对四选一难度设计
INTERVALS = [1, 2, 4, 8, 15, 30, 45, 60, 90, 120, 180, 240, 360]

TIERS = [
    (0.85, "已掌握"),
    (0.60, "熟练"),
    (0.35, "学习中"),
    (-1.0, "生疏"),
]


def tier_of(proficiency: float) -> str:
    for threshold, name in TIERS:
        if proficiency >= threshold:
            return name
    return "生疏"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def proficiency_from(acc_ema: float, interval_days: float, lapses: int) -> float:
    """熟练度 = 近期正确率 × 间隔成长度，再扣少量遗忘惩罚。

    近期正确率用指数加权平均，越近的结果权重越高；
    间隔越长仍保持高正确率，说明记忆越稳定。
    """
    growth = min(interval_days / 60.0, 1.0)
    penalty = min(lapses * 0.03, 0.15)
    return clamp01(acc_ema * (0.70 + 0.30 * growth) - penalty)


def decayed_proficiency(state: dict[str, Any], now: datetime) -> float:
    """当前时刻的熟练度：随时间衰减，体现"太久没出现会变生疏"。"""
    if state.get("reps", 0) <= 0:
        return 0.0
    last_s = state.get("last_reviewed_at")
    if not last_s:
        return 0.0
    last = parse_dt(last_s)
    elapsed_days = max(0.0, (now - last).total_seconds() / 86400.0)
    interval = max(float(state.get("interval_days", 1.0)), 1.0)
    half_life = interval * 1.5
    return state.get("proficiency", 0.0) * math.exp(
        -math.log(2.0) * elapsed_days / half_life
    )


def review_priority(state: dict[str, Any], now: datetime) -> float:
    """到期词的复习优先级：越逾期、越生疏，优先级越高。

    熟练的词刚到期时优先级低，不会抢占生词资源；
    但逾期很久后 urgency 会显著上升，保证它们也能复现。
    """
    due = parse_dt(state["due_at"])
    overdue_days = max(0.0, (now - due).total_seconds() / 86400.0)
    urgency = (overdue_days + 1.0) ** 0.9
    unfamiliarity = 1.0 - decayed_proficiency(state, now)
    return urgency * (unfamiliarity + 0.15)


def apply_review(
    state: dict[str, Any],
    result: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """根据一次复习结果更新学习状态（SM-2 思路）。"""
    now = now or datetime.now()
    st = dict(state)
    correct = result == "correct"

    st["reps"] = int(st.get("reps", 0)) + 1
    st["correct"] = int(st.get("correct", 0)) + (1 if correct else 0)

    if correct:
        st["streak"] = int(st.get("streak", 0)) + 1
        st["ease"] = min(float(st.get("ease", 2.5)) + 0.05, 2.8)
        streak = st["streak"]
        if streak <= len(INTERVALS):
            interval = float(INTERVALS[streak - 1])
        else:
            interval = round(max(float(st.get("interval_days", 1.0)), 1.0) * 1.2)
    else:
        st["streak"] = 0
        st["lapses"] = int(st.get("lapses", 0)) + 1
        st["ease"] = max(float(st.get("ease", 2.5)) - 0.20, 1.3)
        interval = 1.0

    st["interval_days"] = float(interval)
    if st["reps"] == 1:
        ema = 1.0 if correct else 0.0
    else:
        ema = float(st.get("acc_ema", 0.0)) * 0.75 + (1.0 if correct else 0.0) * 0.25
    st["acc_ema"] = ema
    st["proficiency"] = proficiency_from(ema, interval, st["lapses"])
    st["last_reviewed_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    st["due_at"] = (now + timedelta(days=interval)).strftime("%Y-%m-%d %H:%M:%S")
    return st


def build_queue(
    db: Any,
    new_limit: int,
    total_limit: int,
    now: datetime | None = None,
) -> dict[str, list[int]]:
    """构建今日复习队列。

    - 新词独立配额（new_limit），即使复习积压也不会被饿死；
    - 复习词按优先级排序，总数受 total_limit 约束；
    - 超出上限的到期词顺延到以后，不会一次性淹没用户。
    """
    now = now or datetime.now()
    new_limit = max(0, int(new_limit))
    total_limit = max(0, int(total_limit))

    new_rows = db.get_pending_new(new_limit)
    new_ids = [int(r["word_id"]) for r in new_rows]

    capacity = max(0, total_limit - len(new_ids))
    review_ids: list[int] = []
    if capacity > 0:
        scored = [
            (review_priority(s, now), int(s["word_id"]))
            for s in db.get_due_reviews()
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        review_ids = [wid for _, wid in scored[:capacity]]

    return {"new": new_ids, "review": review_ids}
