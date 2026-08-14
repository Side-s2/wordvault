"""检查常用短语在 ECDICT 中的分布（一次性工具）。"""

import sqlite3
import sys


def main() -> None:
    path = sys.argv[1]
    conn = sqlite3.connect(path)
    for phrase in ["give up", "look forward to", "take care of", "give in", "put off"]:
        row = conn.execute(
            "SELECT word, translation, bnc, frq, tag FROM stardict WHERE word = ?",
            (phrase,),
        ).fetchone()
        print(phrase, "->", row)
    counts = conn.execute(
        "SELECT COUNT(*) FROM stardict WHERE word LIKE '% %' AND translation IS NOT NULL"
    ).fetchone()[0]
    print("all phrases with translation:", counts)
    common = conn.execute(
        "SELECT COUNT(*) FROM stardict WHERE word LIKE '% %' AND translation IS NOT NULL "
        "AND (bnc > 0 OR frq > 0 OR collins > 0 OR oxford > 0)"
    ).fetchone()[0]
    print("common phrases (freq/星级):", common)
    with_pos = conn.execute(
        "SELECT COUNT(*) FROM stardict WHERE word LIKE '% %' AND translation IS NOT NULL "
        "AND pos IS NOT NULL AND pos != ''"
    ).fetchone()[0]
    print("phrases with pos:", with_pos)
    le3 = conn.execute(
        "SELECT COUNT(*) FROM stardict WHERE word LIKE '% %' AND translation IS NOT NULL "
        "AND (LENGTH(word) - LENGTH(REPLACE(word, ' ', ''))) <= 2"
    ).fetchone()[0]
    print("phrases with <=3 words:", le3)
    print(
        "sample pos:",
        conn.execute(
            "SELECT word, pos, translation FROM stardict WHERE word IN "
            "('give up','look forward to','take care of','put off')"
        ).fetchall(),
    )
    conn.close()


if __name__ == "__main__":
    main()
