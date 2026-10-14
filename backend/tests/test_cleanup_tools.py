"""외부 호출 없이 예산·도구·보고서 신뢰 경계를 회귀 검사합니다."""

import json
import sqlite3
import tempfile
import unittest
import uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agents.agentic.budget import RuntimeBudget
from app.agents.agentic.contracts import ReportProposal, ReviewResolution, ToolReply
from app.agents.agentic.report import ReportInvalid, finalize, validate_proposal
from app.agents.agentic.sql_tool import LOCAL_VIEWS, _authorizer, error, query_raw
from app.agents.agentic.tools import ToolExecutor, _audit
from app.db.connection import connect, initialize
from app.llm.budget import BudgetExceeded
from app.local_data.adapter import LocalAdapter
from app.local_data.database import LocalDataDB
from app.local_data.persistence import register_cell
from app.local_data.provenance import save_snapshot
from app.schemas import Site
from app.storage.raw import capture_scope
from app.storage.scrub import env_secrets, scrub, scrub_text
from app.text import has_digit


class BudgetBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_evaluators_reserve_small_output(self):
        budget = RuntimeBudget({"calls": [{"output_tokens": 15000}]})
        reservations = [await budget.claim_output(4000) for _ in range(4)]
        self.assertEqual(reservations, [4000] * 4)
        for reservation in reservations:
            await budget.release_output(reservation)
        self.assertEqual(budget.pending_output, 0)

    async def test_evaluators_leave_final_calls(self):
        budget = RuntimeBudget({"used": 38})
        with self.assertRaises(BudgetExceeded):
            await budget.reserve("examiner")
        self.assertEqual(await budget.reserve("decision", final=True), 39)
        self.assertEqual(await budget.reserve("decision", final=True), 40)
        with self.assertRaises(BudgetExceeded):
            await budget.reserve("decision", final=True)


class CleanupToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "requests.sqlite3"
        initialize(self.path)
        with connect(self.path) as db:
            db.execute(
                "INSERT INTO analysis_requests(request_id,input_address,status,created_at) "
                "VALUES('one','시험','running','now')"
            )
        self.manager = capture_scope("one", self.path)
        self.scope = await self.manager.__aenter__()
        self.site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)
        await self.scope.record(
            source="business_lifecycle",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [{"SIMILR_INDUTY_STOR_CO": i} for i in range(60)]},
        )

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_sql_invalid_numbers_stay_tool_errors(self):
        reply = await query_raw(self.scope, "SELECT ?", [10**100])
        self.assertEqual(reply.error.code, "SQL_DENIED")
        for value in [float("nan"), float("inf")]:
            with self.subTest(value=value):
                tool = ToolExecutor(self.scope, self.site)
                reply = await tool.execute("query_raw", {"sql": "SELECT ?", "params": [value]})
                self.assertEqual(reply.error.code, "INVALID_ARGUMENT")

    async def test_nan_arguments_are_audited(self):
        tool = ToolExecutor(self.scope, self.site)
        reply = await tool.execute("query_raw", {"sql": "SELECT ?", "params": [float("nan")]})
        self.assertEqual(reply.error.code, "INVALID_ARGUMENT")
        with connect(self.path) as db:
            arguments = json.loads(db.execute("SELECT input_json FROM tool_calls").fetchone()[0])
        self.assertEqual(arguments["params"], [None])

    async def test_submission_survives_exhausted_read_limits(self):
        submit = AsyncMock(return_value=ToolReply(status="ok", data={}))
        tool = ToolExecutor(
            self.scope, self.site, actor="examiner", handlers={"submit_review": submit}
        )
        tool.shared.calls["total"] = 40
        tool.shared.calls[("examiner", "total")] = 4
        reply = await tool.execute(
            "submit_review", {"draft_id": "draft", "verdict": "agree", "issues": []}
        )
        self.assertEqual(reply.status, "ok")
        submit.assert_awaited_once()
        self.assertEqual(tool.shared.calls["total"], 40)

    async def test_transient_error_is_not_duplicate(self):
        handler = AsyncMock(
            side_effect=[error("SQL_TIMEOUT", "시간 초과"), ToolReply(status="ok", data={})]
        )
        tool = ToolExecutor(self.scope, self.site, handlers={"query_raw": handler})
        arguments = {"sql": "SELECT 1"}
        self.assertEqual((await tool.execute("query_raw", arguments)).error.code, "SQL_TIMEOUT")
        reply = await tool.execute("query_raw", arguments)
        self.assertEqual(reply.status, "ok")
        self.assertFalse(reply.duplicate)
        self.assertEqual(handler.await_count, 2)

    async def test_uppercase_views_and_safe_functions(self):
        reply = await query_raw(
            self.scope,
            "SELECT substr(raw_json,1,3),instr(raw_json,'SIMILR') FROM V_RAW_LIFECYCLE "
            "WHERE raw_json LIKE '%SIMILR%'",
        )
        self.assertEqual(reply.status, "partial")
        self.assertEqual(len(reply.data.rows), 50)

    async def test_sql_response_is_bounded(self):
        sql = "SELECT " + "||".join(["raw_json"] * 200) + " AS large FROM v_raw_lifecycle"
        reply = await query_raw(self.scope, sql)
        self.assertEqual(reply.status, "partial")
        self.assertTrue(reply.truncated)
        self.assertLessEqual(len(reply.model_dump_json().encode()), 65536)
        self.assertLess(len(reply.data.rows), 50)

    def proposal(self, ids):
        return {
            "L_records": [
                {
                    "industry_code": "I201",
                    "review_state": "reviewed",
                    "status": "observed",
                    "grade": 3,
                    "selection": {
                        "basis": "code_lower_top10",
                        "code_score_snapshot_id": "base",
                        "code_lower_rank": 1,
                        "reason": "새 근거 확인",
                    },
                    "new_factors": [
                        {"direction": "favorable", "claim": "새 요인", "fact_ids": [ids[0]]}
                    ],
                    "checked_questions": ["새 요인이 유리한가"],
                    "tool_call_ids": ["call"],
                    "limitations": ["자료 한계"],
                }
            ]
        }

    def validate(self, proposal, facts):
        with patch("app.agents.agentic.report.fact_rows", return_value=facts):
            return validate_proposal(
                self.scope, ReportProposal.model_validate(proposal), "base", [{"code": "I201"}]
            )

    async def test_all_L_free_text_fields_reject_numbers(self):
        fact_id = "f_" + str(uuid.uuid4())
        original = self.proposal([fact_id])
        for field in ["reason", "claim", "checked_questions", "limitations"]:
            proposal = deepcopy(original)
            record = proposal["L_records"][0]
            if field == "reason":
                record["selection"][field] = "숫자 12"
            elif field == "claim":
                record["new_factors"][0][field] = "숫자 12"
            else:
                record[field] = ["숫자 12"]
            with self.subTest(field=field), self.assertRaises(ReportInvalid):
                self.validate(proposal, {})

    async def test_overlap_and_other_industry_fact_rejected(self):
        ids = ["f_" + str(uuid.uuid4()) for _ in range(2)]
        facts = {
            f: {"status": "observed", "citable": 1, "metric": "lq", "industry_code": "I201"}
            for f in ids
        }
        _audit(
            self.scope,
            "call",
            "decision",
            "get_facts",
            {},
            ToolReply(status="ok", data={}, fact_ids=ids),
        )
        proposal = self.proposal(ids)
        self.validate(proposal, facts)
        proposal["L_records"][0]["grade"] = 4
        proposal["L_records"][0]["new_factors"].append(
            {
                "direction": "favorable",
                "claim": "다른 요인",
                "fact_ids": ids,
            }
        )
        with self.assertRaisesRegex(ReportInvalid, "중복"):
            self.validate(proposal, facts)
        proposal = self.proposal(ids)
        facts[ids[0]]["industry_code"] = "I202"
        with self.assertRaisesRegex(ReportInvalid, "업종"):
            self.validate(proposal, facts)

    async def test_resolution_free_text_rejects_numbers(self):
        for field in ["reason", "applied", "not_applied"]:
            data = {"issue_id": "issue", "disposition": "accepted", "reason": "반영"}
            data[field] = "숫자 12" if field == "reason" else ["숫자 12"]
            resolution = ReviewResolution.model_validate(data)
            with self.subTest(field=field), self.assertRaises(ReportInvalid):
                finalize(self.scope, ReportProposal(), "base", [], resolutions=[resolution])

    async def test_local_cell_keeps_industry_period_and_value_validation(self):
        market = LocalDataDB(Path(self.temp.name) / "market.sqlite3")
        version_id = market.stage(
            "lifecycle",
            "20262",
            [
                {
                    "row_key": "row",
                    "area_code": "area",
                    "industry_code": "I201",
                    "payload": {"STDR_YYQU_CD": "20262", "SIMILR_INDUTY_STOR_CO": 7},
                },
                {
                    "row_key": "other",
                    "area_code": "area",
                    "industry_code": "I202",
                    "payload": {"STDR_YYQU_CD": None, "SIMILR_INDUTY_STOR_CO": 9},
                },
            ],
            "hash",
        )
        with market.connection() as db:
            version = dict(
                db.execute(
                    "SELECT * FROM data_versions WHERE version_id=?", (version_id,)
                ).fetchone()
            )
        adapter = LocalAdapter(market.path, [version])
        task = SimpleNamespace(site=self.site, radius_m=500)
        save_snapshot(self.scope, adapter, task, data={"area_selection": {"area_code": "area"}})
        with self.assertRaisesRegex(ValueError, "불일치"):
            register_cell(
                self.scope,
                "lifecycle",
                version_id,
                "row",
                "SIMILR_INDUTY_STOR_CO",
                metric="store_count",
                unit="개",
                expected_value=8,
            )
        reply = await query_raw(
            self.scope, "SELECT store_count FROM V_RAW_LIFECYCLE ORDER BY store_count"
        )
        self.assertEqual(reply.status, "ok")
        self.assertEqual(reply.data.rows[0].values["store_count"], 7)
        fact_id = reply.data.rows[0].fact_ids[0]
        with connect(self.path) as db:
            fact = db.execute(
                "SELECT industry_code,period,value_json FROM facts WHERE fact_id=?", (fact_id,)
            ).fetchone()
            lineage = db.execute(
                "SELECT row_key,column_name FROM local_fact_lineage WHERE fact_id=?", (fact_id,)
            ).fetchone()
        self.assertEqual(tuple(fact), ("I201", "20262", "7"))
        self.assertEqual(tuple(lineage), ("row", "SIMILR_INDUTY_STOR_CO"))
        with connect(self.path) as db:
            fallback = db.execute(
                "SELECT industry_code,period FROM facts WHERE fact_id=?",
                (reply.data.rows[1].fact_ids[0],),
            ).fetchone()
        self.assertEqual(tuple(fallback), ("I202", "20262"))


class ScrubTests(unittest.TestCase):
    def test_count_empty_column_only_allows_approved_views(self):
        for view in LOCAL_VIEWS:
            self.assertEqual(
                _authorizer(sqlite3.SQLITE_READ, view.upper(), "", None, None), sqlite3.SQLITE_OK
            )
        for table in ["lifecycle", "raw_rows", "sqlite_master", "facts"]:
            self.assertEqual(
                _authorizer(sqlite3.SQLITE_READ, table, "", None, None), sqlite3.SQLITE_DENY
            )

    def test_env_secret_names_and_lengths(self):
        with patch.dict(
            "os.environ",
            {
                "LLM_MAX_TOKENS": "8192",
                "OPENAI_API_KEY": "private-key",
                "X_TOKEN": "short",
                "X_SECRET": "other-secret",
            },
            clear=True,
        ):
            self.assertEqual(set(env_secrets()), {"private-key", "other-secret"})
            self.assertEqual(scrub_text("8192 private-key", env_secrets()), "8192 [REDACTED]")

    def test_auth_keys_removed_and_nonfinite_sanitized(self):
        value = scrub(
            {"key": "secret", "authKey": "secret", "crtfc_key": "secret", "rows": [float("nan")]}
        )
        self.assertEqual(value, {"rows": [None]})
        self.assertEqual(
            scrub("https://example.test/?key=secret&name=visible"),
            "https://example.test/?name=visible",
        )

    def test_unicode_numbers(self):
        self.assertTrue(has_digit("유동인구 １２"))
        self.assertTrue(has_digit("비율 ½"))
        self.assertFalse(has_digit("새 요인 해석"))
