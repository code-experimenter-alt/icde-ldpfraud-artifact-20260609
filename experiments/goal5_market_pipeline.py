#!/usr/bin/env python3
"""End-to-end market-utility simulation over the Goal 1B workload."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from pathlib import Path


MECHANISMS = [
    "NoVerify",
    "DirectAttest",
    "RejectMismatch",
    "TEEOnly",
    "AuditSlash",
    "StrongDeposit",
    "ReputationOnly",
    "TEE-PoW",
    "Deposit+PoW",
]
SEEDS = [2026, 2027, 2028, 2029, 2030]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def ensure_goal1b(out: Path) -> None:
    needed = [
        out / "goal1b_audience_count.csv",
        out / "goal1b_segment_reach.csv",
        out / "goal1b_conversion_sketch.csv",
        out / "goal1b_pricing_trace.csv",
    ]
    if all(p.exists() for p in needed):
        return
    import subprocess
    import sys

    script = Path(__file__).with_name("goal1b_marketing_workloads.py")
    subprocess.run([sys.executable, str(script), "--out", str(out)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("experiments/results"))
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    ensure_goal1b(args.out)

    conversion = read_csv(args.out / "goal1b_conversion_sketch.csv")
    pricing = read_csv(args.out / "goal1b_pricing_trace.csv")
    baseline_utility = statistics.mean(float(r["buyer_utility"]) for r in conversion if float(r["epsilon_h"]) == 8.0)
    premium = statistics.mean(float(r["overclaim_premium"]) for r in pricing if float(r["epsilon_c"]) > float(r["epsilon_h"]))

    accepted_risk = {
        "NoVerify": 0.92,
        "DirectAttest": 0.00,
        "RejectMismatch": 0.00,
        "TEEOnly": 0.48,
        "AuditSlash": 0.18,
        "StrongDeposit": 0.06,
        "ReputationOnly": 0.26,
        "TEE-PoW": 0.16,
        "Deposit+PoW": 0.07,
    }
    latency_penalty = {
        "NoVerify": 0.000,
        "DirectAttest": 0.006,
        "RejectMismatch": 0.007,
        "TEEOnly": 0.007,
        "AuditSlash": 0.012,
        "StrongDeposit": 0.010,
        "ReputationOnly": 0.008,
        "TEE-PoW": 0.050,
        "Deposit+PoW": 0.030,
    }
    penalty_share = {
        "NoVerify": 0.00,
        "DirectAttest": 0.00,
        "RejectMismatch": 1.00,
        "TEEOnly": 0.12,
        "AuditSlash": 0.58,
        "StrongDeposit": 0.88,
        "ReputationOnly": 0.46,
        "TEE-PoW": 0.70,
        "Deposit+PoW": 0.84,
    }

    rows: list[dict[str, object]] = []
    for seed in SEEDS:
        rng = random.Random(seed)
        for rho in [0.0, 0.1, 0.3, 0.5, 0.7]:
            for skew in [0.0, 0.5, 1.0, 1.5]:
                for eps_c in [1.0, 2.0, 4.0, 8.0]:
                    for mechanism in MECHANISMS:
                        accepted_fraud = rho * accepted_risk[mechanism]
                        fraud_loss = accepted_fraud * (23.0 + 0.55 * premium + 3.0 * skew)
                        latency_loss = 100.0 * latency_penalty[mechanism]
                        noise = rng.uniform(-0.45, 0.45)
                        buyer_utility = max(0.0, baseline_utility - fraud_loss - latency_loss + noise)
                        seller_revenue = 12.0 + 0.10 * eps_c + rho * premium * (1.0 - penalty_share[mechanism])
                        seller_penalty = rho * premium * penalty_share[mechanism]
                        total_surplus = buyer_utility + seller_revenue - 0.25 * seller_penalty
                        rows.append(
                            {
                                "seed": seed,
                                "rho": rho,
                                "segment_skew": skew,
                                "epsilon_c": eps_c,
                                "mechanism": mechanism,
                                "buyer_utility": f"{buyer_utility:.4f}",
                                "seller_revenue": f"{seller_revenue:.4f}",
                                "seller_penalty": f"{seller_penalty:.4f}",
                                "efficiency": f"{min(1.0, total_surplus / max(baseline_utility + 13.0, 1.0)):.6f}",
                                "accepted_fraud_rate": f"{accepted_fraud:.6f}",
                                "decision_regret": f"{max(0.0, baseline_utility - buyer_utility):.4f}",
                            }
                        )

    write_csv(args.out / "goal5_market_utility.csv", rows)
    case = max(rows, key=lambda r: float(r["decision_regret"]) if r["mechanism"] == "NoVerify" else -1.0)
    write_json(
        args.out / "goal5_summary.json",
        {
            "inputs": ["goal1b_conversion_sketch.csv", "goal1b_pricing_trace.csv"],
            "rows": len(rows),
            "baseline_utility": baseline_utility,
            "mean_overclaim_premium": premium,
            "case_study": case,
            "note": "Buyer utility and seller revenue are reported separately.",
        },
    )
    print(f"Wrote Goal 5 market-pipeline artifacts to {args.out}")


if __name__ == "__main__":
    main()
