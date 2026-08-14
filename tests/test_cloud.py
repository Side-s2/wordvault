"""云同步模块的离线单元测试（不访问真实网络）。"""

import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from wordvault import cloud


class _FakeResponse:
    def __init__(self, content: bytes = b"", payload: dict | None = None):
        self.content = content
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def raise_for_status(self):
        return None


class _FakeDb:
    def export_payload(self):
        return {"app": "wordvault", "words": [], "states": [], "logs": []}


class CloudSignTests(unittest.TestCase):
    def test_signed_headers_format(self):
        body = b'{"a": 1}'
        now = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)
        headers = cloud.build_signed_headers(
            "PUT",
            "https://cn-nb1.rains3.com/storage1/word/x.json",
            body=body,
            headers={"content-type": "application/json"},
            now=now,
        )
        self.assertEqual(headers["host"], "cn-nb1.rains3.com")
        self.assertEqual(headers["x-amz-date"], "20260814T120000Z")
        self.assertEqual(
            headers["x-amz-content-sha256"], hashlib.sha256(body).hexdigest()
        )
        self.assertIn(
            "Credential=cR8MJXcVrgmTRED3/20260814/cn-nb1/s3/aws4_request",
            headers["authorization"],
        )
        self.assertIn(
            "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date",
            headers["authorization"],
        )

    def test_upload_filename_contains_date_and_time(self):
        now = datetime(2026, 8, 14, 12, 34, 56, 789123)
        with patch("wordvault.cloud._request") as mock_req:
            result = cloud.upload_backup(_FakeDb(), now=now)
        self.assertEqual(
            result["key"], "word/wordvault_backup_20260814_123456_789.json"
        )
        args = mock_req.call_args.args
        self.assertEqual(args[0], "PUT")
        self.assertIn("word/wordvault_backup_20260814_123456_789.json", args[1])

    def test_list_backups_parses_xml(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<Contents><Key>word/a.json</Key><LastModified>"
            "2026-08-14T10:00:00.000Z</LastModified><Size>100</Size></Contents>"
            "<Contents><Key>word/b.json</Key><LastModified>"
            "2026-08-14T12:00:00.000Z</LastModified><Size>200</Size></Contents>"
            "</ListBucketResult>"
        )
        with patch("wordvault.cloud._request", return_value=_FakeResponse(xml.encode())):
            items = cloud.list_backups()
        self.assertEqual([i["key"] for i in items], ["word/a.json", "word/b.json"])
        self.assertLess(
            items[0]["last_modified_dt"], items[1]["last_modified_dt"]
        )

    def test_download_latest_picks_newest(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<Contents><Key>word/a.json</Key><LastModified>"
            "2026-08-14T10:00:00.000Z</LastModified><Size>100</Size></Contents>"
            "<Contents><Key>word/b.json</Key><LastModified>"
            "2026-08-14T12:00:00.000Z</LastModified><Size>200</Size></Contents>"
            "</ListBucketResult>"
        )
        payload = {"words": [], "states": [], "logs": []}
        with patch(
            "wordvault.cloud._request",
            side_effect=[
                _FakeResponse(xml.encode()),
                _FakeResponse(payload=payload),
            ],
        ):
            latest, data = cloud.download_latest()
        self.assertEqual(latest["key"], "word/b.json")
        self.assertEqual(data, payload)

    def test_download_latest_rejects_bad_payload(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<Contents><Key>word/a.json</Key><LastModified>"
            "2026-08-14T10:00:00.000Z</LastModified><Size>100</Size></Contents>"
            "</ListBucketResult>"
        )
        with patch(
            "wordvault.cloud._request",
            side_effect=[
                _FakeResponse(xml.encode()),
                _FakeResponse(payload={"not": "a backup"}),
            ],
        ):
            with self.assertRaises(cloud.CloudError):
                cloud.download_latest()

    def test_describe_error_messages(self):
        import requests

        err = requests.exceptions.HTTPError()
        err.response = type("R", (), {"status_code": 403})()
        self.assertIn("认证失败", cloud.describe_error(err))


if __name__ == "__main__":
    unittest.main()
