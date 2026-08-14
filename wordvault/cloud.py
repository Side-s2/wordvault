"""雨云 rains3 对象存储云同步（S3 兼容协议，手写 SigV4 签名）。"""

from __future__ import annotations

import hashlib
import hmac
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit

import requests

ENDPOINT = "https://cn-nb1.rains3.com"
BUCKET = "storage1"
REGION = "cn-nb1"
ACCESS_KEY = "cR8MJXcVrgmTRED3"
SECRET_KEY = "zhFy9KWIyUTqO9iM6g74kx2YzMdBQz"
PREFIX = "word/"
TIMEOUT = 40


class CloudError(Exception):
    """云同步过程中可展示给用户的错误。"""


def _canonical_query(query: str) -> str:
    """SigV4 要求查询参数按键名排序、值按 RFC3986 编码。"""
    pairs = parse_qsl(query, keep_blank_values=True)
    encoded = sorted(
        (quote(k, safe="-_.~"), quote(v, safe="-_.~")) for k, v in pairs
    )
    return "&".join(f"{k}={v}" for k, v in encoded)


def _signing_key(secret: str, datestamp: str) -> bytes:
    def sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k_date = sign(("AWS4" + secret).encode("utf-8"), datestamp)
    k_region = sign(k_date, REGION)
    k_service = sign(k_region, "s3")
    return sign(k_service, "aws4_request")


def build_signed_headers(
    method: str,
    url: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    """构造 SigV4 签名请求头；now 可注入以便测试。"""
    parts = urlsplit(url)
    host = parts.netloc
    path = quote(parts.path or "/", safe="/-_.~")
    query = _canonical_query(parts.query)
    now = now or datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()

    out = {k.lower(): str(v) for k, v in (headers or {}).items()}
    out["host"] = host
    out["x-amz-content-sha256"] = payload_hash
    out["x-amz-date"] = amz_date

    names = sorted(out)
    canonical_headers = "".join(f"{n}:{out[n].strip()}\n" for n in names)
    signed_headers = ";".join(names)
    canonical_request = "\n".join(
        [method.upper(), path, query, canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{datestamp}/{REGION}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(SECRET_KEY, datestamp),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    out["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={ACCESS_KEY}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return out


def _request(
    method: str,
    url: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> requests.Response:
    signed = build_signed_headers(method, url, body=body, headers=headers)
    try:
        resp = requests.request(
            method,
            url,
            data=body if body else None,
            headers=signed,
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        raise CloudError(describe_error(exc)) from exc
    if resp.status_code >= 400:
        raise CloudError(describe_error(requests.exceptions.HTTPError(response=resp)))
    return resp


def describe_error(exc: Exception) -> str:
    """把底层异常转成适合展示的中文提示。"""
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "连接云端超时，请稍后重试"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "无法连接云端，请检查网络"
    resp = getattr(exc, "response", None)
    if resp is not None:
        code = getattr(resp, "status_code", 0)
        if code in (401, 403):
            return f"云端认证失败（{code}），请检查访问密钥"
        if code == 404:
            return "云端桶或文件不存在（404）"
        return f"云端返回错误（{code}）"
    return str(exc) or "未知云端错误"


def upload_backup(db: Any, now: datetime | None = None) -> dict:
    """把当前数据库导出为 JSON 并上传，文件名含日期时间，避免重名。"""
    import json

    data = json.dumps(db.export_payload(), ensure_ascii=False, indent=2).encode(
        "utf-8"
    )
    now = now or datetime.now()
    name = (
        f"wordvault_backup_{now:%Y%m%d_%H%M%S}"
        f"_{now.microsecond // 1000:03d}.json"
    )
    key = f"{PREFIX}{name}"
    url = f"{ENDPOINT}/{BUCKET}/{quote(key, safe='/')}"
    _request(
        "PUT",
        url,
        body=data,
        headers={"content-type": "application/json; charset=utf-8"},
    )
    return {
        "key": key,
        "name": name,
        "size": len(data),
        "url": f"https://storage1.cn-nb1.rains3.com/{key}",
    }


def _parse_iso(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def list_backups() -> list[dict]:
    """列出云端 word/ 目录下所有对象，含最后修改时间。"""
    url = (
        f"{ENDPOINT}/{BUCKET}?list-type=2&prefix={quote(PREFIX, safe='')}"
        "&max-keys=1000"
    )
    resp = _request("GET", url)
    root = ET.fromstring(resp.content)
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    items: list[dict] = []
    for node in root.findall(f".//{ns}Contents"):
        key = (node.findtext(f"{ns}Key") or "").strip()
        size = int(node.findtext(f"{ns}Size") or "0")
        modified = (node.findtext(f"{ns}LastModified") or "").strip()
        items.append(
            {
                "key": key,
                "size": size,
                "last_modified": modified,
                "last_modified_dt": _parse_iso(modified),
            }
        )
    return items


def download_latest() -> tuple[dict, dict]:
    """自动拉取最新的 JSON 备份并解析，返回 (文件信息, payload)。"""
    items = [
        b
        for b in list_backups()
        if b["size"] > 0 and b["key"].lower().endswith(".json")
    ]
    if not items:
        raise CloudError("云端还没有备份文件，请先上传一次")
    latest = max(items, key=lambda b: b["last_modified_dt"])
    resp = _request(
        "GET", f"{ENDPOINT}/{BUCKET}/{quote(latest['key'], safe='/')}"
    )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise CloudError("云端文件不是有效的 JSON 备份") from exc
    if not isinstance(payload, dict) or "words" not in payload:
        raise CloudError("云端文件格式不正确，不是有效的单词备份")
    return latest, payload
