"""批量输入解析：每行一条；行内可用逗号/分号分隔，空格不视为分隔符。

短语（如 give up、cater on）中的空格会原样保留，因此空格不会被当作
多个单词之间的分隔符；尾部中文与无关标点会被忽略。
"""

from __future__ import annotations

import re


_CJK = re.compile(r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]")
_LETTER = re.compile(r"[A-Za-z]")
_CLEAN = re.compile(r"[^A-Za-z'\- ]+")
_SEP = re.compile(r"[,，;；]")


def clean_word(token: str) -> str:
    """去掉尾部中文和无关标点，规范化短语中的空白。"""
    token = token.strip().strip(".,;:!?()[]{}<>\"“”‘’\u3002")
    if not token:
        return ""
    m = _CJK.search(token)
    if m:
        token = token[: m.start()]
    token = _CLEAN.sub(" ", token)
    token = re.sub(r"\s+", " ", token).strip(" -'")
    return token


def parse_input_text(text: str) -> list[str]:
    """解析用户输入，返回去重后的单词/短语列表（保留首次出现的写法）。"""
    chunks: list[str] = []
    for line in (text or "").splitlines():
        chunks.extend(_SEP.split(line))

    seen: set[str] = set()
    result: list[str] = []
    for chunk in chunks:
        word = clean_word(chunk)
        if not word or not _LETTER.search(word):
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(word)
    return result
