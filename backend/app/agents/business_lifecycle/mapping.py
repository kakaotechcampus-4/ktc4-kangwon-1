"""개폐업에서 쓰는 이름은 유지하고 공통 75개 카탈로그를 재사용합니다."""

from app.industries.catalog import (
    EXCLUDED_SEOUL_INDUSTRIES,
)
from app.industries.catalog import (
    INDUSTRIES as SERVICE_INDUSTRIES,
)
from app.industries.catalog import (
    INDUSTRIES_WITHOUT_SEOUL as UNSUPPORTED_SERVICE_INDUSTRIES,
)
from app.industries.catalog import (
    SEOUL_TO_INDUSTRY as SEOUL_TO_SERVICE,
)

__all__ = [
    "EXCLUDED_SEOUL_INDUSTRIES",
    "SERVICE_INDUSTRIES",
    "UNSUPPORTED_SERVICE_INDUSTRIES",
    "SEOUL_TO_SERVICE",
]
