import unittest

from app.agentic import scoring
from backtest.ranking import G_INDUSTRIES, ITEMS, count_ranks, rank_rows, score_rows, target_summary


def item(status="unknown", points=None):
    grade = 4 if status == "observed" else None
    return {"status": status, "grade": grade, "points": points, "value": None, "reason": "시험"}


def make_row(code, lower, coverage=0.8, regulation="해당 없음", c4="n.a.", points=None):
    items = {name: item() for name in ITEMS}
    items["C4"] = item(c4, 10.0 if c4 == "observed" else None)
    for name, value in (points or {}).items():
        items[name] = item("observed", value)
    return {
        "code": code,
        "name": f"업종 {code}",
        "items": items,
        "lower": lower,
        "upper": lower + 10,
        "coverage": coverage,
        "regulation": regulation,
        "badge": "보류",
    }


class RankTests(unittest.TestCase):
    def test_top_five_matches_the_service_order(self):
        rows = [make_row(f"A{i:02d}", 90 - i * 3, 0.5 + i / 100) for i in range(12)]
        ours = [r["code"] for r in rank_rows(rows)[:5]]
        service = [r["code"] for r in scoring.rank_candidates(rows)]
        self.assertEqual(ours, service)

    def test_ties_share_the_best_rank(self):
        rows = [make_row("A", 50), make_row("B", 40), make_row("C", 40), make_row("D", 30)]
        self.assertEqual([r["rank"] for r in rank_rows(rows)], [1, 2, 2, 4])

    def test_coverage_breaks_a_lower_tie(self):
        rows = [make_row("A", 40, 0.5), make_row("B", 40, 0.9)]
        self.assertEqual([r["code"] for r in rank_rows(rows)], ["B", "A"])

    def test_prohibited_goes_last(self):
        rows = [make_row("A", 90, regulation="금지"), make_row("B", 10)]
        ranked = rank_rows(rows)
        self.assertEqual([r["code"] for r in ranked], ["B", "A"])
        self.assertEqual(ranked[1]["rank"], 2)

    def test_count_ranks_share_ties_and_fill_missing(self):
        ranks = count_ranks({"a": 3, "b": 3, "c": 1}, ["a", "b", "c", "d"])
        self.assertEqual(ranks, {"a": 1, "b": 1, "c": 3, "d": 4})


class SummaryTests(unittest.TestCase):
    def test_target_summary_fields(self):
        rows = [
            make_row(
                "I207", 60, points={"D1": 10.0, "S1": 7.5}, c4="observed", regulation="조건부"
            ),
            make_row("B", 40, points={"D1": 5.0}),
            make_row("C", 20),
        ]
        ranked = rank_rows(rows)
        summary = target_summary(ranked, "I207", {"I207": 4, "B": 9})
        self.assertEqual(summary["순위"], 1)
        self.assertEqual(summary["업종 수"], 3)
        self.assertEqual(summary["상위5 업종 수"], 3)
        self.assertEqual(summary["평균 대비"], 20.0)
        self.assertEqual(summary["점포 수"], 4)
        self.assertEqual(summary["점포 수 순위"], 2)
        self.assertEqual(summary["D 차이"], 7.5)
        self.assertEqual(summary["C 차이"], 10.0)
        self.assertEqual(summary["S 차이"], 7.5)
        self.assertTrue(summary["서울 자료 없음"])
        self.assertTrue(summary["현재 시점 C4"])
        self.assertFalse(summary["현재 시점 G"])

    def test_g_flag_is_false_for_non_g_target_with_unknown_regulation(self):
        rows = [make_row("I207", 60, regulation="unknown"), make_row("B", 40)]
        summary = target_summary(rank_rows(rows), "I207", {})
        self.assertFalse(summary["현재 시점 G"])

    def test_g_flag_is_true_for_g_target(self):
        rows = [make_row("R104", 60, regulation="해당 없음"), make_row("B", 40)]
        summary = target_summary(rank_rows(rows), "R104", {})
        self.assertTrue(summary["현재 시점 G"])

    def test_g_industries_match_the_service(self):
        self.assertEqual(G_INDUSTRIES, frozenset({"I101", "I102", "R104", "I211"}))

    def test_score_rows_write_points_or_status(self):
        ranked = rank_rows([make_row("A", 50, points={"D1": 10.0})])
        rows = score_rows("SV001-1", ranked)
        self.assertEqual(rows[0]["D1"], 10.0)
        self.assertEqual(rows[0]["D2"], "unknown")
        self.assertEqual(rows[0]["C4"], "n.a.")
        self.assertEqual(rows[0]["행"], "SV001-1")


if __name__ == "__main__":
    unittest.main()
