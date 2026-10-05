"""인용 가능한 값을 원자료 부모 경로별로 묶습니다."""

from app.evidence import SourceIndex

BRIEF_CONTEXT_KEYS = ("description", "summary", "summary_text", "interpretation")


def build_facts(index: SourceIndex, *, codes: set[str] | None = None) -> dict:
    """공통 자료는 유지하고 요청한 업종의 경로와 값을 손실 없이 묶습니다."""
    shared: dict = {}
    industries: dict = {}
    for record in index.records:
        if record.owner is not None and codes is not None and record.owner not in codes:
            continue
        groups = shared if record.owner is None else industries.setdefault(record.owner, {})
        parent, field = record.path.rsplit("/", 1)
        groups.setdefault(parent, {})[field] = record.value
    return {"shared": shared, "industries": industries}
