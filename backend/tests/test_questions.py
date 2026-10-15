"""도구 루프의 질문 개수·중복·문장 길이 경계를 검증합니다."""

import unittest

from app.agentic.contracts import AskUserInput, UserQuestion


class QuestionTests(unittest.TestCase):
    def test_count_and_duplicate_fields(self):
        def question(field="floor"):
            return dict(field=field, question="몇 층인가요?", reason="접근성 확인")

        for fields in (
            [],
            ["floor", "floor"],
            ["floor", "exclusive_area", "space_condition", "existing_facilities"],
            ["secret"],
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                AskUserInput(questions=[question(field) for field in fields])
        self.assertEqual(len(AskUserInput(questions=[question()]).questions), 1)

    def test_question_and_reason_lengths(self):
        question = dict(field="floor", question="몇 층인가요?", reason="접근성 확인")
        for field in ("question", "reason"):
            for value in ("", " ", "가" * 201):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    UserQuestion.model_validate({**question, field: value})
            self.assertEqual(
                len(getattr(UserQuestion.model_validate({**question, field: "가" * 200}), field)),
                200,
            )
