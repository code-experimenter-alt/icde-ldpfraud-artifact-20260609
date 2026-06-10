#!/usr/bin/env python3
"""Parent-side driver for AWS Nitro Enclaves LDP oracle measurements."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import csv
import hashlib
import json
import os
import random
import socket
import subprocess
import sys
import time
from pathlib import Path


def leading_zero_bits(payload: bytes) -> int:
    digest = hashlib.sha256(payload).digest()
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        bits += 8 - byte.bit_length()
        break
    return bits


def solve_pow(y: int, salt: str, k: int) -> tuple[int, int]:
    start = time.perf_counter_ns()
    nonce = 0
    prefix = json.dumps({"y": y, "u": salt}, sort_keys=True).encode("utf-8")
    while True:
        payload = prefix + b":" + str(nonce).encode("ascii")
        if leading_zero_bits(payload) >= k:
            return nonce, time.perf_counter_ns() - start
        nonce += 1


def send_vsock(cid: int, port: int, req: dict[str, object]) -> tuple[dict[str, object], int]:
    if not hasattr(socket, "AF_VSOCK"):
        raise RuntimeError("AF_VSOCK is not available on this Python build")
    start = time.perf_counter_ns()
    sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    with sock:
        sock.connect((cid, port))
        sock.sendall(json.dumps(req, sort_keys=True).encode("utf-8") + b"\n")
        chunks = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
            if b"\n" in data:
                break
    elapsed = time.perf_counter_ns() - start
    raw = b"".join(chunks).split(b"\n", 1)[0]
    return json.loads(raw.decode("utf-8")), elapsed


def send_stdio(proc: subprocess.Popen[bytes], req: dict[str, object]) -> tuple[dict[str, object], int]:
    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("stdio process was not opened with pipes")
    start = time.perf_counter_ns()
    proc.stdin.write(json.dumps(req, sort_keys=True).encode("utf-8") + b"\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    elapsed = time.perf_counter_ns() - start
    return json.loads(line.decode("utf-8")), elapsed


FIELDNAMES = [
    "phase",
    "mechanism",
    "concurrency",
    "batch_size",
    "idx",
    "epsilon_h",
    "epsilon_c",
    "k",
    "counter",
    "oracle_elapsed_ns",
    "round_trip_ns",
    "pow_ns",
    "total_client_ns",
    "nonce",
    "attestation_mode",
    "attestation_document_sha256",
    "attestation_document_bytes",
    "attestation_elapsed_ns",
    "report_commitment_sha256",
]


def should_store_attestation(idx: int, retain_first: int, retain_every: int) -> bool:
    if idx < retain_first:
        return True
    return retain_every > 0 and idx % retain_every == 0


def build_request(args: argparse.Namespace, idx: int) -> dict[str, object]:
    rng = random.Random(args.seed + idx)
    return {
        "x": int(rng.random() < 0.35),
        "epsilon_h": args.epsilon_h,
        "epsilon_c": args.epsilon_c,
        "lambda": args.lam,
        "k0": args.k0,
        "workload": args.workload,
        "session": args.session,
    }


def run_one(
    args: argparse.Namespace,
    idx: int,
    proc: subprocess.Popen[bytes] | None = None,
) -> dict[str, object]:
    req = build_request(args, idx)
    start = time.perf_counter_ns()
    if args.stdio_local:
        if proc is None:
            raise RuntimeError("stdio process missing")
        response, round_trip_ns = send_stdio(proc, req)
    else:
        response, round_trip_ns = send_vsock(args.cid, args.port, req)

    if args.skip_pow or int(response["k"]) <= 0:
        nonce = -1
        pow_ns = 0
    else:
        nonce, pow_ns = solve_pow(int(response["y"]), str(response["u"]), int(response["k"]))
    total_client_ns = time.perf_counter_ns() - start

    att = response.get("attestation", {})
    att_mode = att.get("mode", "unknown") if isinstance(att, dict) else "unknown"
    att_doc_b64 = att.get("document_b64", "") if isinstance(att, dict) else ""
    att_sha256 = att.get("document_sha256", "") if isinstance(att, dict) else ""
    att_bytes = int(att.get("document_bytes", 0)) if isinstance(att, dict) else 0
    att_elapsed_ns = int(att.get("attestation_elapsed_ns", 0)) if isinstance(att, dict) else 0
    if att_doc_b64 and should_store_attestation(idx, args.attestation_retain_first, args.attestation_retain_every):
        doc_path = args.attestation_dir / f"{args.phase}_report_{idx:08d}.attestation.cose"
        doc_path.write_bytes(base64.b64decode(att_doc_b64))
        (args.attestation_dir / f"{args.phase}_report_{idx:08d}.response.json").write_text(
            json.dumps(response, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    return {
        "phase": args.phase,
        "mechanism": args.mechanism,
        "concurrency": args.workers,
        "batch_size": args.batch_size,
        "idx": idx,
        "epsilon_h": args.epsilon_h,
        "epsilon_c": args.epsilon_c,
        "k": response["k"],
        "counter": response["counter"],
        "oracle_elapsed_ns": response["oracle_elapsed_ns"],
        "round_trip_ns": round_trip_ns,
        "pow_ns": pow_ns,
        "total_client_ns": total_client_ns,
        "nonce": nonce,
        "attestation_mode": att_mode,
        "attestation_document_sha256": att_sha256,
        "attestation_document_bytes": att_bytes,
        "attestation_elapsed_ns": att_elapsed_ns,
        "report_commitment_sha256": response.get("report_commitment_sha256", ""),
    }


def write_summary(path: Path, args: argparse.Namespace, started: float, rows_written: int) -> None:
    elapsed = time.perf_counter() - started
    summary = {
        "phase": args.phase,
        "mechanism": args.mechanism,
        "reports": rows_written,
        "workers": args.workers,
        "batch_size": args.batch_size,
        "epsilon_h": args.epsilon_h,
        "epsilon_c": args.epsilon_c,
        "k0": args.k0,
        "lambda": args.lam,
        "skip_pow": args.skip_pow,
        "wall_time_sec": elapsed,
        "reports_per_sec": rows_written / max(elapsed, 1e-9),
        "csv": str(path),
    }
    path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cid", type=int, default=16)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--reports", type=int, default=1000)
    parser.add_argument("--epsilon-h", type=float, default=0.5)
    parser.add_argument("--epsilon-c", type=float, default=2.0)
    parser.add_argument("--lambda", dest="lam", type=float, default=0.1)
    parser.add_argument("--k0", type=int, default=12)
    parser.add_argument("--phase", default="pilot")
    parser.add_argument("--mechanism", default="TEE-PoW")
    parser.add_argument("--workload", default="segment_membership")
    parser.add_argument("--session", default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--skip-pow", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("nitro_measurements.csv"))
    parser.add_argument("--attestation-dir", type=Path, default=Path("attestation_docs"))
    parser.add_argument("--attestation-retain-first", type=int, default=0)
    parser.add_argument("--attestation-retain-every", type=int, default=1)
    parser.add_argument("--progress-every", type=int, default=1000)
    parser.add_argument("--stdio-local", action="store_true", help="Debug against local enclave_oracle.py over stdio.")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    if args.session is None:
        args.session = f"{args.phase}-{os.getpid()}"
    if args.stdio_local and args.workers != 1:
        raise ValueError("--stdio-local supports only --workers 1")

    rng = random.Random(args.seed)
    proc: subprocess.Popen[bytes] | None = None
    if args.stdio_local:
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("enclave_oracle.py")), "--seed", str(args.seed)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    args.workers = max(1, args.workers)
    args.attestation_dir.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    rows_written = 0
    try:
        with args.out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            writer.writeheader()
            if args.workers == 1:
                for idx in range(args.reports):
                    writer.writerow(run_one(args, idx, proc))
                    rows_written += 1
                    if args.progress_every and rows_written % args.progress_every == 0:
                        print(f"{args.phase}: wrote {rows_written}/{args.reports}", file=sys.stderr, flush=True)
            else:
                next_idx = 0
                with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
                    futures: set[concurrent.futures.Future[dict[str, object]]] = set()
                    while next_idx < min(args.reports, args.workers * 4):
                        futures.add(executor.submit(run_one, args, next_idx, None))
                        next_idx += 1
                    while futures:
                        done, futures = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
                        for fut in done:
                            writer.writerow(fut.result())
                            rows_written += 1
                            if args.progress_every and rows_written % args.progress_every == 0:
                                print(f"{args.phase}: wrote {rows_written}/{args.reports}", file=sys.stderr, flush=True)
                            if next_idx < args.reports:
                                futures.add(executor.submit(run_one, args, next_idx, None))
                                next_idx += 1
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    write_summary(args.out, args, started, rows_written)
    print(f"Wrote {rows_written} rows to {args.out}")


if __name__ == "__main__":
    main()
