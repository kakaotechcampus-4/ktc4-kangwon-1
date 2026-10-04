"""서버·CLI 진입점에서 환경을 읽고 요청에 명시적으로 전달할 설정입니다."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from app.agents.business_lifecycle.config import Settings as LifecycleSettings
from app.agents.commercial_area.config import Settings as CommercialSettings
from app.agents.floating_population.config import Settings as FloatingSettings
from app.config import AddressSettings
from app.db.connection import resolve_path
from app.llm.config import LLMSettings
from app.schemas import AnalysisMode, SpecialistId


def validate_timeout(value: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("실행 제한시간은 유한한 양수여야 합니다.")


@dataclass(frozen=True)
class ExecutionSettings:
    address: AddressSettings = field(default_factory=AddressSettings)
    floating: FloatingSettings = field(default_factory=FloatingSettings)
    commercial: CommercialSettings = field(default_factory=CommercialSettings)
    lifecycle: LifecycleSettings = field(default_factory=LifecycleSettings)
    decision_llm: LLMSettings = field(default_factory=LLMSettings)
    db_path: str | Path | None = None
    agent_timeout: float = 180.0
    overall_timeout: float = 600.0
    analysis_mode: AnalysisMode = "single_decision"
    specialist_llms: dict[SpecialistId, LLMSettings] = field(default_factory=dict)
    # 백그라운드(wait=false) 동시 분석 수. 분석 1회가 외부 요청을 100회 넘게 만듭니다.
    max_concurrency: int = 2

    def __post_init__(self) -> None:
        validate_timeout(self.agent_timeout)
        validate_timeout(self.overall_timeout)
        if type(self.max_concurrency) is not int or self.max_concurrency < 1:
            raise ValueError("동시 분석 수는 1 이상의 정수여야 합니다.")
        if self.analysis_mode not in get_args(AnalysisMode):
            raise ValueError("지원하지 않는 분석 모드입니다.")

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
            analysis_mode=os.getenv("ANALYSIS_MODE", "single_decision"),  # type: ignore[arg-type]
            max_concurrency=int(os.getenv("ANALYSIS_MAX_CONCURRENCY", "2")),
            specialist_llms={
                role: LLMSettings.from_env(f"SPECIALIST_{role.upper()}")
                for role in get_args(SpecialistId)
            },
        )
