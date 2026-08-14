"""数据导出 / 导入。"""

from __future__ import annotations

import json
from pathlib import Path

from wordvault.db import Database


def export_json(db: Database, target: str | Path) -> Path:
    payload = db.export_payload()
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def import_json(db: Database, source: str | Path, mode: str = "merge") -> dict:
    path = Path(source)
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or "words" not in payload:
        raise ValueError("文件格式不正确，不是有效的单词本备份")
    return db.import_payload(payload, mode=mode)
