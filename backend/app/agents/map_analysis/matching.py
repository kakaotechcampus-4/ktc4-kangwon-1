"""검색 일치 상태는 코드 규칙이며 실제 경쟁점 확정 판정이 아닙니다."""

from app.industries.lookup import industry_terms

RULE_VERSION = "map-rules-1"
INDUSTRY_CATEGORIES = {"P105": "AC5", "Q102": "HP8", "I212": "CE7", "G215": "PM9"}


def distance_m(document):
    raw = document.get("distance")
    if not isinstance(raw, (str, int, float)):
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError, OverflowError):
        return None
    return value if value >= 0 else None


def match_place(industry_code, name, category_name, category_code, facility_code=None):
    if facility_code:
        return (
            ("category_match", RULE_VERSION + ":facility")
            if category_code == facility_code
            else ("unknown", None)
        )
    expected = INDUSTRY_CATEGORIES.get(industry_code)
    terms = [
        token.removesuffix("음식점").removesuffix("식당")
        for term in industry_terms(industry_code)["includes"]
        for token in term.split("/")
    ]

    def normalized(value):
        return value.replace(" ", "").casefold()

    if expected and category_code == expected:
        return "category_match", RULE_VERSION + ":category"
    if any(normalized(term) in normalized(category_name) for term in terms if term):
        return "category_match", RULE_VERSION + ":category-term"
    if any(normalized(term) in normalized(name) for term in terms if term):
        return "name_match", RULE_VERSION + ":name-term"
    return "unknown", None
