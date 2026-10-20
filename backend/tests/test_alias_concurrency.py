"""동시 별칭 생성과 평가 녹화 재생이 유한 시간 안에 끝나는지 검사합니다."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.agentic.aliases import encode
from app.agentic.contracts import SubmitDraftInput, SubmitLInput
from app.agentic.evaluators import PERSONAS
from app.agentic.recording import CallRecording, ReplayGenerate
from app.db.connection import SQLITE_BUSY_TIMEOUT_MS, connect
from app.local_data.database import LocalDataDB
from app.services.mock import call
from tests import test_simple_l_inputs as fixtures


class AliasConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SimpleLTests.asyncSetUp
    asyncTearDown = fixtures.SimpleLTests.asyncTearDown

    def profiles(self):
        with connect(self.path) as db:
            return dict(
                db.execute(
                    "SELECT industry_code,fact_id FROM facts WHERE metric='space_requirements'"
                ).fetchall()
            )

    async def test_eight_concurrent_encodes_are_idempotent(self):
        facts = list(self.profiles().values())
        replies = await asyncio.wait_for(
            asyncio.gather(
                *(asyncio.to_thread(encode, self.scope, {"fact_ids": facts}) for _ in range(8))
            ),
            10,
        )
        self.assertTrue(all(reply == replies[0] for reply in replies))
        self.assertEqual(len(set(replies[0]["fact_ids"])), len(facts))
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM fact_aliases").fetchone()[0], len(facts)
            )

    async def test_collision_limit_rolls_back_without_waiting_forever(self):
        first, second = list(self.profiles().values())[:2]
        existing = encode(self.scope, {"fact_id": first})["fact_id"]
        digest = Mock(return_value=SimpleNamespace(hexdigest=lambda: existing + "0" * 56))
        with patch("app.agentic.aliases.sha256", digest):
            with self.assertRaisesRegex(ValueError, "8회"):
                await asyncio.wait_for(
                    asyncio.to_thread(encode, self.scope, {"fact_id": second}), 5
                )
        self.assertEqual(digest.call_count, 8)
        self.assertEqual(encode(self.scope, {"fact_id": first})["fact_id"], existing)
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM fact_aliases").fetchone()[0], 1)

    async def test_all_runtime_write_connections_share_timeout(self):
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("PRAGMA busy_timeout").fetchone()[0], SQLITE_BUSY_TIMEOUT_MS
            )
        data = LocalDataDB(self.path.parent / "local.sqlite3")
        with data.connection() as db:
            self.assertEqual(
                db.execute("PRAGMA busy_timeout").fetchone()[0], SQLITE_BUSY_TIMEOUT_MS
            )

    async def test_four_review_replays_and_decision_writes_finish(self):
        profiles = self.profiles()
        proposal = {
            "candidates": [
                {"industry_code": code, "fact_ids": [fid]}
                for code, fid in list(profiles.items())[:5]
            ]
        }
        await self.loop.submit_l(SubmitLInput(finish=True))
        await self.loop.submit_draft(SubmitDraftInput(phase="draft", report=proposal))
        recording = CallRecording(self.path.parent / "models.json")
        for actor in PERSONAS:
            await recording.record(
                actor,
                [],
                call(
                    "submit_review",
                    {"draft_id": self.loop.done.report_id, "verdict": "agree", "issues": []},
                ),
                {"model": "replay", "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
                0,
            )
        await recording.record(
            "decision",
            [],
            call("submit_draft", {"phase": "final", "report": proposal, "review_resolutions": []}),
            {"model": "replay", "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
            0,
        )
        entries = json.loads(recording.path.read_text(encoding="utf-8"))
        replays = {
            actor: ReplayGenerate(entries=[entry])
            for actor, entry in ((entry["role"], entry) for entry in entries)
        }
        entered = set()
        ready = asyncio.Event()

        async def evaluator(messages, definitions, settings, receipt):
            actor = next(
                key for key, value in PERSONAS.items() if messages[0]["content"].startswith(value)
            )
            entered.add(actor)
            if len(entered) == 4:
                ready.set()
            await asyncio.wait_for(ready.wait(), 3)
            return await replays[actor](messages, definitions, settings, receipt)

        async def writer():
            for _ in range(8):
                await self.loop.save()

        self.loop.generate = replays["decision"]
        self.loop.evaluator_generate = evaluator
        outcome, _ = await asyncio.wait_for(
            asyncio.gather(self.loop.review_and_finalize(), writer()), 10
        )
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.result.review_completeness, 1)
        self.assertEqual(len(entered), 4)
        self.assertTrue(all(replay.position == 1 for replay in replays.values()))
