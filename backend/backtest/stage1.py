import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from app.agents.business_lifecycle.preprocess import _aggregate_rows
from app.agents.business_lifecycle.scoring import calculate_lifecycle_scores
from backtest.data import LAST_QUARTER, api_rows, load_store_data, quarters_after, quarters_until
from backtest.outcome import MIN_STORES, StoreTable
from backtest.scores import (
    bootstrap_mean,
    concordance,
    persistence_baseline,
    popularity_baseline,
    seoul_baseline,
)

BASES = ["20234", "20241", "20242", "20243", "20244", "20251", "20252"]
BASELINES = ("seoul_average", "popularity", "persistence")


def lifecycle_scores(area_frame: pd.DataFrame, area: str, base: str) -> dict[str, float]:
    rows = api_rows(area_frame, quarters_until(base, 12))
    scored = calculate_lifecycle_scores(_aggregate_rows(rows, area, base, 12), 12)
    return {
        str(r.service_id): float(r.lifecycle_score)
        for r in scored.itertuples()
        if pd.notna(r.lifecycle_score)
    }


def evaluate(data: pd.DataFrame, bases: list[str], last: str = LAST_QUARTER) -> pd.DataFrame:
    table = StoreTable(data)
    by_area = dict(tuple(data.groupby("TRDAR_CD")))
    records = []
    for base in bases:
        future = quarters_after(base, last)
        seoul = seoul_baseline(table, base)
        for area, frame in by_area.items():
            outcomes = {
                industry: value
                for industry, stores in sorted(table.stores_at(area, base).items())
                if stores >= MIN_STORES
                and (value := table.survival(area, industry, future)) is not None
            }
            if len(outcomes) < 2:
                continue
            signals = {
                "seoul_average": seoul,
                "popularity": popularity_baseline(table, area, base),
                "persistence": persistence_baseline(table, area, base),
            }
            coverage: float | None = None
            try:
                signals["lifecycle"] = lifecycle_scores(frame, area, base)
            except Exception as error:
                records.append(
                    {
                        "base": base,
                        "area": area,
                        "signal": "lifecycle",
                        "concordance": None,
                        "industries": len(outcomes),
                        "coverage": None,
                        "error": type(error).__name__,
                    }
                )
            else:
                common = {
                    industry: value
                    for industry, value in outcomes.items()
                    if all(industry in scores for scores in signals.values())
                }
                coverage = len(common) / len(outcomes)
                if len(common) < 2:
                    records.append(
                        {
                            "base": base,
                            "area": area,
                            "signal": "lifecycle",
                            "concordance": None,
                            "industries": len(common),
                            "coverage": coverage,
                            "error": None,
                        }
                    )
                    continue
                outcomes = common
            for name, scores in signals.items():
                records.append(
                    {
                        "base": base,
                        "area": area,
                        "signal": name,
                        "concordance": concordance(scores, outcomes),
                        "industries": len(outcomes),
                        "coverage": coverage,
                        "error": None,
                    }
                )
    return pd.DataFrame(records)


def summarize(rows: pd.DataFrame) -> dict:
    valid = rows.dropna(subset=["concordance"])
    wide = valid.pivot_table(index=["base", "area"], columns="signal", values="concordance")
    per_area = wide.groupby(level="area").mean()
    summary: dict = {
        "pairs": int(len(wide)),
        "areas": int(len(per_area)),
        "signals": {},
        "lifecycle_vs": {},
    }
    for signal in per_area.columns:
        mean, low, high = bootstrap_mean(per_area[signal].dropna().tolist())
        summary["signals"][signal] = {"mean": mean, "low": low, "high": high}
    if "lifecycle" in wide.columns:
        for baseline in BASELINES:
            both = wide[["lifecycle", baseline]].dropna()
            gaps = (both["lifecycle"] - both[baseline]).groupby(level="area").mean()
            mean, low, high = bootstrap_mean(gaps.tolist())
            summary["lifecycle_vs"][baseline] = {
                "mean": mean,
                "low": low,
                "high": high,
                "wins": low > 0,
            }
    life = rows[(rows["signal"] == "lifecycle") & rows["error"].isna()]
    coverage = life["coverage"].dropna() if "coverage" in life else pd.Series(dtype=float)
    summary["coverage_mean"] = float(coverage.mean()) if len(coverage) else None
    summary["skipped"] = int(life["concordance"].isna().sum())
    summary["errors"] = rows["error"].dropna().value_counts().to_dict()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bases", nargs="*", default=BASES)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    rows = evaluate(load_store_data(args.data), args.bases)
    rows.to_csv(args.out / "stage1_concordance.csv", index=False, encoding="utf-8-sig")
    summary = summarize(rows)
    summary["created"] = date.today().isoformat()
    (args.out / "stage1_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
