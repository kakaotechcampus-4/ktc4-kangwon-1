"""새 요청 경계의 예외를 안전한 HTTP 오류로 변환합니다."""

import logging

from fastapi import HTTPException

from app.api.v1.jobs import request_headers
from app.application.errors import ADDRESS_INPUT_ERRORS, AddressError
from app.application.errors import AnalysisConflictError as AnalysisConflictError
from app.shared.logging import log_exception

logger = logging.getLogger(__name__)


async def run_or_http(work, request_id, *, kind):
    try:
        return await work
    except HTTPException:
        raise
    except AddressError as exc:
        invalid = exc.code in ADDRESS_INPUT_ERRORS
        raise HTTPException(
            400 if invalid else 502,
            "주소를 확인해 주세요." if invalid else "주소 조회 서비스에 실패했습니다.",
            headers=request_headers(request_id),
        ) from None
    except AnalysisConflictError:
        raise HTTPException(
            409, "이미 처리했거나 대기 중인 질문이 없습니다.", headers=request_headers(request_id)
        ) from None
    except (RuntimeError, TimeoutError):
        raise HTTPException(
            502, "분석 서비스에 실패했습니다.", headers=request_headers(request_id)
        ) from None
    except Exception as exc:
        log_exception(logger, "분석 처리 실패: request_id=%s", exc, request_id)
        raise HTTPException(
            500, "분석 결과 처리 또는 저장에 실패했습니다.", headers=request_headers(request_id)
        ) from None
