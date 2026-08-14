"""把 ECDICT 全量库裁剪为常用词精简库（word/phonetic/translation/definition）。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


WHERE = (
    "(bnc > 0 OR frq > 0 "
    "OR tag LIKE '%zk%' OR tag LIKE '%gk%' "
    "OR tag LIKE '%cet4%' OR tag LIKE '%cet6%' OR tag LIKE '%ky%' "
    "OR tag LIKE '%toefl%' OR tag LIKE '%ielts%' OR tag LIKE '%gre%') "
    "AND (translation IS NOT NULL OR definition IS NOT NULL)"
)


def main() -> None:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path(__file__).resolve().parent.parent / "assets" / "dict" / "ecdict.db"
    )
    dst.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(src)
    source.row_factory = sqlite3.Row
    target = sqlite3.connect(dst)
    target.execute(
        "CREATE TABLE stardict ("
        "word TEXT PRIMARY KEY COLLATE NOCASE, "
        "phonetic TEXT, translation TEXT, definition TEXT)"
    )
    target.execute("CREATE INDEX idx_word ON stardict(word)")

    rows = source.execute(
        f"SELECT word, phonetic, translation, definition FROM stardict WHERE {WHERE}"
    )
    count = 0
    batch = []
    for row in rows:
        batch.append(
            (row["word"], row["phonetic"], row["translation"], row["definition"])
        )
        count += 1
        if len(batch) >= 5000:
            target.executemany("INSERT OR IGNORE INTO stardict VALUES (?,?,?,?)", batch)
            batch = []
    if batch:
        target.executemany("INSERT OR IGNORE INTO stardict VALUES (?,?,?,?)", batch)
    target.commit()
    target.execute("VACUUM")
    target.commit()

    total = target.execute("SELECT COUNT(*) FROM stardict").fetchone()[0]
    print(f"rows_selected={count}")
    print(f"rows_written={total}")
    print(f"size_bytes={dst.stat().st_size}")
    source.close()
    target.close()


if __name__ == "__main__":
    main()
