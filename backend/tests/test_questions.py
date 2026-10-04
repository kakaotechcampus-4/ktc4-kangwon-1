"""임대인 질문 계약과 답변 정규화의 경계를 검사합니다."""

import unittest

from app import schemas as s


def question(field="floor"):
    return dict(
        field=field, text="몇 층인가요?", why_needed="접근성 확인", expected_impact="후보 검토"
    )


class QuestionTests(unittest.TestCase):
    def test_question_count_and_duplicates(self):
        self.assertTrue(hasattr(s, "QuestionPlan"), "질문 계약이 필요합니다.")
        for fields in (
            [],
            ["floor", "floor"],
            ["floor", "exclusive_area", "space_condition", "existing_facilities"],
            ["secret"],
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                s.QuestionPlan(action="ask_user", questions=[question(f) for f in fields])
        self.assertEqual(
            len(s.QuestionPlan(action="ask_user", questions=[question()]).questions), 1
        )

    def test_answer_status_and_length(self):
        self.assertTrue(hasattr(s, "LandlordAnswer"))
        for status, value in (
            ("answered", None),
            ("answered", " "),
            ("answered", "가" * 1001),
            ("unknown", "2층"),
            ("skipped", "2층"),
        ):
            with self.subTest(status=status, value=value), self.assertRaises(ValueError):
                s.LandlordAnswer(field="floor", status=status, value=value)
        self.assertEqual(
            len(s.LandlordAnswer(field="floor", status="answered", value="가" * 1000).value), 1000
        )

    def test_normalization_fills_missing_and_rejects_other_questions(self):
        self.assertTrue(hasattr(s, "WaitingForInput"))
        waiting = s.WaitingForInput(
            request_id="r",
            question_set_id="q",
            questions=[question("floor"), question("exclusive_area")],
        )
        submission = s.AnswerSubmission(
            request_id="r",
            question_set_id="q",
            answers=[dict(field="floor", status="answered", value="2층")],
        )
        normalized = s.normalize_answers(waiting, submission)
        self.assertEqual(
            [(a.field, a.status) for a in normalized.answers],
            [("exclusive_area", "skipped"), ("floor", "answered")],
        )
        for change in (
            dict(request_id="other"),
            dict(question_set_id="other"),
            dict(answers=[dict(field="existing_facilities", status="unknown")]),
            dict(answers=[dict(field="floor", status="unknown")] * 2),
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                s.normalize_answers(
                    waiting,
                    s.AnswerSubmission.model_validate({**submission.model_dump(), **change}),
                )

    def test_snapshot_identifiers_and_attempts(self):
        self.assertTrue(hasattr(s, "QuestionSnapshot"))
        payload = dict(
            version=1,
            task=dict(
                request_id="r",
                site=dict(
                    input_address="주소", road_address="도로", latitude=37.0, longitude=127.0
                ),
            ),
            waiting=dict(request_id="r", question_set_id="q", questions=[question()]),
            source_attempts=dict.fromkeys(s.AGENT_IDS, 1),
            supplement_done=False,
            feedback=[],
        )
        self.assertEqual(s.QuestionSnapshot.model_validate(payload).version, 1)
        for change in (
            dict(version=2),
            dict(source_attempts={}),
            dict(source_attempts=dict.fromkeys(s.AGENT_IDS, True)),
            dict(waiting={**payload["waiting"], "request_id": "other"}),
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                s.QuestionSnapshot.model_validate({**payload, **change})
