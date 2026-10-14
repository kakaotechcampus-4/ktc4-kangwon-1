"""서버·CLI 진입점에서 환경을 읽고 요청에 명시적으로 전달할 설정입니다."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from app.agents.business_lifecycle.config import Settings as LifecycleSettings
from app.agents.commercial_area.config import Settings as CommercialSettings
from app.agents.floating_population.config import Settings as FloatingSettings
from app.config import AddressSettings
from app.db.connection import resolve_path
from app.execution.validation import validate_timeout
from app.llm.config import LLMSettings
from app.schemas import AnalysisMode, SpecialistId

# 기존 설정 경고를 수집하는 운영·테스트 경로를 유지합니다.
logger = logging.getLogger("app.services.settings")


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {"true", "false", "1", "0"}:
        raise ValueError(f"{name}은 true/false 또는 1/0이어야 합니다.")
    return value.lower() in {"true", "1"}


@dataclass(frozen=True)
class ExecutionSettings:
    address: AddressSettings = field(default_factory=AddressSettings)
    floating: FloatingSettings = field(default_factory=FloatingSettings)
    commercial: CommercialSettings = field(default_factory=CommercialSettings)
    lifecycle: LifecycleSettings = field(default_factory=LifecycleSettings)
    decision_llm: LLMSettings = field(default_factory=LLMSettings)
    db_path: str | Path | None = None
    agent_timeout: float = 180.0
    # 생성 시 평가자 여부에 맞춘 기본값을 확정하며 명시한 시간은 유지합니다.
    overall_timeout: float = None  # type: ignore[assignment]
    analysis_mode: AnalysisMode = "single_decision"
    evaluators_enabled: bool = False
    evaluator_llm: LLMSettings = field(default_factory=LLMSettings)
    specialist_llms: dict[SpecialistId, LLMSettings] = field(default_factory=dict)
    # 백그라운드(wait=false) 동시 분석 수. 분석 1회가 외부 요청을 100회 넘게 만듭니다.
    max_concurrency: int = 2

    def __post_init__(self) -> None:
        if self.overall_timeout is None:
            object.__setattr__(
                self, "overall_timeout", 1200.0 if self.evaluators_enabled else 600.0
            )
        validate_timeout(self.agent_timeout)
        validate_timeout(self.overall_timeout)
        if type(self.max_concurrency) is not int or self.max_concurrency < 1:
            raise ValueError("동시 분석 수는 1 이상의 정수여야 합니다.")
        if self.analysis_mode not in get_args(AnalysisMode):
            raise ValueError("지원하지 않는 분석 모드입니다.")
        if type(self.evaluators_enabled) is not bool:
            raise ValueError("평가자 사용 여부는 참 또는 거짓이어야 합니다.")

    @property
    def briefing_enabled(self) -> bool:
        return self.analysis_mode == "multi_agent"

    @classmethod
    def from_env(cls) -> "ExecutionSettings":
        return cls(
            address=AddressSettings.from_env(),
            floating=FloatingSettings.from_env(),
            commercial=CommercialSettings.from_env(),
            lifecycle=LifecycleSettings.from_env(),
            decision_llm=LLMSettings.from_env("DECISION"),
            db_path=resolve_path(),
            agent_timeout=float(os.getenv("ANALYSIS_AGENT_TIMEOUT_SECONDS", "180")),
            overall_timeout=float(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "600")),
            evaluator_llm=LLMSettings.from_env("EVALUATOR"),
            max_concurrency=int(os.getenv("ANALYSIS_MAX_CONCURRENCY", "2")),
        )
