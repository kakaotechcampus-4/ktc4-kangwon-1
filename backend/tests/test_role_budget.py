"""역할 예약·평가자 도구·짧은 입력 오류를 모델 대역으로 검증합니다."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.agentic import evaluators
from app.agentic.budget import RuntimeBudget
from app.agentic.contracts import FactsResult, ToolReply
from app.agentic.space import ensure_space_fits
from app.agentic.sql_tool import error
from app.agentic.tools import EVALUATORS, ToolExecutor
from app.canonical import canonical_json
from app.llm.budget import BudgetExceeded
from app.services.mock import call
from tests import test_space_fit as space_fixtures


class RoleBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_call_partitions_including_measurement(self):
        for measurement in (False, True):
            budget = RuntimeBudget(measurement=measurement)
            for _ in range(20):
                await budget.reserve("decision", input_chars=0)
            with self.assertRaises(BudgetExceeded):
                await budget.reserve("decision")
            for role, count in [("advisor", 2), *[(role, 4) for role in EVALUATORS]]:
                for _ in range(count):
                    await budget.reserve(role)
                with self.assertRaises(BudgetExceeded):
                    await budget.reserve(role)
            self.assertEqual(budget.used, 38)
            await budget.reserve("decision", final=True)
            await budget.reserve("decision", final=True)
            with self.assertRaises(BudgetExceeded):
                await budget.reserve("decision", final=True)
            self.assertEqual(budget.used, 40)

    async def test_all_output_reservations_fit_and_cannot_borrow(self):
        budget = RuntimeBudget(measurement=True)
        reservations = [
            ("decision", False, await budget.claim_output(16000, role="decision")),
            ("decision", False, await budget.claim_output(16000, role="decision")),
            ("decision", True, await budget.claim_output(16000, role="decision", final=True)),
            ("advisor", False, await budget.claim_output(16000, role="advisor")),
        ]
        for role in EVALUATORS:
            reservations.append((role, False, await budget.claim_output(5500, role=role)))
            with self.assertRaises(BudgetExceeded):
                await budget.claim_output(1, role=role)
        self.assertEqual([row[2] for row in reservations[:4]], [16000, 14000, 6000, 2000])
        self.assertEqual(sum(row[2] for row in reservations), 60000)
        for role, final, reserved in reservations:
            await budget.release_output(reserved, role=role, final=final)
        self.assertEqual(budget.pending_output, 0)

    async def test_pending_inputs_are_atomic_and_actual_usage_releases_estimate(self):
        budget = RuntimeBudget()
        attempts = await asyncio.gather(
            budget.reserve("examiner", input_chars=48000),
            budget.reserve("examiner", input_chars=48000),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(value, int) for value in attempts), 1)
        self.assertEqual(sum(isinstance(value, BudgetExceeded) for value in attempts), 1)
        await budget.finish(
            1,
            status="completed",
            elapsed_ms=1,
            usage=SimpleNamespace(prompt_tokens=10000, completion_tokens=50),
        )
        self.assertEqual(await budget.reserve("examiner", input_chars=60000), 2)
        self.assertEqual(await budget.reserve("founder", input_chars=80000), 3)

    async def test_resume_preserves_role_and_phase_usage(self):
        budget = RuntimeBudget()
        attempt = await budget.reserve("decision", input_chars=360000)
        await budget.finish(
            attempt,
            status="completed",
            elapsed_ms=1,
            usage=SimpleNamespace(prompt_tokens=180000, completion_tokens=30000),
        )
        resumed = RuntimeBudget(budget.snapshot(), measurement=True)
        self.assertEqual(await resumed.reserve("customer", input_chars=80002), 2)
        with self.assertRaises(BudgetExceeded):
            await resumed.claim_output(1, role="decision")
        self.assertEqual(await resumed.claim_output(16000, role="decision", final=True), 6000)
        self.assertEqual(await resumed.reserve("decision", final=True, input_chars=100000), 3)
        self.assertEqual(await resumed.reserve("customer", input_chars=80000), 4)

    async def test_role_schema_is_used_without_decision_schema(self):
        budget = RuntimeBudget()
        budget.schema_chars = 100000
        budget.schema_chars_by_role["examiner"] = 1000
        await budget.reserve("examiner", input_chars=1000)
        self.assertEqual(budget.calls[0]["estimated_input"], 1000)

    async def test_submit_reservations_bypass_role_limits_but_keep_global_limit(self):
        budget = RuntimeBudget(
            {
                "used": 4,
                "calls": [{"role": "examiner", "input_tokens": 45000, "output_tokens": 5500}] * 4,
            }
        )
        budget.submitting.add("examiner")
        self.assertEqual(await budget.reserve("examiner", input_chars=1), 5)
        reserved = await budget.claim_output(4000, role="examiner")
        self.assertEqual(reserved, 4000)
        await budget.release_output(reserved, role="examiner")
        budget.input_limit = 180000
        with self.assertRaises(BudgetExceeded):
            await budget.reserve("examiner", input_chars=1)


class EvaluatorToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        decode = patch("app.agentic.tools.decode", side_effect=lambda scope, value: value)
        decode.start()
        self.addCleanup(decode.stop)
        report = patch(
            "app.agentic.tools.decode_report", side_effect=lambda scope, value: (value, [])
        )
        report.start()
        self.addCleanup(report.stop)

    def executor(self, actor="examiner", measurement=False, handlers=None):
        executor = ToolExecutor(
            SimpleNamespace(snapshot_id="snapshot"), None, actor=actor, handlers=handlers
        )
        executor.shared.measurement = measurement
        return executor

    async def test_examiner_reads_without_raw_rows_and_others_keep_four_tools(self):
        founder = self.executor("founder")
        self.assertEqual(
            {definition["function"]["name"] for definition in founder.definitions()},
            {"get_scorecard", "get_facts", "query_raw", "submit_review"},
        )
        with patch("app.agentic.tools._audit"):
            denied = await self.executor().execute("query_raw", {"sql": "SELECT 1"})
        self.assertEqual(denied.error.code, "INVALID_ARGUMENT")

    async def test_get_facts_rule_message_names_the_broken_rule(self):
        executor = self.executor()
        with patch("app.agentic.tools._audit"):
            reply = await executor.execute("get_facts", {"source": "commercial_area"})
        self.assertEqual(reply.error.code, "INVALID_ARGUMENT")
        self.assertIn("업종·출처·지표를 모두 지정해야 합니다.", reply.error.message)
        self.assertLessEqual(len(reply.error.message), 400)

    async def test_only_three_examiner_tools_and_three_reads_in_measurement(self):
        expected = {"get_scorecard", "get_facts", "submit_review"}
        for measurement in (False, True):
            executor = self.executor(
                measurement=measurement,
                handlers={
                    "get_scorecard": AsyncMock(return_value=ToolReply(status="ok", data={})),
                    "submit_review": AsyncMock(return_value=ToolReply(status="ok", data={})),
                },
            )
            self.assertEqual(
                {definition["function"]["name"] for definition in executor.definitions()}, expected
            )
            with patch("app.agentic.tools._audit"):
                for limit in (1, 2, 3):
                    self.assertEqual(
                        (await executor.execute("get_scorecard", {"limit": limit})).status, "ok"
                    )
                fourth = await executor.execute("get_scorecard", {"limit": 4})
                self.assertEqual(fourth.error.code, "BUDGET_EXCEEDED")
                submitted = await executor.execute(
                    "submit_review", {"draft_id": "draft", "verdict": "agree", "issues": []}
                )
                self.assertEqual(submitted.status, "ok")
                repeated = await executor.execute(
                    "submit_review", {"draft_id": "other", "verdict": "agree", "issues": []}
                )
                self.assertEqual(repeated.status, "ok")
                self.assertEqual(executor.shared.calls[("examiner", "submit_review")], 0)

    async def test_submit_l_handler_is_allowed_and_not_a_read(self):
        executor = self.executor(
            "decision",
            handlers={"submit_l": AsyncMock(return_value=ToolReply(status="ok", data={}))},
        )
        executor.shared.calls[("decision", "total")] = 20
        with patch("app.agentic.tools._audit"):
            reply = await executor.execute("submit_l", {"L_records": [], "finish": True})
        self.assertEqual(reply.status, "ok")
        self.assertEqual(executor.shared.calls[("decision", "total")], 20)

    async def test_submit_l_repeated_arguments_reach_the_handler(self):
        handler = AsyncMock(
            side_effect=[
                ToolReply(status="ok", data={}),
                error("DUPLICATE_INDUSTRY", "이미 채택한 업종입니다."),
            ]
        )
        executor = self.executor("decision", handlers={"submit_l": handler})
        arguments = {"finish": True}
        with patch("app.agentic.tools._audit"):
            self.assertEqual((await executor.execute("submit_l", arguments)).status, "ok")
            repeated = await executor.execute("submit_l", arguments)
        self.assertEqual(repeated.error.code, "DUPLICATE_INDUSTRY")
        self.assertFalse(repeated.duplicate)
        self.assertEqual(handler.await_count, 2)

    async def test_validation_error_exposes_path_type_and_cap_only(self):
        executor = self.executor("decision")
        arguments = {
            "phase": "draft",
            "report": {"candidates": [{"industry_code": "I201"}] * 6},
            "secret-field-name": "secret-value",
        }
        with patch("app.agentic.tools._audit"):
            reply = await executor.execute("submit_draft", arguments)
        self.assertEqual(reply.error.code, "INVALID_ARGUMENT")
        self.assertIn("report.candidates", reply.error.message)
        self.assertIn("too_long", reply.error.message)
        self.assertIn("max=5", reply.error.message)
        self.assertNotIn("secret-field-name", reply.error.message)
        self.assertNotIn("secret-value", reply.error.message)
        self.assertLessEqual(len(reply.error.message), 400)


class EvaluatorContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        decode = patch("app.agentic.tools.decode", side_effect=lambda scope, value: value)
        decode.start()
        self.addCleanup(decode.stop)

    def draft(self):
        records = [
            {
                "industry_code": "I201",
                "status": "observed",
                "grade": 3,
                "selection": {
                    "basis": "all_industries",
                    "code_score_snapshot_id": "base",
                    "code_lower_rank": 1,
                    "reason": "전체 업종",
                },
                "new_factors": [
                    {
                        "direction": "favorable",
                        "claim": "확인된 운영 조건",
                        "fact_ids": ["fact"],
                        "major_constraint": False,
                    }
                ],
            }
        ]
        data = {
            "report_id": "draft",
            "snapshot_id": "snapshot",
            "top5": [{"industry_code": "I201", "code_points": 60, "L_points": 7.5}],
            "L_records": records,
            "facts": [
                {
                    "fact_id": "fact",
                    "value": "일치",
                    "status": "observed",
                    "citable": True,
                    "spatial_scope": {"radius_m": 500},
                    "calc_version": "calc",
                    "provenance_ref": "local_fact_lineage:fact",
                }
            ]
            * 2,
        }
        return SimpleNamespace(
            report_id="draft", model_dump=MagicMock(return_value=json.loads(canonical_json(data)))
        )

    async def test_packet_preserves_candidate_evidence_and_grade_counts(self):
        draft = self.draft()
        full = json.loads(canonical_json(draft.model_dump(mode="json")))
        compressed = evaluators.compact_draft(draft)
        self.assertNotIn("L_records", compressed)
        for key in ("new_factors", "industry_code", "status", "grade"):
            self.assertEqual(compressed["candidate_factors"][0][key], full["L_records"][0][key])
        self.assertEqual(compressed["L_counts"], {"3": 1})
        self.assertTrue(all(f["fact_id"] == "fact" for f in compressed["facts"]))
        self.assertLess(len(canonical_json(compressed)), len(canonical_json(full)))

    async def test_four_evaluators_complete_with_role_reservations(self):
        budget = RuntimeBudget()
        scope = SimpleNamespace(snapshot_id="snapshot")
        shared_executor = ToolExecutor(scope, None)
        entered, ready = set(), asyncio.Event()

        async def model(role, messages, settings, definitions):
            reserved = await budget.claim_output(settings.max_tokens, role=role)
            attempt = await budget.reserve(role, input_chars=len(canonical_json(messages)))
            entered.add(role)
            if len(entered) == 4:
                ready.set()
            await asyncio.wait_for(ready.wait(), 2)
            await budget.finish(
                attempt,
                status="completed",
                elapsed_ms=1,
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=200),
            )
            await budget.release_output(reserved, role=role)
            return call(
                "submit_review", {"draft_id": "draft", "verdict": "agree", "issues": []}
            ), {}

        loop = SimpleNamespace(scope=scope, budget=budget, _model=model, event=AsyncMock())
        with (
            patch("app.agentic.evaluators.fact_rows", return_value={}),
            patch("app.agentic.evaluators.save_review"),
            patch(
                "app.agentic.landlord.review_packet",
                return_value=evaluators.compact_draft(self.draft()),
            ),
            patch("app.agentic.customer_rubric.code_checks", return_value=([], [], set())),
            patch("app.agentic.customer_rubric.packet", return_value={"draft_id": "draft"}),
            patch("app.agentic.tools._audit"),
            patch("app.agentic.evaluators.encode", side_effect=lambda scope, value: value),
            patch(
                "app.agentic.examiner.review_packet",
                return_value=evaluators.compact_draft(self.draft()),
            ),
        ):
            reviews = await asyncio.gather(
                *(
                    evaluators.review(loop, actor, shared_executor.for_actor(actor), self.draft())
                    for actor in EVALUATORS
                )
            )
        self.assertEqual(len(reviews), 4)
        self.assertTrue(all(item.status == "completed" for item in reviews))
        self.assertEqual(budget.pending_output, 0)

    async def test_three_reads_then_invalid_submission_gets_two_corrections(self):
        budget = RuntimeBudget()
        scope = SimpleNamespace(snapshot_id="snapshot")
        executor = ToolExecutor(scope, None, actor="examiner")
        sequence = [call("get_scorecard", {"limit": limit}) for limit in (1, 2, 3)] + [
            call("submit_review", {"draft_id": draft_id, "verdict": "agree", "issues": []})
            for draft_id in ("wrong", "wrong", "draft")
        ]
        definitions_seen = []

        async def model(role, messages, settings, definitions):
            definitions_seen.append({d["function"]["name"] for d in definitions})
            reservation = await budget.claim_output(settings.max_tokens, role=role)
            attempt = await budget.reserve(role, input_chars=len(canonical_json(messages)))
            await budget.finish(
                attempt,
                status="completed",
                elapsed_ms=1,
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=100),
            )
            await budget.release_output(reservation, role=role)
            return sequence.pop(0), {}

        loop = SimpleNamespace(scope=scope, budget=budget, _model=model, event=AsyncMock())
        with (
            patch(
                "app.agentic.tools.get_scorecard",
                AsyncMock(return_value=ToolReply(status="ok", data={})),
            ),
            patch("app.agentic.evaluators.fact_rows", return_value={}),
            patch("app.agentic.evaluators.save_review"),
            patch("app.agentic.tools._audit"),
            patch("app.agentic.evaluators.encode", side_effect=lambda scope, value: value),
            patch(
                "app.agentic.examiner.review_packet",
                return_value=evaluators.compact_draft(self.draft()),
            ),
        ):
            result = await evaluators.review(loop, "examiner", executor, self.draft())
        self.assertEqual(result.status, "completed")
        self.assertEqual(budget.used, 6)
        self.assertEqual(definitions_seen[3:], [{"submit_review"}] * 3)
        self.assertEqual(executor.shared.calls[("examiner", "total")], 3)
        self.assertFalse(budget.submitting)
        self.assertEqual(
            loop.event.await_args_list[-1].args,
            (
                "evaluation",
                "completed",
                {
                    "actor": "examiner",
                    "error_code": None,
                    "issues_count": 0,
                    "reads": 3,
                    "rejections": 2,
                    "model_calls": 6,
                },
            ),
        )

    async def test_final_event_counts_accepted_issues(self):
        scope = SimpleNamespace(snapshot_id="snapshot")
        executor = ToolExecutor(scope, None, actor="examiner")
        fact_id = "f_00000000-0000-4000-8000-000000000001"
        issue = {
            "issue_id": "evidence",
            "target": "claim",
            "kind": "missing_evidence",
            "comment": "문장의 근거가 없습니다.",
            "fact_ids": [fact_id],
            "suggested_check": "근거를 붙이세요.",
        }
        message = call(
            "submit_review", {"draft_id": "draft", "verdict": "conditional", "issues": [issue]}
        )
        loop = SimpleNamespace(
            scope=scope,
            budget=RuntimeBudget(),
            _model=AsyncMock(return_value=(message, {})),
            event=AsyncMock(),
        )
        with (
            patch(
                "app.agentic.evaluators.fact_rows",
                return_value={fact_id: {"citable": True, "status": "observed"}},
            ),
            patch("app.agentic.evaluators.save_review"),
            patch("app.agentic.tools._audit"),
            patch("app.agentic.evaluators.encode", side_effect=lambda scope, value: value),
            patch(
                "app.agentic.examiner.review_packet",
                return_value=evaluators.compact_draft(self.draft()),
            ),
        ):
            result = await evaluators.review(loop, "examiner", executor, self.draft())
        self.assertEqual(result.status, "completed")
        self.assertEqual(
            loop.event.await_args_list[-1].args[2],
            {
                "actor": "examiner",
                "error_code": None,
                "issues_count": 1,
                "reads": 0,
                "rejections": 0,
                "model_calls": 1,
            },
        )

    async def test_final_event_counts_zero_when_packet_fails(self):
        scope = SimpleNamespace(snapshot_id="snapshot")
        loop = SimpleNamespace(
            scope=scope, budget=RuntimeBudget(), _model=AsyncMock(), event=AsyncMock()
        )
        with (
            patch("app.agentic.examiner.review_packet", side_effect=ValueError("over")),
            patch("app.agentic.evaluators.save_review"),
        ):
            result = await evaluators.review(
                loop, "examiner", ToolExecutor(scope, None, actor="examiner"), self.draft()
            )
        self.assertEqual(result.error_code, "SOURCE_UNAVAILABLE")
        loop._model.assert_not_awaited()
        self.assertEqual(
            loop.event.await_args_list[-1].args,
            (
                "evaluation",
                "failed",
                {
                    "actor": "examiner",
                    "error_code": "SOURCE_UNAVAILABLE",
                    "issues_count": 0,
                    "reads": 0,
                    "rejections": 0,
                    "model_calls": 0,
                },
            ),
        )

    async def test_packet_all_industry_counts_without_all_industry_records(self):
        draft = self.draft()
        payload = draft.model_dump(mode="json")
        original = payload["L_records"][0]
        payload["L_records"] = [
            dict(original, industry_code=f"X{index:03}") for index in range(50)
        ] + [original]
        draft.model_dump.return_value = payload
        with patch("app.agentic.evaluators.encode", side_effect=lambda scope, value: value):
            packet = evaluators.review_packet(None, draft)
        self.assertEqual(packet["L_counts"], {"3": 51})
        self.assertEqual(len(packet["candidate_factors"]), 1)
        self.assertEqual(len(packet["facts"]), 1)
        self.assertLessEqual(len(canonical_json(packet)), 12000)

    async def test_invalid_submission_stops_after_three_failures(self):
        scope = SimpleNamespace(snapshot_id="snapshot")
        executor = ToolExecutor(scope, None, actor="examiner")
        message = call("submit_review", {"draft_id": "wrong", "verdict": "agree", "issues": []})
        loop = SimpleNamespace(
            scope=scope,
            budget=RuntimeBudget(),
            _model=AsyncMock(return_value=(message, {})),
            event=AsyncMock(),
        )
        with (
            patch("app.agentic.evaluators.save_review"),
            patch("app.agentic.tools._audit"),
            patch("app.agentic.evaluators.encode", side_effect=lambda scope, value: value),
            patch(
                "app.agentic.examiner.review_packet",
                return_value=evaluators.compact_draft(self.draft()),
            ),
        ):
            result = await evaluators.review(loop, "examiner", executor, self.draft())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "DRAFT_MISMATCH")
        self.assertEqual(loop._model.await_count, 3)
        self.assertEqual(executor.shared.calls[("examiner", "submit_review")], 0)
        self.assertEqual(
            loop.event.await_args_list[-1].args[2],
            {
                "actor": "examiner",
                "error_code": "DRAFT_MISMATCH",
                "issues_count": 0,
                "reads": 0,
                "rejections": 3,
                "model_calls": 3,
            },
        )


class SpaceFitCacheTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = space_fixtures.SpaceFitFactsTests.asyncSetUp
    asyncTearDown = space_fixtures.SpaceFitFactsTests.asyncTearDown
    user_fact = space_fixtures.SpaceFitFactsTests.user_fact

    async def test_resume_gets_current_facts_and_same_revision_reuses_cache(self):
        from app.agentic.read_tools import get_facts

        await asyncio.to_thread(ensure_space_fits, self.scope)
        executor = ToolExecutor(self.scope, None)
        arguments = {"source": "industry_profile", "metrics": ["space_fit"], "limit": 51}
        with patch("app.agentic.tools.get_facts", wraps=get_facts) as read:
            initial = await executor.execute("get_facts", arguments)
            old_ids = {fact.fact_id for fact in FactsResult.model_validate(initial.data).facts}
            self.assertEqual(len(old_ids), 51)
            self.assertTrue((await executor.execute("get_facts", arguments)).duplicate)
            self.assertEqual(read.await_count, 1)
            await asyncio.to_thread(self.user_fact, "floor", "1층")
            await asyncio.to_thread(ensure_space_fits, self.scope)
            resumed = ToolExecutor(self.scope, None)
            resumed.shared.seen = set(executor.shared.seen)
            updated = await resumed.execute("get_facts", arguments)
            current_ids = {fact.fact_id for fact in FactsResult.model_validate(updated.data).facts}
            self.assertFalse(updated.duplicate)
            self.assertNotEqual(current_ids, old_ids)
            self.assertTrue((await resumed.execute("get_facts", arguments)).duplicate)
            self.assertEqual(read.await_count, 2)
            recovered = ToolExecutor(self.scope, None)
            recovered.shared.seen = set(resumed.shared.seen)
            reply = await recovered.execute("get_facts", arguments)
            self.assertEqual(
                {fact.fact_id for fact in FactsResult.model_validate(reply.data).facts}, current_ids
            )
            self.assertEqual(read.await_count, 3)
