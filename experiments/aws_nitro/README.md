# AWS Nitro Enclaves Runbook

This runbook is for the real TEE measurements required by the manuscript. It assumes an AWS account with permission to launch enclave-enabled EC2 instances.

## 1. Launch an enclave-enabled EC2 parent

Use an enclave-capable Nitro instance, for example `m6i.xlarge`, `c6i.xlarge`, or `r6i.xlarge`. Record the exact:

- Region and availability zone.
- AMI ID and OS version.
- Instance type.
- Nitro Enclaves CLI version.
- Parent vCPU and memory.
- Enclave vCPU and memory allocation.

Enable Nitro Enclaves on the instance. Attach an IAM role with the minimum permissions needed for SSM/SSH access, CloudWatch logging, and optional KMS attestation tests.

## 2. Install runtime dependencies

On the parent instance:

```bash
sudo yum install -y aws-nitro-enclaves-cli aws-nitro-enclaves-cli-devel docker || true
sudo apt-get update && sudo apt-get install -y aws-nitro-enclaves-cli docker.io || true
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker
sudo systemctl enable --now nitro-enclaves-allocator
```

Edit the allocator config to reserve the enclave vCPU and memory budget, then restart the allocator service.

## 3. Build the enclave image

From this directory:

```bash
docker build -t ldp-tee-oracle:latest .
nitro-cli build-enclave --docker-uri ldp-tee-oracle:latest --output-file ldp-tee-oracle.eif
nitro-cli pcr --eif-path ldp-tee-oracle.eif > pcr_values.txt
```

The final paper must report the PCR values used by the verifier. Do not run in debug mode for reported numbers.

## 4. Run the enclave

```bash
nitro-cli run-enclave --eif-path ldp-tee-oracle.eif --cpu-count 2 --memory 2048 --enclave-cid 16
nitro-cli describe-enclaves
```

The enclave server listens on vsock port `5000`.

## 5. Run parent-side measurements

```bash
python3 parent_host.py --cid 16 --port 5000 --reports 10000 --out nitro_measurements.csv
```

The output should include per-report oracle latency, vsock round-trip time, difficulty bits, PoW solve time, counter, and attestation size. Verifier-side attestation checks should be logged separately.

## 6. Required evidence

Collect these files for the ICDE artifact package:

- `pcr_values.txt`
- `nitro_measurements.csv`
- verifier log with accepted/rejected counters
- replay rejection test output
- parent instance metadata with instance type and AMI ID
- source hash or git commit of the enclave image build context

If AWS credentials are expired or no enclave-enabled capacity is available, do not report mock latency as TEE latency. Report the missing AWS run as an unresolved artifact gap.
