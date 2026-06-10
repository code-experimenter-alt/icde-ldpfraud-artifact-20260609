FROM rust:1.92-slim AS rust-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git musl-tools pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY Cargo.toml /build/Cargo.toml
COPY src/get_attestation_doc.rs /build/src/get_attestation_doc.rs
RUN rustup target install x86_64-unknown-linux-musl \
    && cargo build --release --target=x86_64-unknown-linux-musl --bin get_attestation_doc

FROM python:3.12-slim

WORKDIR /app
COPY enclave_oracle.py /app/enclave_oracle.py
COPY --from=rust-builder /build/target/x86_64-unknown-linux-musl/release/get_attestation_doc /app/get_attestation_doc

ENTRYPOINT ["/usr/local/bin/python3", "/app/enclave_oracle.py", "--vsock", "--port", "5000"]
