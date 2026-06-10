#!/usr/bin/env python3
"""Run the scaled AWS Nitro phases required by Goal 2 and Goal 7."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path


def run(cmd: list[str], cwd: Path, log: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    with log.open("a", encoding="utf-8") as fh:
        fh.write("$ " + " ".join(cmd) + "\n")
        fh.flush()
        env = os.environ.copy()
        env.setdefault("HOME", "/root")
        env.setdefault("NITRO_CLI_ARTIFACTS", "/tmp/nitro-cli-artifacts")
        env.setdefault("NITRO_CLI_BLOBS", "/usr/share/nitro_enclaves/blobs")
        Path(env["NITRO_CLI_ARTIFACTS"]).mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=fh, stderr=subprocess.STDOUT)
        fh.write(f"[exit {proc.returncode}]\n")
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return proc


def capture(cmd: list[str], cwd: Path, out: Path, check: bool = False) -> None:
    env = os.environ.copy()
    env.setdefault("HOME", "/root")
    env.setdefault("NITRO_CLI_ARTIFACTS", "/tmp/nitro-cli-artifacts")
    env.setdefault("NITRO_CLI_BLOBS", "/usr/share/nitro_enclaves/blobs")
    Path(env["NITRO_CLI_ARTIFACTS"]).mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    out.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def phase_plan(profile: str) -> list[dict[str, object]]:
    base = [
        {
            "phase": "phase_correctness_10k_pow15",
            "mechanism": "TEE-PoW",
            "reports": 10_000,
            "workers": 4,
            "batch_size": 128,
            "epsilon_h": 0.5,
            "epsilon_c": 2.0,
            "k0": 12,
            "lambda": 0.1,
            "skip_pow": False,
            "retain_first": 0,
            "retain_every": 1,
        },
        {
            "phase": "phase_direct_1m_k0",
            "mechanism": "DirectAttest",
            "reports": 1_000_000,
            "workers": 8,
            "batch_size": 128,
            "epsilon_h": 2.0,
            "epsilon_c": 2.0,
            "k0": 0,
            "lambda": 0.0,
            "skip_pow": True,
            "retain_first": 16,
            "retain_every": 10000,
        },
        {
            "phase": "phase_teeonly_1m_k0",
            "mechanism": "TEEOnly",
            "reports": 1_000_000,
            "workers": 8,
            "batch_size": 128,
            "epsilon_h": 0.5,
            "epsilon_c": 2.0,
            "k0": 0,
            "lambda": 0.0,
            "skip_pow": True,
            "retain_first": 16,
            "retain_every": 10000,
        },
        {
            "phase": "phase_teepow_250k_pow15",
            "mechanism": "TEE-PoW",
            "reports": 250_000,
            "workers": 8,
            "batch_size": 128,
            "epsilon_h": 0.5,
            "epsilon_c": 2.0,
            "k0": 12,
            "lambda": 0.1,
            "skip_pow": False,
            "retain_first": 16,
            "retain_every": 10000,
        },
        {
            "phase": "phase_hybrid_500k_pow14",
            "mechanism": "Deposit+PoW",
            "reports": 500_000,
            "workers": 8,
            "batch_size": 128,
            "epsilon_h": 0.5,
            "epsilon_c": 2.0,
            "k0": 14,
            "lambda": 0.0,
            "skip_pow": False,
            "retain_first": 16,
            "retain_every": 10000,
        },
    ]
    if profile == "quick":
        for row in base:
            row["reports"] = min(int(row["reports"]), 20_000)
            row["retain_every"] = 1000
        return base
    if profile == "standard":
        return base
    if profile == "full":
        full = [dict(row) for row in base]
        for row in full:
            if row["mechanism"] in {"TEE-PoW", "Deposit+PoW"}:
                row["reports"] = int(row["reports"]) * 2
        return full
    raise ValueError(f"unknown profile: {profile}")


def build_enclave(workdir: Path, result_dir: Path, run_id: str, log: Path, cpu_count: int, memory_mib: int, cid: int) -> None:
    image = f"ldp-tee-oracle:{run_id}"
    eif = result_dir / "ldp-tee-oracle.eif"
    run(["docker", "build", "-t", image, "."], workdir, result_dir / "docker_build.log")
    run(["nitro-cli", "build-enclave", "--docker-uri", image, "--output-file", str(eif)], workdir, result_dir / "eif_build.txt")
    capture(["sha256sum", str(eif)], workdir, result_dir / "eif.sha256")
    capture(["nitro-cli", "pcr", "--eif-path", str(eif)], workdir, result_dir / "pcr_values.txt")
    run(["nitro-cli", "terminate-enclave", "--all"], workdir, log, check=False)
    run(
        [
            "nitro-cli",
            "run-enclave",
            "--eif-path",
            str(eif),
            "--cpu-count",
            str(cpu_count),
            "--memory",
            str(memory_mib),
            "--enclave-cid",
            str(cid),
        ],
        workdir,
        result_dir / "run_enclave.json",
    )
    time.sleep(3.0)
    capture(["nitro-cli", "describe-enclaves"], workdir, result_dir / "enclave_describe.json")


def run_phase(workdir: Path, result_dir: Path, cid: int, phase: dict[str, object], log: Path) -> None:
    csv_path = result_dir / f"{phase['phase']}.csv"
    cmd = [
        sys.executable,
        str(workdir / "parent_host.py"),
        "--cid",
        str(cid),
        "--port",
        "5000",
        "--reports",
        str(phase["reports"]),
        "--workers",
        str(phase["workers"]),
        "--batch-size",
        str(phase["batch_size"]),
        "--epsilon-h",
        str(phase["epsilon_h"]),
        "--epsilon-c",
        str(phase["epsilon_c"]),
        "--lambda",
        str(phase["lambda"]),
        "--k0",
        str(phase["k0"]),
        "--phase",
        str(phase["phase"]),
        "--mechanism",
        str(phase["mechanism"]),
        "--session",
        str(phase["phase"]),
        "--out",
        str(csv_path),
        "--attestation-dir",
        str(result_dir / "attestation_docs"),
        "--attestation-retain-first",
        str(phase["retain_first"]),
        "--attestation-retain-every",
        str(phase["retain_every"]),
        "--progress-every",
        "50000",
    ]
    if bool(phase["skip_pow"]):
        cmd.append("--skip-pow")
    run(cmd, workdir, log)


def collect_diagnostics(result_dir: Path) -> None:
    diag = result_dir / "parent_diagnostics_final"
    diag.mkdir(parents=True, exist_ok=True)
    commands = {
        "date_utc.txt": ["date", "-u"],
        "uname.txt": ["uname", "-a"],
        "os_release.txt": ["cat", "/etc/os-release"],
        "lscpu.txt": ["lscpu"],
        "free.txt": ["free", "-m"],
        "df.txt": ["df", "-h"],
        "docker_version.txt": ["docker", "--version"],
        "nitro_cli_version.txt": ["nitro-cli", "--version"],
        "nitro_describe.txt": ["nitro-cli", "describe-enclaves"],
        "allocator_status.txt": ["systemctl", "status", "nitro-enclaves-allocator", "--no-pager"],
    }
    for name, cmd in commands.items():
        capture(cmd, result_dir, diag / name)


def make_tarball(result_dir: Path) -> Path:
    tar_path = result_dir.parent / f"{result_dir.name}.tgz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(result_dir, arcname=result_dir.name)
    return tar_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--profile", choices=["quick", "standard", "full"], default="standard")
    parser.add_argument("--cid", type=int, default=16)
    parser.add_argument("--enclave-cpu-count", type=int, default=2)
    parser.add_argument("--enclave-memory-mib", type=int, default=2048)
    parser.add_argument("--s3-uri", default=None)
    args = parser.parse_args()

    run_id = "icde-ldp-nitro-scale-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    workdir = args.workdir.resolve()
    result_dir = (workdir / args.results_root / run_id).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    log = result_dir / "scaled_runner.log"
    started = time.time()
    phases = phase_plan(args.profile)
    manifest = {
        "run_id": run_id,
        "profile": args.profile,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "workdir": str(workdir),
        "phases": phases,
    }
    (result_dir / "scale_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    try:
        build_enclave(workdir, result_dir, run_id, log, args.enclave_cpu_count, args.enclave_memory_mib, args.cid)
        for phase in phases:
            run_phase(workdir, result_dir, args.cid, phase, log)
    finally:
        run(["nitro-cli", "terminate-enclave", "--all"], workdir, log, check=False)
        collect_diagnostics(result_dir)

    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["wall_time_sec"] = time.time() - started
    (result_dir / "scale_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    tar_path = make_tarball(result_dir)
    if args.s3_uri:
        target = args.s3_uri.rstrip("/") + f"/{tar_path.name}"
        run(["aws", "s3", "cp", str(tar_path), target], workdir, log)
        (result_dir / "s3_upload.txt").write_text(target + "\n", encoding="utf-8")
    print(json.dumps({"run_id": run_id, "result_dir": str(result_dir), "tarball": str(tar_path)}, indent=2))


if __name__ == "__main__":
    main()
