"""원문·녹화·오류 기록의 비밀 정제 규칙입니다."""

import math
import os
import re
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

_AUTH_KEYS = {
    "apikey",
    "servicekey",
    "authorization",
    "proxyauthorization",
    "referer",
    "referrer",
    "xapikey",
    "accesskey",
    "accesstoken",
    "token",
    "password",
    "cookie",
    "setcookie",
    "key",
    "authkey",
    "crtfckey",
}


def _auth(name: str) -> bool:
    return re.sub(r"[^a-z0-9]", "", name.lower()) in _AUTH_KEYS


def env_secrets() -> list[str]:
    return [
        value
        for name, value in os.environ.items()
        if re.search(r"(?:_API_KEY|_TOKEN|_SECRET)$", name.upper()) and len(value) >= 8
    ]


def scrub_text(text: str, secrets=()) -> str:
    for secret in secrets:
        if secret:
            for encoded in {secret, quote(secret, safe=""), quote_plus(secret)}:
                text = text.replace(encoded, "[REDACTED]")
    if text.startswith(("https://", "http://")):
        url = urlsplit(text)
        parts = url.path.split("/")
        if url.hostname == "openapi.seoul.go.kr" and len(parts) > 2:
            parts[1] = "[REDACTED]"
        query = [(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True) if not _auth(k)]
        text = urlunsplit(
            (url.scheme, url.netloc.rsplit("@", 1)[-1], "/".join(parts), urlencode(query), "")
        )
    return text


def scrub(value, secrets=()):
    """인증 필드를 제거하고 비유한 수는 JSON null로 감사 기록합니다."""
    if isinstance(value, dict):
        return {str(k): scrub(v, secrets) for k, v in value.items() if not _auth(str(k))}
    if isinstance(value, (tuple, list)):
        return [scrub(v, secrets) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return scrub_text(value, secrets) if isinstance(value, str) else value
