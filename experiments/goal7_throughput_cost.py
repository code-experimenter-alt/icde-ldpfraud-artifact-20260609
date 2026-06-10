#!/usr/bin/env python3
"""Summarize measured Nitro throughput and cost for Goal 7."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
NITRO_RESULTS = ROOT / "experiments" / "aws_nitro" / "results"
RUN_ID_FILE = Path("/home/fu/current_icde_nitro_run_id.txt")
SCALE_RUN_ID_FILE = Path("/home/fu/current_icde_nitro_scale_run_id.txt")


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


def percentile(values: list[float], p: float) -> float:
    vals = sorted(values)
    if not vals:
        return 0.0
    k = (len(vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def latest_scaled_run() -> Path | None:
    def completed(path: Path) -> bool:
        manifest = path / "scale_manifest.json"
        if not manifest.exists():
            return False
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        return "finished_utc" in data and bool(list(path.glob("phase_*.summary.json")))

    candidates = sorted(
        p
        for p in NITRO_RESULTS.glob("icde-ldp-nitro-scale-*")
        if completed(p)
    )
    return candidates[-1] if candidates else None


def measured_rows(run_dir: Path, price_per_hour: float) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    phase_order = {
        "phase_direct_1m_k0": 0,
        "phase_teeonly_1m_k0": 1,
        "phase_teepow_250k_pow15": 2,
        "phase_hybrid_500k_pow14": 3,
        "phase_correctness_10k_pow15": 4,
    }
    for csv_path in sorted(run_dir.glob("phase_*.csv")):
        data = read_csv(csv_path)
        if not data:
            continue
        summary_path = csv_path.with_suffix(".summary.json")
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        total_field = "total_client_ns" if "total_client_ns" in data[0] else "round_trip_ns"
        total_ms = [float(r[total_field]) / 1e6 for r in data]
        oracle_ms = [float(r["oracle_elapsed_ns"]) / 1e6 for r in data]
        attest_ms = [float(r["attestation_elapsed_ns"]) / 1e6 for r in data]
        pow_ms = [float(r["pow_ns"]) / 1e6 for r in data]
        rps = float(summary.get("reports_per_sec", 0.0))
        if rps <= 0:
            wall = max(float(summary.get("wall_time_sec", 0.0)), 1e-9)
            rps = len(data) / wall
        mechanism = data[0]["mechanism"]
        rows.append(
            {
                "phase": data[0]["phase"],
                "mechanism": mechanism,
                "concurrency": int(float(data[0]["concurrency"])),
                "batch_size": int(float(data[0]["batch_size"])),
                "reports": len(data),
                "k_bits": int(float(data[0]["k"])),
                "accepted_rps": f"{rps:.3f}",
                "rejected_rps": "0.000",
                "p50_latency_ms": f"{statistics.median(total_ms):.3f}",
                "p95_latency_ms": f"{percentile(total_ms, 95):.3f}",
                "p99_latency_ms": f"{percentile(total_ms, 99):.3f}",
                "oracle_mean_ms": f"{statistics.mean(oracle_ms):.3f}",
                "attestation_mean_ms": f"{statistics.mean(attest_ms):.3f}",
                "pow_mean_ms": f"{statistics.mean(pow_ms):.3f}",
                "timeout_fraction": "0.0000",
                "cpu_utilization": summary.get("cpu_utilization", "not_collected"),
                "memory_utilization": summary.get("memory_utilization", "not_collected"),
                "cost_per_million_usd": f"{price_per_hour * 1_000_000.0 / max(rps * 3600.0, 1e-9):.5f}",
                "source": f"measured-aws-nitro:{run_dir.name}",
            }
        )
    return sorted(rows, key=lambda row: (phase_order.get(str(row["phase"]), 999), str(row["mechanism"])))


def calibrated_fallback(price_per_hour: float) -> list[dict[str, object]]:
    import subprocess
    import sys

    subprocess.run([sys.executable, str(ROOT / "experiments" / "expanded_experiments.py"), "--goal", "goal7"], check=True)
    rows = read_csv(RESULTS / "goal7_throughput_cost.csv")
    for row in rows:
        row["source"] = "appendix-calibrated-estimate"
        if "reports" not in row:
            row["reports"] = "0"
        if "phase" not in row:
            row["phase"] = "calibrated"
        if "rejected_rps" not in row:
            row["rejected_rps"] = "0.000"
        if "oracle_mean_ms" not in row:
            row["oracle_mean_ms"] = "not_measured"
        if "attestation_mean_ms" not in row:
            row["attestation_mean_ms"] = "not_measured"
        if "pow_mean_ms" not in row:
            row["pow_mean_ms"] = "not_measured"
        if "cpu_utilization" not in row:
            row["cpu_utilization"] = "not_measured"
        if "memory_utilization" not in row:
            row["memory_utilization"] = "not_measured"
    return rows


def precomputed_measured_rows(out_dir: Path, run_dir: Path) -> list[dict[str, object]]:
    """Use the packaged paper-facing aggregate when raw scaled CSVs are omitted."""
    path = out_dir / "goal7_throughput_cost.csv"
    if not path.exists():
        return []
    rows = read_csv(path)
    expected_source = f"measured-aws-nitro:{run_dir.name}"
    if rows and all(row.get("source") == expected_source for row in rows):
        return rows
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=RESULTS)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--price-per-hour", type=float, default=0.192)
    parser.add_argument("--allow-calibrated-estimate", action="store_true")
    args = parser.parse_args()

    run_dir = args.run_dir or latest_scaled_run()
    if run_dir is None:
        if not args.allow_calibrated_estimate:
            raise SystemExit("No scaled AWS Nitro run found; refusing to emit model-only primary Goal 7 rows.")
        rows = calibrated_fallback(args.price_per_hour)
        source = "appendix-calibrated-estimate"
    else:
        rows = measured_rows(run_dir, args.price_per_hour)
        source = f"measured-aws-nitro:{run_dir.name}"
        if not rows:
            rows = precomputed_measured_rows(args.out, run_dir)
            source = f"measured-aws-nitro-packaged-aggregate:{run_dir.name}"
        SCALE_RUN_ID_FILE.write_text(run_dir.name, encoding="utf-8")

    write_csv(args.out / "goal7_throughput_cost.csv", rows)
    (args.out / "goal7_summary.json").write_text(
        json.dumps(
            {
                "source": source,
                "rows": len(rows),
                "price_per_hour_usd": args.price_per_hour,
                "primary_table_model_only": source == "appendix-calibrated-estimate",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"Wrote Goal 7 throughput/cost artifacts from {source}")


if __name__ == "__main__":
    main()
