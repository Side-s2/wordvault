"""The Guardian Open Platform 文章拉取（免费 API）。"""

from __future__ import annotations

import requests

GUARDIAN_API_KEY = "c0376bbd-4ec6-41aa-a954-d384bddf32e0"
GUARDIAN_ENDPOINT = "https://content.guardianapis.com/search"


class NewsError(Exception):
    """文章拉取失败时可展示给用户的错误。"""


def fetch_articles(section: str | None = None, page_size: int = 12) -> list[dict]:
    params = {
        "api-key": GUARDIAN_API_KEY,
        "type": "article",
        "show-fields": "headline,bodyText",
        "order-by": "newest",
        "page-size": str(page_size),
    }
    if section:
        params["section"] = section
    try:
        resp = requests.get(GUARDIAN_ENDPOINT, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        raise NewsError(f"无法连接 The Guardian：{exc}") from exc
    except ValueError as exc:
        raise NewsError("The Guardian 返回数据解析失败") from exc

    response = data.get("response") if isinstance(data, dict) else None
    if not response or response.get("status") != "ok":
        message = (response or {}).get("message", "未知错误")
        raise NewsError(f"The Guardian 接口错误：{message}")

    articles: list[dict] = []
    for r in response.get("results") or []:
        if r.get("type") != "article":
            continue
        fields = r.get("fields") or {}
        title = (fields.get("headline") or r.get("webTitle") or "").strip()
        body = (fields.get("bodyText") or "").strip()
        if not title or len(body) < 200:
            continue
        articles.append(
            {
                "id": r.get("id") or r.get("webUrl") or title,
                "title": title,
                "source": "The Guardian",
                "section": r.get("sectionName") or "",
                "section_id": section or "",
                "url": r.get("webUrl") or "",
                "body": body,
                "published_at": r.get("webPublicationDate") or "",
            }
        )
    return articles
