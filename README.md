# Anonymous ICDE LDP Budget-Integrity Artifact

This repository-style artifact accompanies the anonymous ICDE submission on
budget-integrity certificates for LDP data markets. It contains the
reproducibility code, generated CSV/JSON result tables, and the retained AWS
Nitro Enclaves evidence used by the paper.

The manuscript source, LaTeX support files, and rendered paper figures are
intentionally excluded from this minimal code/results artifact.

## Contents

- `Makefile`, `requirements.txt`: reproducibility entry points and Python
  dependency list.
- `experiments/*.py`: deterministic local simulations for disclosure baselines,
  valuation, marketing workloads, PoW calibration, incentive checks, market
  utility, robustness, throughput/cost summaries, and attacker strategies.
- `experiments/results/`: CSV/JSON tables used by the manuscript and figures.
- `experiments/aws_nitro/`: AWS Nitro Enclaves prototype and runbook.
- `experiments/aws_nitro/results/icde-ldp-nitro-20260605094208/`: completed
  non-debug pilot run with 50 NSM attestation documents, response JSON files,
  raw latency rows, EIF hash, PCR/enclave metadata, diagnostics, and manifest.
- `experiments/aws_nitro/results/icde-ldp-nitro-scale-20260606040525/`: scaled
  run summaries, manifests, hashes, diagnostics, and logs. The large per-report
  raw CSVs and bulk attestation documents are intentionally omitted from this
  minimal package; the paper-facing aggregate is in
  `experiments/results/goal7_throughput_cost.csv`.

## Reproducing Local Results

Install the Python dependencies, then regenerate local tables and figures:

```bash
python3 -m pip install -r requirements.txt
make paper_tables MODE=estimate
```

For a shorter existence check:

```bash
make smoke
```

The local scripts regenerate `experiments/results/*.csv`,
`experiments/results/*.json`, `artifact_index.html`, and PDF/PNG figures under
`figures/`. The generated `figures/` directory and generated index HTML are not
stored in this minimal package.

## Nitro Evidence

The Nitro pilot evidence is retained as raw files because those values cannot be
reproduced on a non-Nitro machine. The EIF binary itself is not included; its
hash and build/measurement metadata are included. The scaled run keeps summary
JSON files and manifests instead of the very large per-report raw records, so
the package remains suitable for a minimal GitHub artifact.

See `experiments/aws_nitro/README.md` for the hardware runbook.
