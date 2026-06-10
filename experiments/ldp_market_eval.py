#!/usr/bin/env python3
"""Local LDP market simulation for the ICDE manuscript.

This script intentionally does not simulate or report TEE overhead. AWS Nitro
Enclaves measurements must be collected with the aws_nitro runbook.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


EPSILONS = [0.2, 0.5, 1.0, 2.0, 4.0, 8.0]
NS = [10_000, 100_000, 1_000_000]
DOMAINS = [2, 32, 1024]
PROTOCOLS = ["brr", "oue", "olh"]


def sigma(protocol: str, eps: float, domain: int) -> float:
    """Return an estimator-scale proxy that decreases with epsilon."""
    e = math.exp(eps)
    denom = max(e - 1.0, 1e-12)
    if protocol == "brr":
        return math.sqrt(e) / denom
    if protocol == "oue":
        return 2.0 * math.sqrt(e) / denom
    if protocol == "olh":
        g = max(2.0, round(e + 1.0))
        return math.sqrt((g + domain / g) * e) / denom
    raise ValueError(f"unknown protocol: {protocol}")


def rmse(protocol: str, eps: float, n: int, domain: int, skew: float = 1.1) -> float:
    scale = sigma(protocol, eps, domain)
    domain_penalty = math.sqrt(max(domain - 1, 1))
    skew_penalty = 1.0 + 0.08 * (skew - 1.0)
    return scale * domain_penalty * skew_penalty / math.sqrt(n)


def value_from_rmse(err: float, base_value: float = 100.0, alpha: float = 250.0) -> float:
    return max(0.0, base_value - alpha * err)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def valuation_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for n in NS:
        for domain in DOMAINS:
            for protocol in PROTOCOLS:
                if protocol == "brr" and domain != 2:
                    continue
                if protocol in {"oue", "olh"} and domain == 2:
                    continue
                for eps in EPSILONS:
                    err = rmse(protocol, eps, n, domain)
                    rows.append(
                        {
                            "n": n,
                            "domain": domain,
                            "protocol": protocol,
                            "epsilon_h": eps,
                            "rmse": f"{err:.8f}",
                            "value": f"{value_from_rmse(err):.8f}",
                        }
                    )
    return rows


def premium_rows(values: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[tuple[int, int, str, float], float] = {}
    for row in values:
        key = (int(row["n"]), int(row["domain"]), str(row["protocol"]), float(row["epsilon_h"]))
        by_key[key] = float(row["value"])

    rows: list[dict[str, object]] = []
    for n in NS:
        for domain in DOMAINS:
            for protocol in PROTOCOLS:
                if protocol == "brr" and domain != 2:
                    continue
                if protocol in {"oue", "olh"} and domain == 2:
                    continue
                for eps_h in EPSILONS:
                    for eps_c in EPSILONS:
                        if eps_c <= eps_h:
                            continue
                        price_h = by_key[(n, domain, protocol, eps_h)]
                        price_c = by_key[(n, domain, protocol, eps_c)]
                        rows.append(
                            {
                                "n": n,
                                "domain": domain,
                                "protocol": protocol,
                                "epsilon_h": eps_h,
                                "epsilon_c": eps_c,
                                "price_h": f"{price_h:.8f}",
                                "price_c": f"{price_c:.8f}",
                                "premium": f"{max(0.0, price_c - price_h):.8f}",
                            }
                        )
    return rows


def ic_rows(premiums: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    k0 = 12
    k_cap = 32
    cost_unit = 0.000002
    hash_rates = [2**18, 2**21, 2**24]
    deadlines = [0.05, 0.2, 1.0]
    lambdas = [0.25, 0.5, 1.0, 2.0]
    deposit_multipliers = [0.0, 0.5, 1.0]

    for row in premiums:
        protocol = str(row["protocol"])
        domain = int(row["domain"])
        eps_h = float(row["epsilon_h"])
        eps_c = float(row["epsilon_c"])
        premium = float(row["premium"])
        r = sigma(protocol, eps_h, domain) / sigma(protocol, eps_c, domain)
        for lam in lambdas:
            k_uncapped = math.ceil(k0 + lam * max(0.0, r * r - 1.0))
            k = min(k_uncapped, k_cap)
            added_pow_cost = cost_unit * (2**k - 2**k0)
            for h in hash_rates:
                for tau in deadlines:
                    miss_prob = math.exp(-h * tau / max(2**k, 1))
                    deadline_penalty = miss_prob * (float(row["price_c"]))
                    for dep_mult in deposit_multipliers:
                        slash = dep_mult * premium
                        deterrence = added_pow_cost + deadline_penalty + slash
                        rows.append(
                            {
                                "n": row["n"],
                                "domain": domain,
                                "protocol": protocol,
                                "epsilon_h": eps_h,
                                "epsilon_c": eps_c,
                                "lambda": lam,
                                "k_bits": k,
                                "k_uncapped": k_uncapped,
                                "k_capped": int(k_uncapped > k),
                                "hash_rate": h,
                                "deadline_sec": tau,
                                "deposit_multiplier": dep_mult,
                                "premium": f"{premium:.8f}",
                                "added_pow_cost": f"{added_pow_cost:.8f}",
                                "deadline_penalty": f"{deadline_penalty:.8f}",
                                "slash": f"{slash:.8f}",
                                "deterrence": f"{deterrence:.8f}",
                                "ic": int(deterrence + 1e-12 >= premium),
                            }
                        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("results"))
    parser.add_argument("--seed", type=int, default=2026, help="Recorded for reproducibility metadata.")
    args = parser.parse_args()

    values = valuation_rows()
    premiums = premium_rows(values)
    ics = ic_rows(premiums)
    write_csv(args.out / "valuation_curves.csv", values)
    write_csv(args.out / "fraud_premiums.csv", premiums)
    write_csv(args.out / "ic_regions.csv", ics)

    metadata = [
        {"key": "seed", "value": args.seed},
        {"key": "note", "value": "Local analytic simulation; no TEE overhead claimed."},
    ]
    write_csv(args.out / "metadata.csv", metadata)
    print(f"Wrote {len(values)} valuation rows, {len(premiums)} premium rows, and {len(ics)} IC rows to {args.out}")


if __name__ == "__main__":
    main()
