"""엘리스 클라우드의 OpenAI 호환 API를 호출합니다."""

import math
import os

from pydantic import ValidationError

from app.schemas import DecisionContent


def generate_decision(system_prompt: str, input_json: str) -> DecisionContent:
    """구조화 응답을 요청하며 실패를 샘플 결과로 대체하지 않습니다."""
    model = os.getenv("ELICE_MODEL", "").strip()
    if not model:
        raise ValueError("사용할 모델 식별자를 ELICE_MODEL에 설정해 주세요.")
    api_key = os.getenv("ELICE_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ELICE_API_KEY에 인증 키를 설정해 주세요.")
    base_url = os.getenv("ELICE_BASE_URL", "").strip()
    if not base_url:
        raise ValueError("ELICE_BASE_URL에 엘리스 기본 URL을 설정해 주세요.")
    try:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    except ValueError as exc:
        raise ValueError("응답 길이와 대기 시간은 양수로 설정해 주세요.") from exc
    if max_tokens <= 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("응답 길이와 대기 시간은 양수로 설정해 주세요.")

    try:
        from openai import APIError, APIStatusError, OpenAI
    except ImportError as exc:
        raise RuntimeError("OpenAI 호환 호출 라이브러리를 설치해 주세요: pip install -e .") from exc
    try:
        with OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input_json},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=max_tokens,
            )
    except APIStatusError as exc:
        detail = exc.body.get("message") if isinstance(exc.body, dict) else None
        suffix = f": {detail}" if isinstance(detail, str) else ""
        raise RuntimeError(f"모델 요청이 HTTP {exc.status_code}로 거절되었습니다{suffix}") from exc
    except APIError as exc:
        raise RuntimeError("모델 요청에 실패했습니다. 엘리스 키, URL, 모델 접근 권한과 연결 상태를 확인해 주세요.") from exc

    if not response.choices:
        raise RuntimeError("모델이 분석을 완료하지 못했습니다. 응답 거절 또는 길이 제한을 확인해 주세요.")
    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise RuntimeError("모델이 분석을 완료하지 못했습니다. 응답 거절 또는 길이 제한을 확인해 주세요.")
    try:
        return DecisionContent.model_validate_json(choice.message.content)
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors()[:3])
        raise RuntimeError(f"모델 응답 형식이 올바르지 않습니다. 확인 항목: {fields}") from exc
