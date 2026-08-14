"""往 data_smoke 写入 3 个词 + 3 条今天的复习记录（用于验证统计图渲染）。"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["WORDVAULT_DATA_DIR"] = str(
    Path(__file__).resolve().parent.parent / "data_smoke"
)

from wordvault.db import Database, Meaning  # noqa: E402
from wordvault.scheduler import apply_review  # noqa: E402


def main() -> None:
    db = Database()
    for word, text in [("apple", "苹果"), ("banana", "香蕉"), ("cherry", "樱桃")]:
        created = db.add_word(word, meanings=[Meaning("n.", text)])
        state = db.ensure_state(created.id)
        state = apply_review(state, "correct")
        db.save_review(
            created.id,
            state,
            "correct",
            text,
            text,
            500,
            "choice",
            state["last_reviewed_at"],
        )
    print("seeded", db.count_words(), db.total_volume())
    db.close()


if __name__ == "__main__":
    main()
