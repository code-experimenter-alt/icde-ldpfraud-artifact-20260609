#!/usr/bin/env python3
"""Minimal Nitro Enclave oracle server for LDP market reports.

Inside AWS Nitro Enclaves, run with --vsock. For local debugging, omit --vsock
and send one JSON request per stdin line.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import random
import socket
import subprocess
import sys
import threading
import time
from typing import BinaryIO


COUNTER = 0


def sigma(eps: float) -> float:
    e = math.exp(eps)
    return math.sqrt(e) / max(e - 1.0, 1e-12)


def randomized_response(bit: int, eps: float, rng: random.Random) -> int:
    p = math.exp(eps) / (math.exp(eps) + 1.0)
    keep = rng.random() < p
    return bit if keep else 1 - bit


def leading_zero_bits(data: bytes) -> int:
    digest = hashlib.sha256(data).digest()
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        bits += 8 - byte.bit_length()
        break
    return bits


def difficulty(eps_h: float, eps_c: float, k0: int, lam: float) -> int:
    r = sigma(eps_h) / sigma(eps_c)
    return math.ceil(k0 + lam * max(0.0, r * r - 1.0))


def nsm_attestation(user_data: bytes) -> dict[str, object]:
    encoded = base64.b64encode(user_data).decode("ascii")
    helper = "/app/get_attestation_doc"
    if os.path.exists(helper):
        try:
            start = time.perf_counter_ns()
            proc = subprocess.run([helper, encoded], check=True, capture_output=True, timeout=5)
            document_b64 = proc.stdout.decode("ascii").strip()
            document = base64.b64decode(document_b64)
            return {
                "mode": "nsm-rust-helper",
                "document_b64": document_b64,
                "document_sha256": hashlib.sha256(document).hexdigest(),
                "document_bytes": len(document),
                "attestation_elapsed_ns": time.perf_counter_ns() - start,
            }
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
            return {
                "mode": "nsm-rust-helper-failed",
                "error": str(exc),
                "user_data_sha256": hashlib.sha256(user_data).hexdigest(),
            }
    for cmd in (
        ["nsm-cli", "attestation", "--user-data", encoded],
        ["/usr/bin/nsm-cli", "attestation", "--user-data", encoded],
    ):
        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, timeout=5)
            return {
                "mode": "nsm-cli",
                "document_b64": base64.b64encode(proc.stdout).decode("ascii"),
                "stderr": proc.stderr.decode("utf-8", errors="replace"),
            }
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    return {
        "mode": "local-no-nsm",
        "warning": "No Nitro NSM attestation command was available; do not report as real TEE evidence.",
        "user_data_sha256": hashlib.sha256(user_data).hexdigest(),
    }


def handle_request(req: dict[str, object], rng: random.Random, state_lock: threading.Lock) -> dict[str, object]:
    global COUNTER
    start = time.perf_counter_ns()
    x = int(req.get("x", 0))
    eps_c = float(req.get("epsilon_c", 1.0))
    eps_h = float(req.get("epsilon_h", os.environ.get("SEALED_EPSILON_H", "1.0")))
    k0 = int(req.get("k0", 12))
    lam = float(req.get("lambda", 1.0))
    workload = str(req.get("workload", "segment_membership"))
    session = str(req.get("session", "local"))

    k = difficulty(eps_h, eps_c, k0, lam)
    with state_lock:
        y = randomized_response(1 if x else 0, eps_h, rng)
        salt = os.urandom(16).hex()
        COUNTER += 1
        counter = COUNTER
    commitment = hashlib.sha256(json.dumps(
        {
            "y": y,
            "salt": salt,
            "k": k,
            "epsilon_c": eps_c,
            "workload": workload,
            "session": session,
            "counter": counter,
        },
        sort_keys=True,
    ).encode("utf-8")).digest()
    att = nsm_attestation(commitment)
    elapsed_ns = time.perf_counter_ns() - start
    return {
        "y": y,
        "u": salt,
        "k": k,
        "epsilon_c": eps_c,
        "workload": workload,
        "counter": counter,
        "report_commitment_sha256": commitment.hex(),
        "attestation": att,
        "oracle_elapsed_ns": elapsed_ns,
    }


def serve_stdio(rng: random.Random) -> None:
    state_lock = threading.Lock()
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle_request(json.loads(line), rng, state_lock)
        print(json.dumps(response, sort_keys=True), flush=True)


def read_json_line(conn: socket.socket) -> dict[str, object] | None:
    chunks = []
    while True:
        data = conn.recv(4096)
        if not data:
            return None
        chunks.append(data)
        if b"\n" in data:
            break
    raw = b"".join(chunks).split(b"\n", 1)[0]
    return json.loads(raw.decode("utf-8"))


def handle_vsock_connection(conn: socket.socket, rng: random.Random, state_lock: threading.Lock) -> None:
    with conn:
        req = read_json_line(conn)
        if req is None:
            return
        response = handle_request(req, rng, state_lock)
        conn.sendall(json.dumps(response, sort_keys=True).encode("utf-8") + b"\n")


def serve_vsock(port: int, rng: random.Random) -> None:
    if not hasattr(socket, "AF_VSOCK"):
        raise RuntimeError("AF_VSOCK is not available on this Python build")
    sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    sock.bind((socket.VMADDR_CID_ANY, port))
    sock.listen(128)
    state_lock = threading.Lock()
    while True:
        conn, _ = sock.accept()
        thread = threading.Thread(target=handle_vsock_connection, args=(conn, rng, state_lock), daemon=True)
        thread.start()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vsock", action="store_true")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    if args.vsock:
        serve_vsock(args.port, rng)
    else:
        serve_stdio(rng)


if __name__ == "__main__":
    main()
