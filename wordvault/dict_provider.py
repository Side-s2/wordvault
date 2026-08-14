"""词典/翻译提供器：离线 ECDICT 优先，在线（有道/MyMemory）兜底。"""

from __future__ import annotations

import random
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from wordvault.db import Example, Meaning


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

POS_PATTERN = re.compile(r"^(?P<pos>\[[^\]]*\]|[a-zA-Z]{1,12}\.)\s*(?P<rest>.*)$")


@dataclass
class LookupResult:
    word: str
    phonetic: str = ""
    meanings: list[Meaning] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)
    source: str = "none"  # offline / online / none

    @property
    def ok(self) -> bool:
        return bool(self.meanings)


def split_pos(text: str) -> tuple[str, str]:
    """把 'n. 苹果' 拆成 ('n.', '苹果')。"""
    text = text.strip()
    m = POS_PATTERN.match(text)
    if m and m.group("rest").strip():
        return m.group("pos"), m.group("rest").strip()
    return "", text


def split_multi_meanings(text: str) -> list[str]:
    parts = re.split(r"[；;，,、]", text)
    return [p.strip() for p in parts if p.strip()]


def uk_phonetic(raw: str) -> str:
    """只保留英式音标：优先取“英 /.../”，否则保留原值。"""
    raw = (raw or "").strip()
    if not raw:
        return ""
    match = re.search(r"英(?:式)?\s*(/[\w\s,.:;'\u0250-\u02ff-]+/)", raw)
    if match:
        return match.group(1).strip()
    return raw


def parse_translation_lines(translation: str) -> list[Meaning]:
    """解析 ECDICT 的 translation 字段为词性+释义列表。"""
    meanings: list[Meaning] = []
    for raw_line in (translation or "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        pos, rest = split_pos(line)
        for part in split_multi_meanings(rest):
            meanings.append(Meaning(pos=pos, text=part))
    return meanings


class DictProvider:
    """查词服务。线程安全；在线请求自带限速。"""

    def __init__(self, offline_db_path: str | Path | None = None):
        self.offline_db_path = Path(offline_db_path) if offline_db_path else None
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._throttle_lock = threading.Lock()
        self._last_request = 0.0

    # ---------- 离线 ECDICT ----------

    def _offline_conn(self) -> sqlite3.Connection | None:
        if not self.offline_db_path or not self.offline_db_path.exists():
            return None
        with self._lock:
            if self._conn is None:
                try:
                    conn = sqlite3.connect(
                        f"file:{self.offline_db_path}?mode=ro", uri=True
                    )
                    conn.row_factory = sqlite3.Row
                    self._conn = conn
                except sqlite3.Error:
                    return None
            return self._conn

    def _lookup_offline(self, word: str) -> LookupResult | None:
        conn = self._offline_conn()
        if conn is None:
            return None
        try:
            with self._lock:
                row = conn.execute(
                    "SELECT phonetic, translation, definition FROM stardict "
                    "WHERE word = ?",
                    (word.lower(),),
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        meanings = parse_translation_lines(row["translation"])
        if not meanings:
            definition = (row["definition"] or "").strip()
            if re.search(r"[\u4e00-\u9fff]", definition):
                for part in split_multi_meanings(definition):
                    meanings.append(Meaning(pos="", text=part))
        phonetic = (row["phonetic"] or "").strip()
        return LookupResult(
            word=word,
            phonetic=phonetic,
            meanings=meanings[:12],
            source="offline",
        )

    def has_offline_entry(self, word: str) -> bool:
        """判断某串（含短语）是否存在于离线词库，用于批量解析消歧。"""
        conn = self._offline_conn()
        if conn is None:
            return False
        try:
            with self._lock:
                row = conn.execute(
                    "SELECT 1 FROM stardict WHERE word = ?", (word.strip().lower(),)
                ).fetchone()
            return row is not None
        except sqlite3.Error:
            return False

    # ---------- 在线接口 ----------

    def _throttle(self) -> None:
        with self._throttle_lock:
            gap = time.monotonic() - self._last_request
            if gap < 0.12:
                time.sleep(0.12 - gap)
            self._last_request = time.monotonic()

    def _lookup_youdao(self, word: str) -> LookupResult | None:
        try:
            self._throttle()
            resp = requests.get(
                "https://dict.youdao.com/jsonapi",
                params={"q": word},
                headers={
                    "User-Agent": random.choice(USER_AGENTS),
                    "Referer": "https://dict.youdao.com/",
                    "Accept": "application/json, text/plain, */*",
                },
                timeout=6,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, dict):
                return None
        except (requests.RequestException, ValueError):
            return None

        ec = data.get("ec") or {}
        if not isinstance(ec, dict):
            ec = {}
        w = ec.get("word") or {}
        if isinstance(w, list):
            w = w[0] if w else {}
        if not isinstance(w, dict):
            w = {}
        us = str(w.get("usphone") or "").strip()
        uk = str(w.get("ukphone") or "").strip()
        phonetic = ""
        if uk:
            phonetic = f"/{uk}/"
        elif us:
            phonetic = f"/{us}/"

        meanings: list[Meaning] = []
        is_phrase = " " in word
        web_values: list[str] = []
        web_trans = (data.get("web_trans") or {}).get("web-translation") or []
        for item in web_trans:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip().lower()
            if key == word.strip().lower():
                for t in item.get("trans") or []:
                    if isinstance(t, dict) and t.get("value"):
                        web_values.append(str(t["value"]))

        if is_phrase and web_values:
            # 短语用 web_trans 的简洁中文释义
            for value in web_values[:8]:
                meanings.append(Meaning(pos="", text=value))
        else:
            for tr in w.get("trs") or []:
                if not isinstance(tr, dict):
                    continue
                for item in tr.get("tr") or []:
                    if not isinstance(item, dict):
                        continue
                    leaf = item.get("l") or {}
                    if not isinstance(leaf, dict):
                        continue
                    for raw in leaf.get("i") or []:
                        pos, text = split_pos(str(raw))
                        for part in split_multi_meanings(text):
                            meanings.append(Meaning(pos=pos, text=part))

        examples: list[Example] = []
        for pair in (data.get("blng_sents_part") or {}).get("sentence-pair") or []:
            if not isinstance(pair, dict):
                continue
            en = (pair.get("sentence") or "").strip()
            zh = (pair.get("sentence-translation") or "").strip()
            if en and zh:
                examples.append(Example(en=en, zh=zh))
            if len(examples) >= 3:
                break

        if meanings:
            return LookupResult(
                word=word,
                phonetic=phonetic,
                meanings=meanings[:12],
                examples=examples,
                source="online",
            )
        return None

    def _lookup_mymemory(self, word: str) -> LookupResult | None:
        try:
            self._throttle()
            resp = requests.get(
                "https://api.mymemory.translated.net/get",
                params={"q": word, "langpair": "en|zh-CN"},
                headers={"User-Agent": random.choice(USER_AGENTS)},
                timeout=6,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            text = (
                (data.get("responseData") or {}).get("translatedText") or ""
            ).strip()
        except (requests.RequestException, ValueError):
            return None
        if not text or text.upper() == word.upper():
            return None
        meanings = [Meaning(pos="", text=p) for p in split_multi_meanings(text)]
        if meanings:
            return LookupResult(word=word, meanings=meanings[:8], source="online")
        return None

    # ---------- 统一入口 ----------

    def lookup(self, word: str, want_examples: bool = True) -> LookupResult:
        word = word.strip()
        offline = self._lookup_offline(word)
        if offline is not None and offline.ok:
            if want_examples:
                online = self._lookup_youdao(word)
                if online is not None:
                    if online.examples:
                        offline.examples = online.examples
                    if not offline.phonetic and online.phonetic:
                        offline.phonetic = online.phonetic
            return offline

        online = self._lookup_youdao(word)
        if online is not None and online.ok:
            return online

        fallback = self._lookup_mymemory(word)
        if fallback is not None and fallback.ok:
            return fallback

        return LookupResult(word=word, source="none")

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
