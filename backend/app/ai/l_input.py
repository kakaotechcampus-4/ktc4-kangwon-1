"""단순 판단 입력을 기존 검증용 L 기록으로 변환합니다."""

from app.ai.aliases import decode
from app.ai.tool_contracts import LInput
from app.application.ports.storage import open_stores
from app.application.report import fact_rows
from app.domain.l_record import assemble_record


def build_record(scope, raw, base_id, base_rows):
    item = LInput.model_validate(decode(scope, raw))
    ids = {factor.fact_id for factor in item.factors} | set(item.fact_ids)
    facts = fact_rows(scope, ids)
    with open_stores(scope) as st:
        calls = [
            call.tool_call_id
            for call in st.agentic.decision_tool_calls(scope.request_id, scope.snapshot_id)
            if call.reply["status"] in {"ok", "partial"}
            and any(fid in call.reply_text for fid in ids)
        ]
    return assemble_record(item, facts, calls, base_id, base_rows)
