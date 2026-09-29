"""전송 공통화 후 에이전트의 설정 주입과 계산 보존을 검증합니다."""

import os
import unittest
from unittest.mock import AsyncMock, patch

from app.agents.decision.llm import generate_decision
from app.llm.config import LLMSettings


class CallerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(
            patch(
                "httpx.AsyncHTTPTransport.handle_async_request",
                side_effect=AssertionError("외부 연결 금지"),
            )
        )
        self.settings = LLMSettings(
            model="injected", api_key="test", base_url="https://invalid.example/v1"
        )

    async def test_decision_injection_keeps_schema_validation_and_safe_fields(self):
        payload = {"SECRET-KEY": "private"}
        with patch("app.llm.client.complete_json", new=AsyncMock(return_value=payload)) as call:
            with self.assertRaises(RuntimeError) as raised:
                await generate_decision("지침", "{}", settings=self.settings)
        self.assertNotIn("SECRET-KEY", str(raised.exception))
        self.assertIs(call.call_args.args[2], self.settings)

    async def test_mapping_examples_share_transport_and_keep_matching_policy(self):
        from examples import match_upjong, match_upjong_by_small

        settings = LLMSettings(model="test", api_key="test", base_url="https://invalid.example/v1")
        rows = [{"SVC_INDUTY_CD": "CS100001", "SVC_INDUTY_CD_NM": "한식"}]
        with patch(
            "app.llm.client.complete_json",
            new=AsyncMock(
                return_value={"matches": [{"seoul_code": "CS100001", "candidates": ["I201"]}]}
            ),
        ):
            self.assertEqual(await match_upjong.ask(settings, [], rows), {"CS100001": ["I201"]})
        picks = {}
        with patch(
            "app.llm.client.complete_json",
            new=AsyncMock(
                return_value={"matches": [{"seoul_code": "CS100001", "small_codes": ["s1", "bad"]}]}
            ),
        ):
            await match_upjong_by_small.fill_with_model(
                settings, {"s1": ("한식", "I201")}, rows, picks, {}
            )
        self.assertEqual(picks, {"CS100001": (["s1"], "모델")})
