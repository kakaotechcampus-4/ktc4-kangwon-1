import unittest

from backtest.metrics import bootstrap_mean, rank_metrics, summarize


def summary(rank, group="1", status="완료", store_rank=20):
    return {
        "상태": status,
        "그룹": group,
        "순위": rank,
        "업종 수": 51,
        "상위5 업종 수": 5,
        "점포 수 순위": store_rank,
        "평균 대비": 10.0,
        "배지": "조건부",
        "D 차이": 1.0,
        "C 차이": -1.0,
        "S 차이": 2.0,
        "서울 자료 없음": False,
        "현재 시점 C4": True,
        "현재 시점 G": False,
    }


class MetricTests(unittest.TestCase):
    def test_bootstrap_is_repeatable(self):
        values = [1.0, 0.0, 1.0, 0.0, 0.0]
        self.assertEqual(bootstrap_mean(values), bootstrap_mean(values))
        mean, low, high = bootstrap_mean(values)
        self.assertAlmostEqual(mean, 0.4)
        self.assertLessEqual(low, mean)
        self.assertGreaterEqual(high, mean)

    def test_rank_metrics(self):
        result = rank_metrics([1, 3, 6, 12])
        self.assertEqual(result["주소 수"], 4)
        self.assertEqual(result["상위5 비율"], 0.5)
        self.assertEqual(result["상위10 비율"], 0.75)
        self.assertEqual(result["순위 중앙값"], 4.5)

    def test_rank_metrics_on_nothing(self):
        self.assertEqual(rank_metrics([]), {"주소 수": 0})

    def test_summarize_uses_only_completed_rows(self):
        rows = [summary(1), summary(9, group="2"), summary(3, status="상권 밖"), {"상태": "오류"}]
        result = summarize(rows)
        self.assertEqual(result["상태"], {"완료": 2, "상권 밖": 1, "오류": 1})
        self.assertEqual(result["서비스"]["주소 수"], 2)
        self.assertEqual(result["점포 수 기준"]["상위5 비율"], 0.0)
        self.assertEqual(result["무작위 상위5 기대 비율"], 0.098)
        self.assertEqual(set(result["그룹별"]), {"1", "2"})
        self.assertEqual(result["항목 차이 평균"], {"D": 1.0, "C": -1.0, "S": 2.0})
        self.assertEqual(result["현재 시점 자료 대상"], 2)

    def test_summarize_without_completed_rows(self):
        result = summarize([{"상태": "오류"}])
        self.assertEqual(result["서비스"], {"주소 수": 0})


if __name__ == "__main__":
    unittest.main()
