import json
import tempfile
import unittest
from pathlib import Path

from app.agentic.questions import save_confirmed_space
from app.agentic.scoring import WEIGHTS, result, summarize
from app.agentic.snapshot import persist_report, persist_space_requirements
from app.agentic.space import ensure_space_fits
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.industries.catalog import INDUSTRIES
from app.schemas import Site
from app.storage.raw import capture_scope


class ConfirmedSpaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "db.sqlite3"
        initialize(self.path)
        create_request("loop", "시험", db_path=self.path)
        self.manager = capture_scope("loop", self.path)
        self.scope = await self.manager.__aenter__()
        self.site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)
        rows = [
            summarize(code, {key: result(key) for key in WEIGHTS}, "해당 없음")
            for code in INDUSTRIES
        ]
        persist_report(self.scope, {"rows": rows, "top5": rows[:5]}, {}, [])

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    def message(self, name, args):
        from openai.types.chat import ChatCompletionMessage

        return ChatCompletionMessage(
            role="assistant",
            tool_calls=[
                {
                    "id": "m1",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                }
            ],
        )

    def space_fit(self, code):
        current = ensure_space_fits(self.scope)
        with connect(self.path) as db:
            row = db.execute("SELECT value_json FROM facts WHERE fact_id=?", (current[code],))
            return json.loads(row.fetchone()[0])

    async def test_confirmed_values_fill_space_fit(self):
        persist_space_requirements(self.scope)
        saved = save_confirmed_space(self.scope, {"floor": "1층", "exclusive_area": "85㎡"})
        value = self.space_fit("G202")
        self.assertEqual((value["floor"], value["area"]), ("일치", "일치"))
        self.assertEqual(saved["values"], {"floor": "1층", "exclusive_area": "85㎡"})
        self.assertEqual(set(saved["fact_ids"]), {"floor", "exclusive_area"})
        with connect(self.path) as db:
            facts = db.execute(
                "SELECT metric,value_json,unit FROM facts WHERE source='user' ORDER BY metric"
            ).fetchall()
            raw = db.execute("SELECT count(*) FROM raw_responses WHERE source='user'").fetchone()
        self.assertEqual(
            [(m, json.loads(v), u) for m, v, u in facts],
            [("exclusive_area", "85㎡", "확인 화면 확정값"), ("floor", "1층", "확인 화면 확정값")],
        )
        self.assertEqual(raw[0], 1)

    async def test_without_values_space_fit_stays_unknown(self):
        persist_space_requirements(self.scope)
        value = self.space_fit("G202")
        self.assertEqual((value["floor"], value["area"]), ("미확인", "미확인"))

    async def test_loop_first_message_carries_confirmed_values(self):
        from app.agentic.aliases import decode
        from app.agentic.runtime import DecisionLoop

        saved = save_confirmed_space(self.scope, {"floor": "4층"})
        seen = []

        async def generate(messages, *args):
            seen.append(json.loads(json.dumps(messages)))
            return self.message("submit_draft", {"phase": "draft", "report": {}})

        loop = await DecisionLoop.create(
            self.scope, self.site, generate=generate, confirmed_space=saved
        )
        reply = await loop.tools.execute("submit_l", {"finish": True})
        self.assertEqual(reply.status, "ok", reply.error)
        await loop.run()
        body = json.loads(seen[0][1]["content"])
        self.assertEqual(body["confirmed_space"]["values"], {"floor": "4층"})
        self.assertRegex(body["confirmed_space"]["fact_ids"]["floor"], r"^[0-9a-f]{8}$")
        self.assertEqual(
            decode(self.scope, body["confirmed_space"])["fact_ids"]["floor"],
            saved["fact_ids"]["floor"],
        )
        self.assertEqual(loop.state["known_fact_ids"], [saved["fact_ids"]["floor"]])

    async def test_loop_without_values_keeps_first_message(self):
        from app.agentic.runtime import DecisionLoop

        loop = await DecisionLoop.create(self.scope, self.site)
        body = json.loads(loop.state["messages"][1]["content"])
        self.assertNotIn("confirmed_space", body)
        self.assertEqual(loop.state["known_fact_ids"], [])

    async def test_later_answer_overrides_confirmed_floor(self):
        from app.agentic.runtime import DecisionLoop

        saved = save_confirmed_space(self.scope, {"floor": "1층"})

        async def generate(*args):
            return self.message(
                "ask_user",
                {"questions": [{"field": "floor", "question": "층?", "reason": "조건"}]},
            )

        loop = await DecisionLoop.create(
            self.scope, self.site, generate=generate, confirmed_space=saved
        )
        self.assertEqual(self.space_fit("G202")["floor"], "일치")
        waiting = await loop.run()
        self.assertEqual(waiting.status, "waiting_for_input")
        await DecisionLoop.resume(self.scope, self.site, {"floor": "2층"}, generate=generate)
        self.assertEqual(self.space_fit("G202")["floor"], "불일치")

    def space_fit_fact(self, code):
        current = ensure_space_fits(self.scope)
        with connect(self.path) as db:
            row = db.execute(
                "SELECT value_json FROM facts WHERE fact_id=?", (current[code],)
            ).fetchone()
            parents = db.execute(
                "SELECT parent_fact_id FROM fact_parents WHERE fact_id=?", (current[code],)
            ).fetchall()
        return json.loads(row[0]), [parent[0] for parent in parents]

    async def test_unreadable_later_floor_does_not_override_confirmed(self):
        persist_space_requirements(self.scope)
        first = save_confirmed_space(self.scope, {"floor": "1층"})
        save_confirmed_space(self.scope, {"floor": "3층 정도"})
        value, parents = self.space_fit_fact("G202")
        self.assertEqual(value["floor"], "일치")
        self.assertIn(first["fact_ids"]["floor"], parents)

    async def test_unreadable_later_area_does_not_override_confirmed(self):
        persist_space_requirements(self.scope)
        save_confirmed_space(self.scope, {"exclusive_area": "85㎡"})
        save_confirmed_space(self.scope, {"exclusive_area": "모르겠습니다."})
        self.assertEqual(self.space_fit("G202")["area"], "일치")

    async def test_unreadable_answer_in_question_flow_keeps_confirmed_floor(self):
        from app.agentic.runtime import DecisionLoop

        saved = save_confirmed_space(self.scope, {"floor": "1층"})

        async def generate(*args):
            return self.message(
                "ask_user",
                {"questions": [{"field": "floor", "question": "층?", "reason": "조건"}]},
            )

        loop = await DecisionLoop.create(
            self.scope, self.site, generate=generate, confirmed_space=saved
        )
        waiting = await loop.run()
        self.assertEqual(waiting.status, "waiting_for_input")
        await DecisionLoop.resume(self.scope, self.site, {"floor": "3층 정도"}, generate=generate)
        self.assertEqual(self.space_fit("G202")["floor"], "일치")

    async def test_only_unreadable_floor_stays_unknown(self):
        persist_space_requirements(self.scope)
        save_confirmed_space(self.scope, {"floor": "3층 정도"})
        self.assertEqual(self.space_fit("G202")["floor"], "미확인")

    async def test_service_registers_values_before_loop(self):
        from app.services.analysis import execute_agentic_analysis

        async def resolve(address):
            return self.site

        first = []

        async def generate(messages, definitions, *args):
            if not first:
                first.append(json.loads(messages[1]["content"]))
            if "submit_l" in [d["function"]["name"] for d in definitions]:
                return self.message("submit_l", {"finish": True})
            phase = "final" if "reviews" in messages[-1].get("content", "") else "draft"
            return self.message("submit_draft", {"phase": phase, "report": {}})

        async def evaluator(messages, *args):
            draft_id = json.loads(messages[1]["content"])["draft_id"]
            return self.message(
                "submit_review", {"draft_id": draft_id, "verdict": "agree", "issues": []}
            )

        outcome = await execute_agentic_analysis(
            "시험",
            db_path=self.path,
            request_id="confirmed",
            resolve=resolve,
            mock=True,
            generate=generate,
            evaluator_generate=evaluator,
            confirmed_space={"floor": "1층", "exclusive_area": "85㎡"},
        )
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            first[0]["confirmed_space"]["values"], {"floor": "1층", "exclusive_area": "85㎡"}
        )
        with connect(self.path) as db:
            count = db.execute(
                "SELECT count(*) FROM facts WHERE request_id='confirmed' AND source='user' "
                "AND unit='확인 화면 확정값'"
            ).fetchone()[0]
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
