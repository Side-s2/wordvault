"""Guardian 文章拉取解析的离线单元测试。"""

import unittest
from unittest.mock import patch

from wordvault import news


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class NewsTests(unittest.TestCase):
    def test_fetch_filters_and_normalizes(self):
        payload = {
            "response": {
                "status": "ok",
                "results": [
                    {
                        "type": "article",
                        "id": "world/1",
                        "sectionName": "World",
                        "webUrl": "https://example.com/1",
                        "webPublicationDate": "2026-08-22T00:00:00Z",
                        "webTitle": "Headline one",
                        "fields": {"headline": "Headline one", "bodyText": "x" * 300},
                    },
                    {
                        "type": "liveblog",
                        "id": "sport/2",
                        "webTitle": "live",
                        "fields": {"bodyText": "y" * 500},
                    },
                    {
                        "type": "article",
                        "id": "world/3",
                        "webTitle": "too short",
                        "fields": {"headline": "too short", "bodyText": "short"},
                    },
                ],
            }
        }
        with patch("wordvault.news.requests.get", return_value=_FakeResponse(payload)):
            articles = news.fetch_articles(section="world")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["id"], "world/1")
        self.assertEqual(articles[0]["source"], "The Guardian")


if __name__ == "__main__":
    unittest.main()
