"""真实云端闭环验证：上传 -> 列表 -> 拉取最新 -> 清理测试文件。"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wordvault import cloud  # noqa: E402
from wordvault.db import Database, Meaning  # noqa: E402


def main() -> int:
    tmp = tempfile.mkdtemp()
    db = Database(Path(tmp) / "probe.db")
    try:
        db.add_word("probe", meanings=[Meaning("n.", "探测")])
        result = cloud.upload_backup(db)
        print("UPLOAD", result["key"], result["size"])

        items = cloud.list_backups()
        print("LIST_COUNT", len(items))
        for item in items:
            print("  KEY", item["key"], item["size"], item["last_modified"])

        latest, payload = cloud.download_latest()
        print("LATEST", latest["key"], "words", len(payload["words"]))
        assert latest["key"] == result["key"]

        cloud._request(
            "DELETE", f"{cloud.ENDPOINT}/{cloud.BUCKET}/{result['key']}"
        )
        print("CLEANUP_OK", result["key"])
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
