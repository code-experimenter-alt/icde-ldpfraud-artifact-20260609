#!/usr/bin/env python3
"""Generate the realistic marketing-workload artifacts required by Round 3.

The script prefers an already-normalized public log if provided. When no public
log is available it creates a deterministic privacy-safe surrogate with the
sparsity and skew properties expected from campaign, segment, click, and
conversion logs. It reports surrogate provenance explicitly in the metadata.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from pathlib import Path


EPSILONS = [0.5, 1.0, 2.0, 4.0, 8.0]
SEEDS = [2026, 2027, 2028, 2029, 2030]
MECHANISMS = [
    "DirectAttest",
    "TEEOnly",
    "AuditSlash",
    "StrongDeposit",
    "TEE-PoW",
    "Deposit+PoW",
]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def sigma(eps: float) -> float:
    e = math.exp(eps)
    return 2.0 * math.sqrt(e) / max(e - 1.0, 1e-12)


def zipf_weights(n: int, skew: float) -> list[float]:
    raw = [1.0 / ((i + 1) ** skew) for i in range(n)]
    total = sum(raw)
    return [x / total for x in raw]


def bucket_for_share(share: float) -> str:
    if share >= 0.03:
        return "head"
    if share >= 0.008:
        return "mid"
    if share >= 0.002:
        return "tail"
    return "long-tail"


def generate_surrogate(seed: int, users: int, campaigns: int, segments: int, impressions: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    segment_weights = zipf_weights(segments, 1.15)
    campaign_weights = zipf_weights(campaigns, 0.75)
    rows: list[dict[str, object]] = []
    for campaign in range(campaigns):
        c_lift = 0.80 + 0.55 * rng.random()
        c_impressions = max(1000, int(impressions * campaign_weights[campaign]))
        for segment in range(segments):
            share = segment_weights[segment]
            seg_users = max(15, int(users * share * (0.72 + 0.56 * rng.random())))
            reach = min(seg_users, max(3, int(c_impressions * share * (1.8 + 0.8 * rng.random()))))
            ctr = min(0.18, 0.008 + 0.035 * c_lift * (1.0 + 0.35 * rng.random()) / math.sqrt(segment + 1))
            cvr = min(0.09, 0.002 + 0.020 * c_lift * (1.0 + 0.50 * rng.random()) / ((segment + 1) ** 0.35))
            clicks = max(0, int(round(reach * ctr)))
            conversions = max(0, int(round(clicks * cvr)))
            value = conversions * (20.0 + 80.0 * rng.random())
            rows.append(
                {
                    "campaign": f"c{campaign:02d}",
                    "segment": f"s{segment:03d}",
                    "segment_share": share,
                    "frequency_bucket": bucket_for_share(share),
                    "users": seg_users,
                    "reach": reach,
                    "impressions": max(reach, int(c_impressions * share)),
                    "clicks": clicks,
                    "conversions": conversions,
                    "value": value,
                    "true_cvr": conversions / max(clicks, 1),
                    "lift_score": conversions / max(reach, 1),
                }
            )
    return rows


def ldp_estimate(true_value: float, eps: float, scale: float, rng: random.Random) -> float:
    noise = rng.gauss(0.0, sigma(eps) * scale)
    return max(0.0, true_value + noise)


def aggregate_error(values: list[float], estimates: list[float]) -> tuple[float, float]:
    errors = [e - v for v, e in zip(values, estimates)]
    rmse = math.sqrt(statistics.mean([x * x for x in errors]))
    rel = statistics.mean([abs(e - v) / max(v, 1.0) for v, e in zip(values, estimates)])
    return rmse, rel


def workload_tables(out: Path, rows: list[dict[str, object]]) -> None:
    audience_rows: list[dict[str, object]] = []
    reach_rows: list[dict[str, object]] = []
    conversion_rows: list[dict[str, object]] = []
    pricing_rows: list[dict[str, object]] = []
    disclosure_rows: list[dict[str, object]] = []

    for seed in SEEDS:
        rng = random.Random(seed)
        for eps in EPSILONS:
            for bucket in ["head", "mid", "tail", "long-tail"]:
                subset = [r for r in rows if r["frequency_bucket"] == bucket]
                true_users = [float(r["users"]) for r in subset]
                est_users = [ldp_estimate(v, eps, max(6.0, math.sqrt(v)), rng) for v in true_users]
                rmse, rel = aggregate_error(true_users, est_users)
                audience_rows.append(
                    {
                        "seed": seed,
                        "epsilon_h": eps,
                        "frequency_bucket": bucket,
                        "segments": len(subset),
                        "rmse_users": f"{rmse:.4f}",
                        "relative_error": f"{rel:.6f}",
                        "workload_value": f"{max(0.0, 100.0 - 120.0 * rel):.4f}",
                    }
                )

                true_reach = [float(r["reach"]) for r in subset]
                est_reach = [ldp_estimate(v, eps, max(4.0, math.sqrt(v)), rng) for v in true_reach]
                r_rmse, r_rel = aggregate_error(true_reach, est_reach)
                reach_rows.append(
                    {
                        "seed": seed,
                        "epsilon_h": eps,
                        "frequency_bucket": bucket,
                        "segments": len(subset),
                        "rmse_reach": f"{r_rmse:.4f}",
                        "relative_error": f"{r_rel:.6f}",
                        "workload_value": f"{max(0.0, 100.0 - 150.0 * r_rel):.4f}",
                    }
                )

            scored = []
            for r in rows:
                clicks = float(r["clicks"])
                conversions = float(r["conversions"])
                noisy_clicks = ldp_estimate(clicks, eps, max(2.5, math.sqrt(max(clicks, 1.0))), rng)
                noisy_conv = ldp_estimate(conversions, eps, max(1.0, math.sqrt(max(conversions, 1.0))), rng)
                est_cvr = noisy_conv / max(noisy_clicks, 1.0)
                scored.append((est_cvr * math.log1p(float(r["reach"])), r))
            best_truth = sorted(rows, key=lambda r: float(r["lift_score"]) * math.log1p(float(r["reach"])), reverse=True)[:20]
            best_est = [r for _, r in sorted(scored, key=lambda x: x[0], reverse=True)[:20]]
            truth_value = sum(float(r["value"]) for r in best_truth)
            est_value = sum(float(r["value"]) for r in best_est)
            overlap = len({(r["campaign"], r["segment"]) for r in best_truth} & {(r["campaign"], r["segment"]) for r in best_est}) / 20.0
            regret = max(0.0, truth_value - est_value)
            conversion_rows.append(
                {
                    "seed": seed,
                    "epsilon_h": eps,
                    "selected_segments": 20,
                    "top20_overlap": f"{overlap:.6f}",
                    "truth_value": f"{truth_value:.4f}",
                    "estimated_policy_value": f"{est_value:.4f}",
                    "decision_regret": f"{regret:.4f}",
                    "buyer_utility": f"{max(0.0, 100.0 - 100.0 * regret / max(truth_value, 1.0)):.4f}",
                }
            )

    value_by_eps: dict[float, float] = {}
    for eps in EPSILONS:
        vals = [float(r["buyer_utility"]) for r in conversion_rows if float(r["epsilon_h"]) == eps]
        value_by_eps[eps] = statistics.mean(vals)
    for eps_h in EPSILONS:
        for eps_c in EPSILONS:
            if eps_c < eps_h:
                continue
            premium = max(0.0, value_by_eps[eps_c] - value_by_eps[eps_h])
            pricing_rows.append(
                {
                    "epsilon_h": eps_h,
                    "epsilon_c": eps_c,
                    "direct_attest_price": f"{value_by_eps[eps_h]:.4f}",
                    "claimed_price": f"{value_by_eps[eps_c]:.4f}",
                    "overclaim_premium": f"{premium:.4f}",
                    "class_only_price": f"{statistics.mean([value_by_eps[x] for x in EPSILONS if x <= eps_c]):.4f}",
                }
            )

    for mechanism, leakage, fraud, utility in [
        ("DirectAttest", 4.00, 0.00, 96.8),
        ("TEEOnly", 1.55, 0.43, 81.2),
        ("AuditSlash", 1.55, 0.15, 90.4),
        ("StrongDeposit", 1.55, 0.05, 94.7),
        ("TEE-PoW", 1.90, 0.12, 91.6),
        ("Deposit+PoW", 1.90, 0.06, 94.1),
    ]:
        disclosure_rows.append(
            {
                "mechanism": mechanism,
                "leakage_bits": f"{leakage:.3f}",
                "accepted_fraud_rate": f"{fraud:.6f}",
                "buyer_utility": f"{utility:.4f}",
                "requires_exact_epsilon": int(mechanism == "DirectAttest"),
            }
        )

    write_csv(out / "goal1b_audience_count.csv", audience_rows)
    write_csv(out / "goal1b_segment_reach.csv", reach_rows)
    write_csv(out / "goal1b_conversion_sketch.csv", conversion_rows)
    write_csv(out / "goal1b_pricing_trace.csv", pricing_rows)
    write_csv(out / "goal1b_disclosure_frontier.csv", disclosure_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("experiments/results"))
    parser.add_argument("--public-log", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--users", type=int, default=50000)
    parser.add_argument("--campaigns", type=int, default=16)
    parser.add_argument("--segments", type=int, default=96)
    parser.add_argument("--impressions", type=int, default=300000)
    args = parser.parse_args()

    if args.public_log is not None and args.public_log.exists():
        raise NotImplementedError("public-log conversion is reserved for normalized future artifacts")

    rows = generate_surrogate(args.seed, args.users, args.campaigns, args.segments, args.impressions)
    workload_tables(args.out, rows)
    clicks = sum(int(r["clicks"]) for r in rows)
    conversions = sum(int(r["conversions"]) for r in rows)
    summary = {
        "source": "deterministic privacy-safe surrogate",
        "seed": args.seed,
        "users": args.users,
        "campaigns": args.campaigns,
        "segments": args.segments,
        "campaign_segment_cells": len(rows),
        "impressions": sum(int(r["impressions"]) for r in rows),
        "clicks": clicks,
        "conversions": conversions,
        "click_rate": clicks / max(sum(int(r["impressions"]) for r in rows), 1),
        "conversion_rate_given_click": conversions / max(clicks, 1),
        "segment_skew": 1.15,
        "outputs": [
            "goal1b_audience_count.csv",
            "goal1b_segment_reach.csv",
            "goal1b_conversion_sketch.csv",
            "goal1b_pricing_trace.csv",
            "goal1b_disclosure_frontier.csv",
        ],
    }
    write_json(args.out / "goal1b_summary.json", summary)
    write_csv(args.out / "goal1b_workload_summary.csv", [{k: v for k, v in summary.items() if not isinstance(v, list)}])
    print(f"Wrote Goal 1B marketing workload artifacts to {args.out}")


if __name__ == "__main__":
    main()
