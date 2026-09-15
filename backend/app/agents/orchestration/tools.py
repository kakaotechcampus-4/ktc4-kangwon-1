"""오케스트레이터가 사용하는 기존 주소 변환 도구를 공개합니다.

목업 실행에서는 이 도구 대신 별도의 주소 변환 대역을 주입합니다.
"""

from app.address import resolve_site

__all__ = ["resolve_site"]

# 도구 인자는 비워 두고 요청 자료는 실행기가 관리합니다.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object", "properties": {}, "required": [],
                "additionalProperties": False,
            },
        },
    }
    for name, description in (
        ("prepare_address", "사용자 주소를 변환하고 분석 공통 입력을 준비합니다."),
        ("run_analyses", "주소 준비 후 세 분석 에이전트를 병렬 실행합니다."),
        ("make_decision", "분석 수집 후 최종판단 에이전트에 결과를 전달합니다."),
    )
]
