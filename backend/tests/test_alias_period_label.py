"""심사위원에게 보내는 fact 기간 코드만 읽기 쉬운 분기 표기로 바꾸는지 검사합니다."""

import json
import unittest

from app.agentic.aliases import (
    decode,
    encode,
    encode_messages,
    label_periods,
    labels_periods,
)
from tests import test_simple_l_inputs as fixtures


class PeriodLabelTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SimpleLTests.asyncSetUp
    asyncTearDown = fixtures.SimpleLTests.asyncTearDown

    def test_quarter_codes_are_spelled_out(self):
        facts = [
            {"period": "20231~20234"},
            {"period": "20234"},
            {"period": "20224~20234"},
        ]
        out = label_periods({"facts": facts})
        self.assertEqual(
            [f["period"] for f in out["facts"]],
            ["2023년 1분기~4분기", "2023년 4분기", "2022년 4분기~2023년 4분기"],
        )
        self.assertEqual(facts[0]["period"], "20231~20234")

    def test_other_periods_and_keys_are_kept(self):
        value = {
            "facts": [
                {"period": "승인 기준선·프로필"},
                {"period": "2026년 2분기"},
                {"period": "20235"},
                {"period": "2023-10-27T10:00:00"},
            ],
            "period_code": "20234",
            "quarter": "20234",
        }
        self.assertEqual(label_periods(value), value)

    def test_encode_keeps_period_codes(self):
        value = {"facts": [{"period": "20231~20234"}]}
        self.assertEqual(encode(self.scope, value), value)

    def test_model_output_periods_are_not_rewritten(self):
        self.assertEqual(decode(self.scope, {"period": "20234"}), {"period": "20234"})

    def test_tool_reply_messages_are_spelled_out_only_when_asked(self):
        body = {"facts": [{"period": "20253~20262"}]}
        messages = [{"role": "tool", "content": json.dumps(body)}]
        labeled = encode_messages(self.scope, messages, label=True)
        self.assertEqual(
            json.loads(labeled[0]["content"])["facts"][0]["period"],
            "2025년 3분기~2026년 2분기",
        )
        plain = encode_messages(self.scope, messages)
        self.assertEqual(json.loads(plain[0]["content"])["facts"][0]["period"], "20253~20262")

    def test_only_examiner_gets_spelled_out_periods(self):
        self.assertTrue(labels_periods("examiner"))
        for role in ("decision", "founder", "customer", "landlord_advocate", "advisor"):
            self.assertFalse(labels_periods(role))
