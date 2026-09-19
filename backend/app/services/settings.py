"""서버·CLI 진입점에서 환경을 읽고 요청에 명시적으로 전달할 설정입니다."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.agents.business_lifecycle.config import Settings as LifecycleSettings
from app.agents.commercial_area.config import Settings as CommercialSettings
from app.agents.floating_population.config import Settings as FloatingSettings
from app.config import AddressSettings
from app.db.connection import resolve_path
from app.llm.config import LLMSettings


def validate_timeout(value: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("실행 제한시간은 유한한 양수여야 합니다.")


@dataclass(frozen=True)
class ExecutionSettings:
    address: AddressSettings = field(default_factory=AddressSettings)
    floating: FloatingSettings = field(default_factory=FloatingSettings)
    commercial: CommercialSettings = field(default_factory=CommercialSettings)
    lifecycle: LifecycleSettings = field(default_factory=LifecycleSettings)
    floating_llm: LLMSettings = field(default_factory=LLMSettings)
    lifecycle_llm: LLMSettings = field(default_factory=LLMSettings)
    orchestration_llm: LLMSettings = field(default_factory=LLMSettings)
    decision_llm: LLMSettings = field(default_factory=LLMSettings)
    db_path: str | Path | None = None
    agent_timeout: float = 180.0
    overall_timeout: float = 600.0

    def __post_init__(self) -> None:
        validate_timeout(self.agent_timeout)
        validate_timeout(self.overall_timeout)

    @classmethod
    def from_env(cls) -> "ExecutionSettings":
        return cls(
            address=AddressSettings.from_env(),
            floating=FloatingSettings.from_env(),
            commercial=CommercialSettings.from_env(),
            lifecycle=LifecycleSettings.from_env(),
            floating_llm=LLMSettings.from_env("FLOATING_POPULATION"),
            lifecycle_llm=LLMSettings.from_env("BUSINESS_LIFECYCLE"),
            orchestration_llm=LLMSettings.from_env("ORCHESTRATION"),
            decision_llm=LLMSettings.from_env("DECISION"),
            db_path=resolve_path(),
            agent_timeout=float(os.getenv("ANALYSIS_AGENT_TIMEOUT_SECONDS", "180")),
            overall_timeout=float(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "600")),
        )
