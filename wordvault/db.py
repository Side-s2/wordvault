"""SQLite 数据层：单词、学习状态、复习日志、设置与统计。"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def data_dir() -> Path:
    env = os.environ.get("WORDVAULT_DATA_DIR")
    if env:
        path = Path(env)
    else:
        app_data = os.environ.get("FLET_APP_STORAGE_DATA")
        if app_data:
            # 手机端：应用私有数据目录，随升级保留且可写
            path = Path(app_data) / "wordvault"
        else:
            path = Path(__file__).resolve().parent.parent / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phonetic TEXT NOT NULL DEFAULT '',
    meanings TEXT NOT NULL DEFAULT '[]',
    examples TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'manual',
    learn_mode TEXT NOT NULL DEFAULT 'write',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_state (
    word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
    reps INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    acc_ema REAL NOT NULL DEFAULT 0.0,
    ease REAL NOT NULL DEFAULT 2.5,
    interval_days REAL NOT NULL DEFAULT 0.0,
    due_at TEXT NOT NULL,
    last_reviewed_at TEXT,
    proficiency REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    reviewed_at TEXT NOT NULL,
    result TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    correct_answer TEXT NOT NULL DEFAULT '',
    ms INTEGER NOT NULL DEFAULT 0,
    proficiency_after REAL NOT NULL DEFAULT 0.0,
    interval_after REAL NOT NULL DEFAULT 0.0,
    mode TEXT NOT NULL DEFAULT 'choice'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'The Guardian',
    section TEXT NOT NULL DEFAULT '',
    section_id TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    body TEXT NOT NULL,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    last_opened_at TEXT,
    finished INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_state_due ON learning_state(due_at);
CREATE INDEX IF NOT EXISTS idx_log_time ON review_log(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_articles_opened ON articles(last_opened_at);
"""

DEFAULT_SETTINGS = {
    "new_daily_limit": "20",
    "review_daily_limit": "100",
    "theme_mode": "system",
}


@dataclass
class Meaning:
    pos: str = ""
    text: str = ""

    def to_dict(self) -> dict:
        return {"pos": self.pos, "text": self.text}

    @staticmethod
    def from_dict(data: dict) -> "Meaning":
        return Meaning(pos=str(data.get("pos", "")), text=str(data.get("text", "")))


@dataclass
class Example:
    en: str = ""
    zh: str = ""

    def to_dict(self) -> dict:
        return {"en": self.en, "zh": self.zh}

    @staticmethod
    def from_dict(data: dict) -> "Example":
        return Example(en=str(data.get("en", "")), zh=str(data.get("zh", "")))


@dataclass
class Word:
    id: int
    word: str
    phonetic: str = ""
    meanings: list[Meaning] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)
    source: str = "manual"
    learn_mode: str = "write"
    created_at: str = ""
    updated_at: str = ""

    @property
    def meaning_brief(self) -> str:
        if not self.meanings:
            return "（暂无释义）"
        return "；".join(m.text for m in self.meanings[:3])

    @property
    def meaning_full(self) -> str:
        lines = []
        for m in self.meanings:
            prefix = f"{m.pos} " if m.pos else ""
            lines.append(f"{prefix}{m.text}".strip())
        return "\n".join(lines)


def _dumps_meaning_list(items: list[Meaning]) -> str:
    return json.dumps([m.to_dict() for m in items], ensure_ascii=False)


def _loads_meaning_list(raw: str) -> list[Meaning]:
    try:
        data = json.loads(raw or "[]")
        return [Meaning.from_dict(d) for d in data]
    except (TypeError, ValueError):
        return []


def _dumps_example_list(items: list[Example]) -> str:
    return json.dumps([e.to_dict() for e in items], ensure_ascii=False)


def _loads_example_list(raw: str) -> list[Example]:
    try:
        data = json.loads(raw or "[]")
        return [Example.from_dict(d) for d in data]
    except (TypeError, ValueError):
        return []


def _row_to_word(row: sqlite3.Row) -> Word:
    return Word(
        id=row["id"],
        word=row["word"],
        phonetic=row["phonetic"],
        meanings=_loads_meaning_list(row["meanings"]),
        examples=_loads_example_list(row["examples"]),
        source=row["source"],
        learn_mode=row["learn_mode"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class Database:
    """线程安全的 SQLite 封装。"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else data_dir() / "wordvault.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._ensure_word_columns()
            self._ensure_article_columns()
            for key, value in DEFAULT_SETTINGS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    (key, value),
                )
            self._conn.commit()

    def _ensure_article_columns(self) -> None:
        cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(articles)").fetchall()
        }
        if "section_id" not in cols:
            self._conn.execute(
                "ALTER TABLE articles ADD COLUMN section_id TEXT NOT NULL DEFAULT ''"
            )
        if "finished" not in cols:
            self._conn.execute(
                "ALTER TABLE articles ADD COLUMN finished INTEGER NOT NULL DEFAULT 0"
            )
        self._conn.commit()

    def _ensure_word_columns(self) -> None:
        cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(words)").fetchall()
        }
        if "learn_mode" not in cols:
            self._conn.execute(
                "ALTER TABLE words ADD COLUMN learn_mode TEXT NOT NULL DEFAULT 'write'"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------- 设置 ----------------

    def get_setting(self, key: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return DEFAULT_SETTINGS.get(key, "")
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def get_int_setting(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get_setting(key))
        except (TypeError, ValueError):
            return default

    # ---------------- 单词增删查改 ----------------

    def word_exists(self, word: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM words WHERE word = ? COLLATE NOCASE", (word.strip(),)
            ).fetchone()
        return row is not None

    def add_word(
        self,
        word: str,
        phonetic: str = "",
        meanings: list[Meaning] | None = None,
        examples: list[Example] | None = None,
        source: str = "manual",
        learn_mode: str = "write",
        created_at: str | None = None,
    ) -> Word | None:
        """添加单词并初始化学习状态；重复返回 None。"""
        word = word.strip()
        if not word:
            return None
        created = created_at or now_str()
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO words(word, phonetic, meanings, examples, source, "
                    "learn_mode, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        word,
                        phonetic or "",
                        _dumps_meaning_list(meanings or []),
                        _dumps_example_list(examples or []),
                        source or "manual",
                        learn_mode or "write",
                        created,
                        created,
                    ),
                )
                word_id = cur.lastrowid
                self._conn.execute(
                    "INSERT INTO learning_state(word_id, due_at) VALUES (?, ?)",
                    (word_id, created),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                return None
        return self.get_word(word_id)

    def get_word(self, word_id: int) -> Word | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM words WHERE id = ?", (word_id,)
            ).fetchone()
        return _row_to_word(row) if row else None

    def list_words(self) -> list[Word]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM words ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [_row_to_word(r) for r in rows]

    def search_words(self, query: str, sort: str = "time_desc") -> list[Word]:
        words = self.list_words()
        q = (query or "").strip().lower()
        if q:
            filtered = []
            for w in words:
                hay = " ".join(
                    [w.word, w.phonetic]
                    + [m.text for m in w.meanings]
                    + [m.pos for m in w.meanings]
                ).lower()
                if q in hay:
                    filtered.append(w)
            words = filtered
        if sort == "time_asc":
            words.sort(key=lambda w: (w.created_at, w.id))
        elif sort == "alpha":
            words.sort(key=lambda w: (w.word.lower(), w.id))
        else:  # time_desc 默认
            words.sort(key=lambda w: (w.created_at, w.id), reverse=True)
        return words

    def update_word(
        self,
        word_id: int,
        word: str,
        phonetic: str,
        meanings: list[Meaning],
        examples: list[Example],
        learn_mode: str = "write",
    ) -> bool:
        word = word.strip()
        if not word:
            return False
        with self._lock:
            try:
                cur = self._conn.execute(
                    "UPDATE words SET word = ?, phonetic = ?, meanings = ?, "
                    "examples = ?, learn_mode = ?, updated_at = ? WHERE id = ?",
                    (
                        word,
                        phonetic or "",
                        _dumps_meaning_list(meanings),
                        _dumps_example_list(examples),
                        learn_mode or "write",
                        now_str(),
                        word_id,
                    ),
                )
                self._conn.commit()
                return cur.rowcount > 0
            except sqlite3.IntegrityError:
                return False

    def delete_word(self, word_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM words WHERE id = ?", (word_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def delete_all_data(self) -> dict:
        """删除所有单词、学习状态与复习记录；应用设置（配额/主题）保留。"""
        with self._lock:
            before_words = int(
                self._conn.execute("SELECT COUNT(*) AS c FROM words").fetchone()["c"]
            )
            before_logs = int(
                self._conn.execute("SELECT COUNT(*) AS c FROM review_log").fetchone()[
                    "c"
                ]
            )
            self._conn.execute("DELETE FROM review_log")
            self._conn.execute("DELETE FROM learning_state")
            self._conn.execute("DELETE FROM words")
            self._conn.commit()
            self._conn.execute("VACUUM")
        return {"words": before_words, "logs": before_logs}

    def count_words(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM words").fetchone()
        return int(row["c"])

    # ---------------- 学习状态与复习 ----------------

    def ensure_state(self, word_id: int) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM learning_state WHERE word_id = ?", (word_id,)
            ).fetchone()
            if row is None:
                created = now_str()
                self._conn.execute(
                    "INSERT INTO learning_state(word_id, due_at) VALUES (?, ?)",
                    (word_id, created),
                )
                self._conn.commit()
                row = self._conn.execute(
                    "SELECT * FROM learning_state WHERE word_id = ?", (word_id,)
                ).fetchone()
        return dict(row)

    def save_review(
        self,
        word_id: int,
        state: dict[str, Any],
        result: str,
        answer: str,
        correct_answer: str,
        ms: int,
        mode: str,
        reviewed_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE learning_state SET reps=?, correct=?, streak=?, lapses=?, "
                "acc_ema=?, ease=?, interval_days=?, due_at=?, last_reviewed_at=?, "
                "proficiency=? WHERE word_id=?",
                (
                    state["reps"],
                    state["correct"],
                    state["streak"],
                    state["lapses"],
                    state["acc_ema"],
                    state["ease"],
                    state["interval_days"],
                    state["due_at"],
                    state["last_reviewed_at"],
                    state["proficiency"],
                    word_id,
                ),
            )
            self._conn.execute(
                "INSERT INTO review_log(word_id, reviewed_at, result, answer, "
                "correct_answer, ms, proficiency_after, interval_after, mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    word_id,
                    reviewed_at,
                    result,
                    answer,
                    correct_answer,
                    ms,
                    state["proficiency"],
                    state["interval_days"],
                    mode,
                ),
            )
            self._conn.commit()

    def get_pending_new(self, limit: int) -> list[dict]:
        """尚未复习过（reps=0）且已到期的新词，按添加时间排序。"""
        now = now_str()
        with self._lock:
            rows = self._conn.execute(
                "SELECT w.id AS word_id, s.* FROM learning_state s "
                "JOIN words w ON w.id = s.word_id "
                "WHERE s.reps = 0 AND s.due_at <= ? "
                "ORDER BY w.created_at ASC, w.id ASC LIMIT ?",
                (now, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_due_reviews(self) -> list[dict]:
        """已复习过且已到期的词，用于按优先级排序。"""
        now = now_str()
        with self._lock:
            rows = self._conn.execute(
                "SELECT w.id AS word_id, s.* FROM learning_state s "
                "JOIN words w ON w.id = s.word_id "
                "WHERE s.reps > 0 AND s.due_at <= ?",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def word_with_state(self, word_id: int) -> tuple[Word, dict]:
        word = self.get_word(word_id)
        state = self.ensure_state(word_id)
        return word, state  # type: ignore[return-value]

    def reset_word_progress(self, word_id: int) -> None:
        """手动重置某个词的学习进度（编辑界面里可用）。"""
        with self._lock:
            self._conn.execute(
                "UPDATE learning_state SET reps=0, correct=0, streak=0, lapses=0, "
                "acc_ema=0, ease=2.5, interval_days=0, due_at=?, "
                "last_reviewed_at=NULL, proficiency=0 WHERE word_id=?",
                (now_str(), word_id),
            )
            self._conn.commit()

    # ---------------- 统计 ----------------

    def total_volume(self) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c, "
                "SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok "
                "FROM review_log"
            ).fetchone()
        return {"total": int(row["c"] or 0), "correct": int(row["ok"] or 0)}

    def day_counts(self, day: str) -> dict:
        """某一天（YYYY-MM-DD）的复习量与正确数。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c, "
                "SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok "
                "FROM review_log WHERE substr(reviewed_at, 1, 10) = ?",
                (day,),
            ).fetchone()
            added = self._conn.execute(
                "SELECT COUNT(*) AS c FROM words WHERE substr(created_at, 1, 10) = ?",
                (day,),
            ).fetchone()
        return {
            "reviews": int(row["c"] or 0),
            "correct": int(row["ok"] or 0),
            "added": int(added["c"] or 0),
        }

    def daily_series(self, days: int = 30) -> list[dict]:
        """最近 N 天的逐日数据（含今天），用于画图。"""
        today = datetime.now().date()
        result = []
        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            key = day.strftime("%Y-%m-%d")
            counts = self.day_counts(key)
            result.append({"date": key, **counts})
        return result

    def streak(self) -> int:
        """连续打卡天数：今天没复习则从昨天往前算。"""
        today = datetime.now().date()
        cursor = today
        if self.day_counts(cursor.strftime("%Y-%m-%d"))["reviews"] == 0:
            cursor = today - timedelta(days=1)
        count = 0
        while True:
            day = cursor.strftime("%Y-%m-%d")
            if self.day_counts(day)["reviews"] > 0:
                count += 1
                cursor -= timedelta(days=1)
            else:
                break
        return count

    def proficiency_distribution(self) -> dict[str, int]:
        from wordvault.scheduler import tier_of

        with self._lock:
            rows = self._conn.execute(
                "SELECT s.reps, s.proficiency, w.learn_mode FROM learning_state s "
                "JOIN words w ON w.id = s.word_id"
            ).fetchall()
        dist = {"未开始": 0, "生疏": 0, "学习中": 0, "熟练": 0, "已掌握": 0}
        for row in rows:
            if row["reps"] <= 0:
                dist["未开始"] += 1
            else:
                dist[tier_of(row["proficiency"], row["learn_mode"])] += 1
        return dist

    def due_overview(self) -> dict:
        """复习队列概况：今日待复习、新词、未来 7 天预计到期。"""
        now = datetime.now()
        now_s = now.strftime("%Y-%m-%d %H:%M:%S")
        week_s = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            due = self._conn.execute(
                "SELECT COUNT(*) AS c FROM learning_state WHERE reps > 0 AND due_at <= ?",
                (now_s,),
            ).fetchone()
            new = self._conn.execute(
                "SELECT COUNT(*) AS c FROM learning_state WHERE reps = 0 AND due_at <= ?",
                (now_s,),
            ).fetchone()
            week = self._conn.execute(
                "SELECT COUNT(*) AS c FROM learning_state WHERE reps > 0 "
                "AND due_at > ? AND due_at <= ?",
                (now_s, week_s),
            ).fetchone()
        return {
            "due_today": int(due["c"] or 0),
            "new_today": int(new["c"] or 0),
            "due_next_week": int(week["c"] or 0),
        }

    # ---------------- 阅读文章 ----------------

    def upsert_article(self, article: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO articles(id, title, source, section, url, body, "
                "section_id, published_at, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET title = excluded.title, "
                "source = excluded.source, section = excluded.section, "
                "section_id = excluded.section_id, "
                "url = excluded.url, body = excluded.body, "
                "published_at = excluded.published_at, "
                "fetched_at = excluded.fetched_at",
                (
                    str(article["id"]),
                    str(article.get("title", "")),
                    str(article.get("source", "The Guardian")),
                    str(article.get("section", "")),
                    str(article.get("url", "")),
                    str(article.get("body", "")),
                    str(article.get("section_id", "")),
                    str(article.get("published_at", "")),
                    now_str(),
                ),
            )
            self._conn.commit()

    def list_articles(self, section_id: str | None = None) -> list[dict]:
        with self._lock:
            if section_id:
                rows = self._conn.execute(
                    "SELECT * FROM articles WHERE section_id = ? "
                    "ORDER BY published_at DESC",
                    (section_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM articles ORDER BY published_at DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_article(self, article_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
        return dict(row) if row else None

    def mark_article_opened(self, article_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE articles SET last_opened_at = ? WHERE id = ?",
                (now_str(), article_id),
            )
            self._conn.commit()

    def reading_history(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM articles WHERE last_opened_at IS NOT NULL "
                "ORDER BY last_opened_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_article_finished(self, article_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE articles SET finished = 1 WHERE id = ?", (article_id,)
            )
            self._conn.commit()

    def delete_article(self, article_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
            self._conn.commit()

    def clear_unopened_articles(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM articles WHERE last_opened_at IS NULL"
            )
            self._conn.commit()
            return cur.rowcount

    # ---------------- 备份 ----------------

    def export_payload(self) -> dict:
        with self._lock:
            words = [dict(r) for r in self._conn.execute("SELECT * FROM words")]
            states = [
                dict(r) for r in self._conn.execute("SELECT * FROM learning_state")
            ]
            logs = [dict(r) for r in self._conn.execute("SELECT * FROM review_log")]
        return {
            "app": "wordvault",
            "version": 1,
            "exported_at": now_str(),
            "words": words,
            "states": states,
            "logs": logs,
        }

    def import_payload(self, payload: dict, mode: str = "merge") -> dict:
        """导入备份。mode: merge 合并 / replace 覆盖 / sync 云端合并。"""
        if mode == "sync":
            return self._import_sync(payload)
        words = payload.get("words", [])
        states = payload.get("states", [])
        logs = payload.get("logs", [])
        with self._lock:
            if mode == "replace":
                self._conn.execute("DELETE FROM review_log")
                self._conn.execute("DELETE FROM learning_state")
                self._conn.execute("DELETE FROM words")
            added, skipped, imported_logs = 0, 0, 0
            for w in words:
                try:
                    self._conn.execute(
                        "INSERT INTO words(id, word, phonetic, meanings, examples, "
                        "source, learn_mode, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            w["id"],
                            w["word"],
                            w.get("phonetic", ""),
                            w.get("meanings", "[]"),
                            w.get("examples", "[]"),
                            w.get("source", "manual"),
                            w.get("learn_mode", "write"),
                            w.get("created_at") or now_str(),
                            w.get("updated_at") or now_str(),
                        ),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    skipped += 1
            for s in states:
                try:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO learning_state(word_id, reps, correct, "
                        "streak, lapses, acc_ema, ease, interval_days, due_at, "
                        "last_reviewed_at, proficiency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            s["word_id"],
                            s.get("reps", 0),
                            s.get("correct", 0),
                            s.get("streak", 0),
                            s.get("lapses", 0),
                            s.get("acc_ema", 0.0),
                            s.get("ease", 2.5),
                            s.get("interval_days", 0.0),
                            s.get("due_at") or now_str(),
                            s.get("last_reviewed_at"),
                            s.get("proficiency", 0.0),
                        ),
                    )
                except sqlite3.IntegrityError:
                    pass
            for item in logs:
                try:
                    self._conn.execute(
                        "INSERT INTO review_log(id, word_id, reviewed_at, result, "
                        "answer, correct_answer, ms, proficiency_after, "
                        "interval_after, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            item["id"],
                            item["word_id"],
                            item.get("reviewed_at") or now_str(),
                            item.get("result", "correct"),
                            item.get("answer", ""),
                            item.get("correct_answer", ""),
                            item.get("ms", 0),
                            item.get("proficiency_after", 0.0),
                            item.get("interval_after", 0.0),
                            item.get("mode", "choice"),
                        ),
                    )
                    imported_logs += 1
                except sqlite3.IntegrityError:
                    pass
            self._conn.commit()
        return {"added": added, "skipped": skipped, "logs": imported_logs}

    def _import_sync(self, payload: dict) -> dict:
        """云端合并：按单词文本匹配，跨设备的单词 ID 自动重映射，不丢数据。"""
        words = payload.get("words", [])
        states = payload.get("states", [])
        logs = payload.get("logs", [])
        id_map: dict[int, int] = {}
        with self._lock:
            added, updated = 0, 0
            for w in words:
                text = str(w.get("word", "")).strip()
                if not text:
                    continue
                row = self._conn.execute(
                    "SELECT id FROM words WHERE word = ? COLLATE NOCASE", (text,)
                ).fetchone()
                if row is not None:
                    local_id = int(row["id"])
                    self._conn.execute(
                        "UPDATE words SET phonetic = ?, meanings = ?, examples = ?, "
                        "learn_mode = ?, updated_at = ? WHERE id = ?",
                        (
                            w.get("phonetic", ""),
                            w.get("meanings", "[]"),
                            w.get("examples", "[]"),
                            w.get("learn_mode", "write"),
                            w.get("updated_at") or now_str(),
                            local_id,
                        ),
                    )
                    updated += 1
                else:
                    cur = self._conn.execute(
                        "INSERT INTO words(word, phonetic, meanings, examples, "
                        "source, learn_mode, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            text,
                            w.get("phonetic", ""),
                            w.get("meanings", "[]"),
                            w.get("examples", "[]"),
                            w.get("source", "manual"),
                            w.get("learn_mode", "write"),
                            w.get("created_at") or now_str(),
                            w.get("updated_at") or now_str(),
                        ),
                    )
                    local_id = int(cur.lastrowid)
                    self._conn.execute(
                        "INSERT INTO learning_state(word_id, due_at) VALUES (?, ?)",
                        (local_id, now_str()),
                    )
                    added += 1
                if isinstance(w.get("id"), int):
                    id_map[w["id"]] = local_id

            for s in states:
                local_id = id_map.get(s.get("word_id"))
                if local_id is None:
                    continue
                self._conn.execute(
                    "INSERT INTO learning_state(word_id, reps, correct, streak, "
                    "lapses, acc_ema, ease, interval_days, due_at, last_reviewed_at, "
                    "proficiency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(word_id) DO UPDATE SET reps = excluded.reps, "
                    "correct = excluded.correct, streak = excluded.streak, "
                    "lapses = excluded.lapses, acc_ema = excluded.acc_ema, "
                    "ease = excluded.ease, interval_days = excluded.interval_days, "
                    "due_at = excluded.due_at, "
                    "last_reviewed_at = excluded.last_reviewed_at, "
                    "proficiency = excluded.proficiency",
                    (
                        local_id,
                        s.get("reps", 0),
                        s.get("correct", 0),
                        s.get("streak", 0),
                        s.get("lapses", 0),
                        s.get("acc_ema", 0.0),
                        s.get("ease", 2.5),
                        s.get("interval_days", 0.0),
                        s.get("due_at") or now_str(),
                        s.get("last_reviewed_at"),
                        s.get("proficiency", 0.0),
                    ),
                )

            imported_logs = 0
            for item in logs:
                local_id = id_map.get(item.get("word_id"))
                if local_id is None:
                    continue
                reviewed_at = item.get("reviewed_at") or now_str()
                exists = self._conn.execute(
                    "SELECT 1 FROM review_log WHERE word_id = ? AND reviewed_at = ?",
                    (local_id, reviewed_at),
                ).fetchone()
                if exists is not None:
                    continue
                self._conn.execute(
                    "INSERT INTO review_log(word_id, reviewed_at, result, answer, "
                    "correct_answer, ms, proficiency_after, interval_after, mode) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        local_id,
                        reviewed_at,
                        item.get("result", "correct"),
                        item.get("answer", ""),
                        item.get("correct_answer", ""),
                        item.get("ms", 0),
                        item.get("proficiency_after", 0.0),
                        item.get("interval_after", 0.0),
                        item.get("mode", "choice"),
                    ),
                )
                imported_logs += 1
            self._conn.commit()
        return {
            "added": added,
            "updated": updated,
            "skipped": 0,
            "logs": imported_logs,
        }
