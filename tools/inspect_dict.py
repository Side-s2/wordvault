"""查看 ECDICT sqlite 的表结构和数据分布（一次性工具）。"""

import sqlite3
import sys


def main() -> None:
    path = sys.argv[1]
    conn = sqlite3.connect(path)
    print(conn.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall())
    print("count:", conn.execute("SELECT COUNT(*) FROM stardict").fetchone())
    print(
        "sample:",
        conn.execute(
            "SELECT word, phonetic, translation, pos, tag, bnc, frq "
            "FROM stardict LIMIT 3"
        ).fetchall(),
    )
    for cond, label in [
        ("bnc > 0", "bnc>0"),
        ("frq > 0", "frq>0"),
        ("tag LIKE '%zk%' OR tag LIKE '%gk%'", "中考/高考 tag"),
        ("tag LIKE '%cet4%' OR tag LIKE '%cet6%' OR tag LIKE '%ky%'", "四六级/考研"),
        (
            "bnc > 0 OR frq > 0 OR tag LIKE '%zk%' OR tag LIKE '%gk%' OR "
            "tag LIKE '%cet4%' OR tag LIKE '%cet6%' OR tag LIKE '%ky%' OR "
            "tag LIKE '%toefl%' OR tag LIKE '%ielts%' OR tag LIKE '%gre%'",
            "union",
        ),
    ]:
        try:
            n = conn.execute(
                f"SELECT COUNT(*) FROM stardict WHERE {cond}"
            ).fetchone()[0]
            print(f"{label}: {n}")
        except sqlite3.OperationalError as exc:
            print(f"{label}: ERROR {exc}")
    conn.close()


if __name__ == "__main__":
    main()
