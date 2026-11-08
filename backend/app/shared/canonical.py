"""동일 자료의 JSON 직렬화·해시를 같은 규칙으로 만듭니다."""

import hashlib
import json
from pathlib import Path


def canonical_json(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
    )


def canonical_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def file_sha256(path: str | Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
