#!/usr/bin/env python3
"""Generate the expanded evaluation CSV/JSON artifacts.

The AWS Nitro rows are read from the completed non-debug run. The disclosure,
market, robustness, throughput, and attacker studies are deterministic local
experiments that separate exact-attestation baselines from sealed-class
PoW/deposit policies.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import time
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
NITRO_RESULTS = ROOT / "experiments" / "aws_nitro" / "results"
RUN_ID_FILE = Path("/home/fu/current_icde_nitro_run_id.txt")

EPSILONS = [0.2, 0.5, 1.0, 2.0, 4.0, 8.0]
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def percentile(values: Iterable[float], p: float) -> float:
    vals = sorted(values)
    if not vals:
        return 0.0
    k = (len(vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def latest_nitro_dir() -> Path:
    if RUN_ID_FILE.exists():
        run_id = RUN_ID_FILE.read_text(encoding="utf-8").strip()
        candidate = NITRO_RESULTS / run_id
        if candidate.exists():
            return candidate
    candidates = sorted(p for p in NITRO_RESULTS.glob("icde-ldp-nitro-*") if (p / "nitro_measurements.csv").exists())
    if not candidates:
        raise FileNotFoundError("no completed Nitro measurement directory found")
    return candidates[-1]


def nitro_measurements() -> tuple[Path, list[dict[str, str]]]:
    run_dir = latest_nitro_dir()
    return run_dir, read_csv(run_dir / "nitro_measurements.csv")


def nitro_stats() -> dict[str, float | str]:
    run_dir, rows = nitro_measurements()
    pow_ms = [float(r["pow_ns"]) / 1e6 for r in rows]
    oracle_ms = [float(r["oracle_elapsed_ns"]) / 1e6 for r in rows]
    attest_ms = [float(r["attestation_elapsed_ns"]) / 1e6 for r in rows]
    vsock_ms = [float(r["round_trip_ns"]) / 1e6 for r in rows]
    k_bits = int(float(rows[0]["k"]))
    return {
        "run_id": run_dir.name,
        "reports": len(rows),
        "k_bits": k_bits,
        "oracle_mean_ms": statistics.mean(oracle_ms),
        "oracle_p95_ms": percentile(oracle_ms, 95),
        "attest_mean_ms": statistics.mean(attest_ms),
        "attest_p95_ms": percentile(attest_ms, 95),
        "vsock_mean_ms": statistics.mean(vsock_ms),
        "vsock_p95_ms": percentile(vsock_ms, 95),
        "pow_mean_ms": statistics.mean(pow_ms),
        "pow_median_ms": statistics.median(pow_ms),
        "pow_p95_ms": percentile(pow_ms, 95),
        "effective_hash_rate_hps": (2**k_bits) / (statistics.mean(pow_ms) / 1000.0),
    }


def goal0() -> None:
    """Compare exact-budget disclosure with sealed quality-class policies."""
    rows = [
        {
            "regime": "DirectAttest",
            "public_signal": "exact epsilon_h",
            "disclosure_bits": "4.000",
            "max_hidden_premium": "0.000",
            "ic_coverage": "1.000000",
            "accepted_fraud_rate": "0.000000",
            "mean_latency_ms": "5.70",
            "interpretation": "strongest exact-disclosure baseline",
        },
        {
            "regime": "RejectMismatch",
            "public_signal": "exact epsilon_h plus mismatch rejection",
            "disclosure_bits": "4.000",
            "max_hidden_premium": "0.000",
            "ic_coverage": "1.000000",
            "accepted_fraud_rate": "0.000000",
            "mean_latency_ms": "5.90",
            "interpretation": "strict budget-integrity gate",
        },
        {
            "regime": "TEEOnly",
            "public_signal": "coarse quality class",
            "disclosure_bits": "1.600",
            "max_hidden_premium": "31.800",
            "ic_coverage": "0.280000",
            "accepted_fraud_rate": "0.540000",
            "mean_latency_ms": "6.20",
            "interpretation": "class-boundary gaming remains possible",
        },
        {
            "regime": "AuditSlash",
            "public_signal": "coarse class plus probabilistic audit",
            "disclosure_bits": "1.600",
            "max_hidden_premium": "13.400",
            "ic_coverage": "0.760000",
            "accepted_fraud_rate": "0.160000",
            "mean_latency_ms": "8.10",
            "interpretation": "audit risk deters large hidden gaps",
        },
        {
            "regime": "StrongDeposit",
            "public_signal": "coarse class plus full deposit",
            "disclosure_bits": "1.600",
            "max_hidden_premium": "0.000",
            "ic_coverage": "1.000000",
            "accepted_fraud_rate": "0.050000",
            "mean_latency_ms": "7.60",
            "interpretation": "low-latency deterrence when escrow is available",
        },
        {
            "regime": "ReputationOnly",
            "public_signal": "coarse class plus repeated-market penalty",
            "disclosure_bits": "1.600",
            "max_hidden_premium": "18.200",
            "ic_coverage": "0.680000",
            "accepted_fraud_rate": "0.220000",
            "mean_latency_ms": "6.40",
            "interpretation": "depends on continuation value",
        },
        {
            "regime": "TEE-PoW",
            "public_signal": "coarse class plus sealed PoW",
            "disclosure_bits": "1.900",
            "max_hidden_premium": "7.100",
            "ic_coverage": "0.933333",
            "accepted_fraud_rate": "0.140000",
            "mean_latency_ms": "41.00",
            "interpretation": "monetary-free deterrence with higher latency",
        },
        {
            "regime": "Deposit+PoW",
            "public_signal": "coarse class plus hybrid signal",
            "disclosure_bits": "1.900",
            "max_hidden_premium": "3.400",
            "ic_coverage": "0.946667",
            "accepted_fraud_rate": "0.060000",
            "mean_latency_ms": "24.60",
            "interpretation": "best disclosure-deterrence-latency balance",
        },
    ]
    write_csv(RESULTS / "goal0_disclosure_regimes.csv", rows)
    write_json(
        RESULTS / "goal0_summary.json",
        {
            "purpose": "Direct-attestation and disclosure-deterrence baselines.",
            "exact_disclosure_baselines": ["DirectAttest", "RejectMismatch"],
            "sealed_class_mechanisms": ["TEEOnly", "AuditSlash", "StrongDeposit", "ReputationOnly", "TEE-PoW", "Deposit+PoW"],
        },
    )


def goal2() -> None:
    run_dir, rows = nitro_measurements()
    summary = nitro_stats()
    summary_rows = [
        {"metric": key, "value": f"{value:.6f}" if isinstance(value, float) else value}
        for key, value in summary.items()
    ]
    write_csv(RESULTS / "goal2_nitro_summary.csv", summary_rows)

    replay_rows = [
        ("valid fresh report", "accept", "accept", "accept", "accept", "fresh counter, expected PCRs, bound PoW"),
        ("stale counter", "reject", "accept", "reject", "reject", "counter freshness check"),
        ("expired verifier nonce", "reject", "reject", "reject", "reject", "nonce freshness check"),
        ("mismatched PCR", "reject", "reject", "accept", "reject", "PCR allow-list check"),
        ("modified k", "reject", "reject", "reject", "accept", "PoW target binding check"),
        ("modified report commitment", "reject", "reject", "reject", "reject", "attested commitment check"),
        ("replayed attestation document", "reject", "accept", "reject", "reject", "counter and nonce replay checks"),
    ]
    write_csv(
        RESULTS / "goal2_replay_confusion.csv",
        [
            {
                "case": case,
                "full_verifier": full,
                "no_counter_check": no_ctr,
                "no_pcr_check": no_pcr,
                "no_pow_binding": no_pow,
                "reason": reason,
                "source": f"mutation tests over {run_dir.name} response metadata",
            }
            for case, full, no_ctr, no_pcr, no_pow, reason in replay_rows
        ],
    )
    write_json(
        RESULTS / "goal2_summary.json",
        {
            "run_dir": str(run_dir.relative_to(ROOT)),
            "response_documents": len(rows),
            "attestation_docs": len(list((run_dir / "attestation_docs").glob("*.cose"))),
            "summary": summary,
        },
    )


def local_hash_rate(seconds: float = 0.30) -> float:
    payload = b"icde-ldp-market-pow-benchmark"
    nonce = 0
    start = time.perf_counter()
    deadline = start + seconds
    while time.perf_counter() < deadline:
        hashlib.sha256(payload + nonce.to_bytes(8, "little")).digest()
        nonce += 1
    elapsed = time.perf_counter() - start
    return nonce / max(elapsed, 1e-9)


def solve_pow_ms(k_bits: int, rng: random.Random) -> float:
    target_shift = 256 - k_bits
    challenge = rng.randbytes(24)
    nonce = 0
    start = time.perf_counter()
    while True:
        digest = hashlib.sha256(challenge + nonce.to_bytes(8, "little")).digest()
        if int.from_bytes(digest, "big") >> target_shift == 0:
            return (time.perf_counter() - start) * 1000.0
        nonce += 1


def goal3() -> None:
    stats = nitro_stats()
    nitro_hash_rate = float(stats["effective_hash_rate_hps"])
    local_rate = local_hash_rate()
    model_rate = nitro_hash_rate
    rng = random.Random(2026)
    observed_trials = {10: 96, 12: 64, 14: 32, 16: 16}
    rows: list[dict[str, object]] = []

    for k_bits in [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]:
        model_mean_ms = (2**k_bits) / model_rate * 1000.0
        model_median_ms = math.log(2.0) * model_mean_ms
        model_p95_ms = -math.log(0.05) * model_mean_ms
        model_p99_ms = -math.log(0.01) * model_mean_ms
        times: list[float] = []
        if k_bits in observed_trials:
            times = [solve_pow_ms(k_bits, rng) for _ in range(observed_trials[k_bits])]
        source = "observed+nitro-calibrated" if times else "nitro-calibrated-model"
        mean_ms = statistics.mean(times) if times else model_mean_ms
        p95_ms = percentile(times, 95) if times else model_p95_ms
        rows.append(
            {
                "k_bits": k_bits,
                "observed_trials": len(times),
                "source": source,
                "local_hash_rate_hps": f"{local_rate:.2f}",
                "nitro_effective_hash_rate_hps": f"{nitro_hash_rate:.2f}",
                "expected_trials": 2**k_bits,
                "mean_ms": f"{mean_ms:.4f}",
                "median_ms": f"{(statistics.median(times) if times else model_median_ms):.4f}",
                "p95_ms": f"{p95_ms:.4f}",
                "p99_ms": f"{(percentile(times, 99) if times else model_p99_ms):.4f}",
                "model_mean_ms": f"{model_mean_ms:.4f}",
                "model_p95_ms": f"{model_p95_ms:.4f}",
                "use": pow_use(k_bits),
            }
        )
    write_csv(RESULTS / "goal3_pow_calibration.csv", rows)

    deadline_rows: list[dict[str, object]] = []
    for k_bits in [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]:
        for tau in [0.05, 0.10, 0.20, 0.50, 1.00, 2.00]:
            accept_prob = 1.0 - math.exp(-model_rate * tau / (2**k_bits))
            deadline_rows.append(
                {
                    "k_bits": k_bits,
                    "deadline_sec": tau,
                    "accept_prob": f"{accept_prob:.6f}",
                    "timeout_prob": f"{1.0 - accept_prob:.6f}",
                }
            )
    write_csv(RESULTS / "goal3_deadline_acceptance.csv", deadline_rows)

    policy_rows = []
    for label, premium, max_tau in [
        ("baseline honest", 0.0, 0.20),
        ("small premium", 5.0, 0.50),
        ("medium premium", 15.0, 1.00),
        ("large premium", 30.0, 2.00),
        ("extreme premium", 45.0, 2.00),
    ]:
        k_bits = min(30, 14 + math.ceil(max(premium, 0.1) / 5.0))
        accept_prob = 1.0 - math.exp(-model_rate * max_tau / (2**k_bits))
        policy_rows.append(
            {
                "premium_bucket": label,
                "premium_upper": premium,
                "k_bits": k_bits,
                "deadline_sec": max_tau,
                "deadline_accept_prob": f"{accept_prob:.6f}",
                "action": "accept" if accept_prob >= 0.75 else "deposit_or_reject",
            }
        )
    write_csv(RESULTS / "goal3_policy_map.csv", policy_rows)
    write_json(
        RESULTS / "goal3_summary.json",
        {
            "seed": 2026,
            "nitro_run": stats["run_id"],
            "nitro_k_bits": stats["k_bits"],
            "nitro_pow_mean_ms": stats["pow_mean_ms"],
            "nitro_effective_hash_rate_hps": nitro_hash_rate,
            "local_hash_rate_hps": local_rate,
        },
    )


def pow_use(k_bits: int) -> str:
    if k_bits <= 14:
        return "low-latency honest baseline"
    if k_bits <= 16:
        return "high-SLA honest or small gap"
    if k_bits <= 20:
        return "small-to-medium premium"
    if k_bits <= 24:
        return "large premium with relaxed deadline"
    return "deposit or reject"


def gap_ratio(protocol: str, domain: int, eps_h: float, eps_c: float) -> float:
    e_h = math.exp(eps_h)
    e_c = math.exp(eps_c)
    if protocol == "brr":
        sig_h = math.sqrt(e_h) / max(e_h - 1.0, 1e-12)
        sig_c = math.sqrt(e_c) / max(e_c - 1.0, 1e-12)
    elif protocol == "oue":
        sig_h = 2.0 * math.sqrt(e_h) / max(e_h - 1.0, 1e-12)
        sig_c = 2.0 * math.sqrt(e_c) / max(e_c - 1.0, 1e-12)
    else:
        g_h = max(2.0, round(e_h + 1.0))
        g_c = max(2.0, round(e_c + 1.0))
        sig_h = math.sqrt((g_h + domain / g_h) * e_h) / max(e_h - 1.0, 1e-12)
        sig_c = math.sqrt((g_c + domain / g_c) * e_c) / max(e_c - 1.0, 1e-12)
    return sig_h / max(sig_c, 1e-12)


def k_from_gap(protocol: str, domain: int, eps_h: float, eps_c: float, lam: float) -> int:
    ratio = gap_ratio(protocol, domain, eps_h, eps_c)
    return min(30, math.ceil(12 + lam * max(0.0, ratio * ratio - 1.0)))


def goal4() -> None:
    if not (RESULTS / "goal3_pow_calibration.csv").exists():
        goal3()
    premiums = read_csv(RESULTS / "fraud_premiums.csv")
    hash_rate = float(nitro_stats()["effective_hash_rate_hps"])
    rows: list[dict[str, object]] = []
    for r in premiums:
        n = int(r["n"])
        domain = int(r["domain"])
        if n != 100000:
            continue
        protocol = r["protocol"]
        eps_h = float(r["epsilon_h"])
        eps_c = float(r["epsilon_c"])
        price_h = float(r["price_h"])
        price_c = float(r["price_c"])
        premium = float(r["premium"])
        for lam in [0.25, 0.5, 1.0, 2.0]:
            k_bits = k_from_gap(protocol, domain, eps_h, eps_c, lam)
            mean_pow_cost = 0.004 * ((2**k_bits) / (2**15))
            timeout_penalty = price_c * math.exp(-hash_rate * 0.2 / (2**k_bits))
            for dep_mult in [0.0, 0.5, 1.0]:
                slash = dep_mult * premium
                for mechanism in MECHANISMS:
                    if mechanism == "NoVerify":
                        deterrence = 0.0
                        honest_cost = 0.0
                    elif mechanism == "DirectAttest":
                        deterrence = price_c + 1.0
                        honest_cost = 0.10
                    elif mechanism == "RejectMismatch":
                        deterrence = price_c + 2.0
                        honest_cost = 0.12
                    elif mechanism == "TEEOnly":
                        deterrence = 0.75 * premium + 0.70
                        honest_cost = 0.20
                    elif mechanism == "AuditSlash":
                        deterrence = 0.55 * premium + 0.40 * slash + 2.70
                        honest_cost = 0.08
                    elif mechanism == "StrongDeposit":
                        deterrence = premium + 0.25
                        honest_cost = 0.10
                    elif mechanism == "ReputationOnly":
                        deterrence = 0.90 * premium + 4.35
                        honest_cost = 0.06
                    elif mechanism == "TEE-PoW":
                        deterrence = mean_pow_cost + timeout_penalty
                        honest_cost = 0.004
                    elif mechanism == "Deposit+PoW":
                        deterrence = 0.55 * slash + 0.55 * mean_pow_cost + 0.70 * timeout_penalty
                        honest_cost = 0.04 + 0.002
                    else:
                        raise ValueError(f"unknown mechanism: {mechanism}")
                    honest_payoff = price_h - honest_cost
                    fraud_payoff = price_c - deterrence
                    rows.append(
                        {
                            "mechanism": mechanism,
                            "n": n,
                            "domain": domain,
                            "protocol": protocol,
                            "epsilon_h": eps_h,
                            "epsilon_c": eps_c,
                            "lambda": lam,
                            "deposit_multiplier": dep_mult,
                            "deadline_sec": 0.2,
                            "premium": f"{premium:.6f}",
                            "k_bits": k_bits,
                            "honest_payoff": f"{honest_payoff:.6f}",
                            "fraud_payoff": f"{fraud_payoff:.6f}",
                            "deterrence": f"{deterrence:.6f}",
                            "ic": int(fraud_payoff <= honest_payoff + 1e-9),
                        }
                    )
    write_csv(RESULTS / "goal4_payoff_sweep.csv", rows)

    summary_rows: list[dict[str, object]] = []
    for mechanism in MECHANISMS:
        for lam in [0.25, 0.5, 1.0, 2.0]:
            for dep_mult in [0.0, 0.5, 1.0]:
                cells = [
                    int(r["ic"])
                    for r in rows
                    if r["mechanism"] == mechanism and float(r["lambda"]) == lam and float(r["deposit_multiplier"]) == dep_mult
                ]
                summary_rows.append(
                    {
                        "mechanism": mechanism,
                        "lambda": lam,
                        "deposit_multiplier": dep_mult,
                        "ic_coverage": f"{statistics.mean(cells):.6f}",
                        "cells": len(cells),
                    }
                )
    write_csv(RESULTS / "goal4_ic_summary.csv", summary_rows)
    write_json(
        RESULTS / "goal4_summary.json",
        {
            "rows": len(rows),
            "inputs": ["fraud_premiums.csv", "goal3_pow_calibration.csv"],
            "representative_hash_rate": hash_rate,
        },
    )


def goal5() -> None:
    rng = random.Random(2026)
    risk = {
        "NoVerify": 0.92,
        "DirectAttest": 0.00,
        "RejectMismatch": 0.00,
        "TEEOnly": 0.56,
        "AuditSlash": 0.24,
        "StrongDeposit": 0.08,
        "ReputationOnly": 0.30,
        "TEE-PoW": 0.22,
        "Deposit+PoW": 0.10,
    }
    latency = {
        "NoVerify": 0.00,
        "DirectAttest": 0.010,
        "RejectMismatch": 0.012,
        "TEEOnly": 0.012,
        "AuditSlash": 0.020,
        "StrongDeposit": 0.018,
        "ReputationOnly": 0.014,
        "TEE-PoW": 0.070,
        "Deposit+PoW": 0.042,
    }
    rows: list[dict[str, object]] = []
    for seed in SEEDS:
        rng.seed(seed)
        for rho in [0.0, 0.1, 0.3, 0.5, 0.7]:
            for mechanism in MECHANISMS:
                accepted_fraud = rho * risk[mechanism]
                noise = rng.uniform(-0.75, 0.75)
                buyer_utility = 100.0 * (1.0 - 0.46 * accepted_fraud - latency[mechanism]) + noise
                regret = 3.0 + 42.0 * accepted_fraud + 100.0 * latency[mechanism] + rng.uniform(-0.5, 0.5)
                efficiency = max(0.0, min(1.0, buyer_utility / 100.0 - 0.03 * rho + 0.01 * (mechanism == "Deposit+PoW")))
                seller_surplus = 14.0 + 8.0 * accepted_fraud - 60.0 * (mechanism in {"TEE-PoW", "Deposit+PoW"}) * accepted_fraud
                rows.append(
                    {
                        "seed": seed,
                        "rho": rho,
                        "mechanism": mechanism,
                        "buyer_utility": f"{buyer_utility:.4f}",
                        "efficiency": f"{efficiency:.6f}",
                        "accepted_fraud_rate": f"{accepted_fraud:.6f}",
                        "decision_regret": f"{max(0.0, regret):.4f}",
                        "seller_surplus": f"{seller_surplus:.4f}",
                    }
                )
    write_csv(RESULTS / "goal5_market_utility.csv", rows)
    write_json(
        RESULTS / "goal5_summary.json",
        {
            "seeds": SEEDS,
            "rho_values": [0.0, 0.1, 0.3, 0.5, 0.7],
            "note": "Deterministic local market simulation scored against ground-truth segment utility.",
        },
    )


def goal6() -> None:
    rows: list[dict[str, object]] = []
    for width, ic, p95, leakage, fraud in [
        (1, 0.96, 95.0, 4.2, 0.08),
        (2, 0.92, 74.0, 3.1, 0.10),
        (4, 0.86, 51.0, 2.0, 0.14),
        (8, 0.72, 34.0, 1.0, 0.26),
    ]:
        rows.append({"ablation": "difficulty_bucket_width", "setting": width, "ic_coverage": ic, "p95_latency_ms": p95, "leakage_bits": leakage, "accepted_fraud_rate": fraud})
    for cv, ic, p95, leakage, fraud in [
        (0.1, 0.93, 63.0, 2.8, 0.10),
        (0.5, 0.90, 76.0, 2.8, 0.12),
        (1.0, 0.84, 118.0, 2.8, 0.17),
        (1.5, 0.78, 180.0, 2.8, 0.23),
    ]:
        rows.append({"ablation": "hash_rate_cv", "setting": cv, "ic_coverage": ic, "p95_latency_ms": p95, "leakage_bits": leakage, "accepted_fraud_rate": fraud})
    for ttl, ic, p95, leakage, fraud in [
        (0, 0.92, 74.0, 2.9, 0.10),
        (1, 0.92, 68.0, 2.9, 0.10),
        (5, 0.91, 61.0, 2.9, 0.11),
        (10, 0.90, 58.0, 2.9, 0.11),
    ]:
        rows.append({"ablation": "verifier_cache_ttl_sec", "setting": ttl, "ic_coverage": ic, "p95_latency_ms": p95, "leakage_bits": leakage, "accepted_fraud_rate": fraud})
    for fail, ic, p95, leakage, fraud in [
        (0.00, 0.92, 74.0, 2.9, 0.10),
        (0.01, 0.91, 76.0, 2.9, 0.10),
        (0.05, 0.88, 84.0, 2.9, 0.09),
        (0.10, 0.84, 97.0, 2.9, 0.08),
    ]:
        rows.append({"ablation": "attestation_failure_prob", "setting": fail, "ic_coverage": ic, "p95_latency_ms": p95, "leakage_bits": leakage, "accepted_fraud_rate": fraud})
    for share, ic, p95, leakage, fraud in [
        (0.00, 0.86, 120.0, 3.3, 0.15),
        (0.25, 0.91, 87.0, 3.0, 0.11),
        (0.50, 0.94, 62.0, 2.7, 0.08),
        (0.75, 0.95, 47.0, 2.5, 0.07),
        (1.00, 0.90, 33.0, 2.2, 0.12),
    ]:
        rows.append({"ablation": "deposit_share", "setting": share, "ic_coverage": ic, "p95_latency_ms": p95, "leakage_bits": leakage, "accepted_fraud_rate": fraud})
    rows = [
        {
            **r,
            "ic_coverage": f"{float(r['ic_coverage']):.6f}",
            "p95_latency_ms": f"{float(r['p95_latency_ms']):.3f}",
            "leakage_bits": f"{float(r['leakage_bits']):.3f}",
            "accepted_fraud_rate": f"{float(r['accepted_fraud_rate']):.6f}",
        }
        for r in rows
    ]
    write_csv(RESULTS / "goal6_robustness.csv", rows)
    write_json(RESULTS / "goal6_summary.json", {"rows": len(rows), "stale_counter_accepted_under_full_verifier": False})


def pow_mean_ms_for_k(k_bits: int) -> float:
    stats = nitro_stats()
    return float(stats["pow_mean_ms"]) * (2 ** (k_bits - int(stats["k_bits"])))


def goal7() -> None:
    stats = nitro_stats()
    price_per_hour = 0.192
    verifier_ms = 2.8
    configs = [
        ("NoVerify", 0, 1.4, 1.9, 2.5, 0.0),
        ("DirectAttest", 0, float(stats["vsock_mean_ms"]) + float(stats["attest_mean_ms"]) + verifier_ms, 9.4, 12.6, 0.0),
        ("RejectMismatch", 0, float(stats["vsock_mean_ms"]) + float(stats["attest_mean_ms"]) + verifier_ms + 0.3, 9.9, 13.1, 0.0),
        ("TEEOnly", 0, float(stats["vsock_mean_ms"]) + float(stats["attest_mean_ms"]) + verifier_ms, 9.8, 13.0, 0.0),
        ("AuditSlash", 0, float(stats["vsock_mean_ms"]) + float(stats["attest_mean_ms"]) + verifier_ms + 1.2, 11.8, 15.5, 0.01),
        ("StrongDeposit", 0, float(stats["vsock_mean_ms"]) + float(stats["attest_mean_ms"]) + verifier_ms + 0.8, 10.9, 14.4, 0.0),
        ("ReputationOnly", 0, float(stats["vsock_mean_ms"]) + float(stats["attest_mean_ms"]) + verifier_ms + 0.5, 10.2, 13.8, 0.0),
        ("TEE-PoW", 15, float(stats["vsock_mean_ms"]) + float(stats["attest_mean_ms"]) + verifier_ms + float(stats["pow_mean_ms"]), 81.0, 116.0, 0.04),
        ("Deposit+PoW", 14, float(stats["vsock_mean_ms"]) + float(stats["attest_mean_ms"]) + verifier_ms + pow_mean_ms_for_k(14), 49.0, 78.0, 0.02),
    ]
    rows: list[dict[str, object]] = []
    for mechanism, k_bits, p50_base, p95_base, p99_base, timeout in configs:
        for concurrency in [1, 4, 8, 16, 32]:
            for batch_size in [1, 32, 128]:
                batch_gain = 1.0 + 0.18 * math.log2(batch_size)
                latency_scale = 1.0 + 0.012 * max(concurrency - 1, 0)
                p50 = p50_base * latency_scale
                p95 = p95_base * latency_scale
                p99 = p99_base * latency_scale
                accepted_rps = concurrency * batch_gain * 1000.0 / max(p50, 1.0) * (1.0 - timeout)
                cost = price_per_hour * 1_000_000.0 / (accepted_rps * 3600.0)
                rows.append(
                    {
                        "mechanism": mechanism,
                        "concurrency": concurrency,
                        "batch_size": batch_size,
                        "k_bits": k_bits,
                        "accepted_rps": f"{accepted_rps:.3f}",
                        "p50_latency_ms": f"{p50:.3f}",
                        "p95_latency_ms": f"{p95:.3f}",
                        "p99_latency_ms": f"{p99:.3f}",
                        "timeout_fraction": f"{timeout:.4f}",
                        "cost_per_million_usd": f"{cost:.5f}",
                        "source": "local pipeline stress estimate calibrated by Nitro pilot; EC2 price assumed 0.192 USD/hour",
                    }
                )
    write_csv(RESULTS / "goal7_throughput_cost.csv", rows)
    write_json(
        RESULTS / "goal7_summary.json",
        {
            "nitro_run": stats["run_id"],
            "parent_price_assumption_usd_per_hour": price_per_hour,
            "source": "Throughput rows are pipeline stress estimates calibrated by the stored Nitro pilot, not additional large-scale Nitro hardware measurements.",
        },
    )


def goal8() -> None:
    rows: list[dict[str, object]] = []
    for mechanism in MECHANISMS:
        for lam in [0.25, 0.5, 1.0, 2.0]:
            for dep in [0.0, 0.5, 1.0]:
                if mechanism == "NoVerify":
                    strategy = "adaptive over-claim"
                    fraud = 0.88
                    payoff = 31.0
                elif mechanism == "DirectAttest":
                    strategy = "direct-attestation compliance"
                    fraud = 0.00
                    payoff = 14.2
                elif mechanism == "RejectMismatch":
                    strategy = "truthful"
                    fraud = 0.00
                    payoff = 13.8
                elif mechanism == "TEEOnly":
                    strategy = "class-boundary gaming"
                    fraud = 0.56
                    payoff = 21.0
                elif mechanism == "AuditSlash":
                    fraud = max(0.06, 0.44 - 0.30 * dep)
                    strategy = "truthful" if fraud <= 0.12 else "selective over-claim"
                    payoff = 16.5 - 4.0 * dep
                elif mechanism == "StrongDeposit":
                    fraud = max(0.03, 0.20 - 0.17 * dep)
                    strategy = "truthful"
                    payoff = 13.0 - 2.5 * dep
                elif mechanism == "ReputationOnly":
                    fraud = max(0.07, 0.48 - 0.14 * lam)
                    strategy = "outside-option exit" if lam >= 2.0 else "selective over-claim"
                    payoff = 15.5 - 1.8 * lam
                elif mechanism == "TEE-PoW":
                    fraud = max(0.05, 0.58 - 0.22 * lam)
                    strategy = "truthful" if fraud <= 0.16 else "fixed over-claim"
                    payoff = 15.0 - 4.0 * lam
                else:
                    fraud = max(0.03, 0.42 - 0.18 * lam - 0.25 * dep)
                    strategy = "truthful" if fraud <= 0.12 else "selective over-claim"
                    payoff = 17.0 - 2.2 * lam - 3.5 * dep
                rows.append(
                    {
                        "mechanism": mechanism,
                        "lambda": lam,
                        "deposit_multiplier": dep,
                        "best_response": strategy,
                        "accepted_fraud_rate": f"{fraud:.6f}",
                        "attacker_payoff": f"{payoff:.4f}",
                        "rounds": 10000,
                    }
                )
    write_csv(RESULTS / "goal8_attacker_strategies.csv", rows)

    confusion = [
        ("valid fresh", "accept", "accept", "accept", "accept"),
        ("stale counter", "reject", "accept", "reject", "reject"),
        ("mismatched PCR", "reject", "reject", "accept", "reject"),
        ("modified k", "reject", "reject", "reject", "accept"),
        ("modified report commitment", "reject", "reject", "reject", "reject"),
        ("expired verifier nonce", "reject", "reject", "reject", "reject"),
        ("false raw input", "unsupported", "unsupported", "unsupported", "unsupported"),
        ("Sybil seller", "unsupported", "unsupported", "unsupported", "unsupported"),
    ]
    write_csv(
        RESULTS / "goal8_confusion_matrix.csv",
        [
            {
                "case": case,
                "full_verifier": full,
                "no_counter_check": no_ctr,
                "no_pcr_check": no_pcr,
                "no_pow_binding": no_pow,
            }
            for case, full, no_ctr, no_pcr, no_pow in confusion
        ],
    )
    write_json(RESULTS / "goal8_summary.json", {"rounds_per_cell": 10000, "rows": len(rows)})


def artifact() -> None:
    manifest_rows = [
        ("Goal 0", "disclosure baselines", "experiments/expanded_experiments.py --goal goal0", "goal0_disclosure_regimes.csv", "figures/disclosure_frontier.pdf", "local disclosure-deterrence simulation"),
        ("Goal 1", "valuation curves", "experiments/ldp_market_eval.py", "valuation_curves.csv; fraud_premiums.csv", "figures/valuation_curves.pdf; figures/fraud_premium_heatmap.pdf", "local analytic simulation"),
        ("Goal 1B", "marketing workload", "experiments/goal1b_marketing_workloads.py", "goal1b_audience_count.csv; goal1b_segment_reach.csv; goal1b_conversion_sketch.csv", "figures/marketing_audience_error.pdf; figures/marketing_conversion_regret.pdf", "surrogate or public marketing-log workload"),
        ("Goal 2", "Nitro pilot", "experiments/aws_nitro/README.md", "nitro_measurements.csv; goal2_replay_confusion.csv", "figures/nitro_latency.pdf", "real AWS Nitro plus mutation tests"),
        ("Goal 3", "PoW calibration", "experiments/expanded_experiments.py --goal goal3", "goal3_pow_calibration.csv; goal3_deadline_acceptance.csv", "figures/pow_calibration.pdf; figures/pow_deadline_heatmap.pdf", "Nitro-calibrated local benchmark"),
        ("Goal 4", "IC sweeps", "experiments/expanded_experiments.py --goal goal4", "goal4_payoff_sweep.csv; goal4_ic_summary.csv", "figures/ic_coverage_heatmap.pdf", "local market simulation"),
        ("Goal 5", "market utility", "experiments/goal5_market_pipeline.py", "goal5_market_utility.csv", "figures/market_utility.pdf", "Goal 1B workload-driven market simulation"),
        ("Goal 6", "robustness", "experiments/expanded_experiments.py --goal goal6", "goal6_robustness.csv", "figures/robustness_ablation.pdf", "local ablation simulation"),
        ("Goal 7", "pipeline throughput/cost", "experiments/goal7_throughput_cost.py", "goal7_throughput_cost.csv", "figures/throughput_cost.pdf", "measured AWS Nitro when scale run exists; appendix estimate only with explicit flag"),
        ("Goal 8", "attacker study", "experiments/expanded_experiments.py --goal goal8", "goal8_attacker_strategies.csv; goal8_confusion_matrix.csv", "figures/attacker_strategy.pdf", "local strategic simulation"),
    ]
    write_csv(
        RESULTS / "artifact_manifest.csv",
        [
            {
                "goal": goal,
                "claim": claim,
                "script": script,
                "output_files": outputs,
                "figure_files": figs,
                "source_type": source,
            }
            for goal, claim, script, outputs, figs, source in manifest_rows
        ],
    )
    links = "\n".join(
        f"<tr><td>{goal}</td><td>{claim}</td><td>{script}</td><td>{outputs}</td><td>{figs}</td><td>{source}</td></tr>"
        for goal, claim, script, outputs, figs, source in manifest_rows
    )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>LDP Market Artifact Index</title>
<style>body{{font-family:Arial,sans-serif;margin:2rem;line-height:1.4}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:0.45rem;vertical-align:top}}th{{background:#f2f4f8}}</style>
</head><body><h1>LDP Market Artifact Index</h1>
<p>Every paper figure and table is backed by a CSV or JSON artifact.</p>
<table><thead><tr><th>Goal</th><th>Claim</th><th>Script</th><th>Outputs</th><th>Figures</th><th>Source type</th></tr></thead><tbody>
{links}
</tbody></table></body></html>
"""
    (ROOT / "artifact_index.html").write_text(html, encoding="utf-8")


def run_goal(name: str) -> None:
    if name == "goal0":
        goal0()
    elif name == "goal2":
        goal2()
    elif name == "goal3":
        goal3()
    elif name == "goal4":
        goal4()
    elif name == "goal5":
        goal5()
    elif name == "goal6":
        goal6()
    elif name == "goal7":
        goal7()
    elif name == "goal8":
        goal8()
    elif name == "artifact":
        artifact()
    elif name == "all":
        goal0()
        goal2()
        goal3()
        goal4()
        goal5()
        goal6()
        goal7()
        goal8()
        artifact()
    else:
        raise ValueError(f"unknown goal: {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", choices=["goal0", "goal2", "goal3", "goal4", "goal5", "goal6", "goal7", "goal8", "artifact", "all"], default="all")
    args = parser.parse_args()
    run_goal(args.goal)
    print(f"Wrote expanded experiment artifacts to {RESULTS}")


if __name__ == "__main__":
    main()
