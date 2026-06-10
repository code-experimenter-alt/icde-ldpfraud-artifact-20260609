# Experiments

This directory supports the ICDE-oriented LDP data-marketing evaluation.

## Local reproducibility

Run the full local paper artifact from the repository root:

```bash
make paper_tables
```

This regenerates Goal 1, Goal 2-8 CSV/JSON files, `artifact_index.html`, and all
color PDF/PNG figures under `figures/`. Use `make smoke` for the same generation
plus a small artifact-existence check.

Run only the base valuation simulation with:

```bash
python3 ldp_market_eval.py --out results --seed 2026
```

The local script does not claim TEE overhead. It produces:

- `valuation_curves.csv`: RMSE and value over `n`, domain size, protocol, and realized epsilon.
- `fraud_premiums.csv`: overpayment premium for each `(epsilon_h, epsilon_c)` pair.
- `ic_regions.csv`: whether the PoW/deposit condition deters over-claims under each market setting.

Regenerate only the paper figures from already-created CSV artifacts and the
final AWS run:

```bash
python3 make_experiment_figures.py
```

The plotting stack is installed in the user Python environment and pinned in
`../requirements.txt`. Offline wheels are saved in `../python_wheels/`.

## AWS Nitro Enclaves requirement

TEE correctness, attestation latency, enclave oracle latency, and accepted-report throughput must be measured on AWS Nitro Enclaves. Do not report local mock latency as hardware TEE evidence.

See `aws_nitro/README.md` for the AWS runbook.

The completed non-debug hardware run is stored under
`aws_nitro/results/icde-ldp-nitro-20260605094208/`. It contains 50 Nitro NSM
attestation COSE documents, response JSON files, the raw latency CSV, EIF hash,
PCR values, parent diagnostics, and a summary JSON.

The throughput and cloud-cost figures in the paper are model-backed estimates
calibrated by this Nitro pilot and are labeled as estimates in the manuscript.
