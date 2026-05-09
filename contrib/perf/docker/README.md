# IPC vs eBPF Tracing Benchmark

Comparative benchmark measuring tracing overhead on Bitcoin Core during `-reindex` with real mainnet blocks. Runs inside a Docker container for reproducibility.

## Requirements

- Docker with `--privileged` support (needed for eBPF/bpftrace)
- ~11GB disk for mainnet blocks (heights 0–200,000)
- ~2GB disk for Docker image build

## Step 1: Build the Docker image

```bash
docker build --no-cache -f contrib/perf/docker/Dockerfile.reindex_benchmark \
    -t bitcoin-reindex-benchmark .
```

## Step 2: Get mainnet blocks

If you already have a synced Bitcoin Core node, use its `blocks/` directory directly. Otherwise sync to the desired height using the Docker image:

```bash
mkdir -p /tmp/btc_blocks
docker run --rm -v /tmp/btc_blocks:/data \
    --entrypoint bash bitcoin-reindex-benchmark \
    -c "mkdir -p /data && /bitcoin/build/bin/bitcoind -datadir=/data -stopatheight=200001 -printtoconsole=0"
```

Block files will be at `/tmp/btc_blocks/blocks/`.

## Step 3: Run the benchmark

```bash
docker run --privileged --rm \
    -v /tmp/btc_blocks/blocks:/blocks \
    bitcoin-reindex-benchmark \
    --block-dir /blocks --stop-height 200000
```

This runs `bitcoind -reindex -stopatheight=N` under four conditions sequentially, with cache flushes between each:

1. **Baseline** — no tracing, USDT probes inactive
2. **eBPF** — bpftrace attached to all 20 USDT probes
3. **IPC** — stdio_bus shadow mode with 6 worker processes
4. **Cap'n Proto sim** — calibrated overhead simulation

## What it measures

The workload is `bitcoind -reindex -stopatheight=N` which replays ConnectBlock for every block in the local blk*.dat files. This fires validation and UTXO cache tracepoints at realistic rates with real transaction data.

## How it works

- The Docker image builds bitcoind with USDT tracing enabled and stdiobus-cpp via FetchContent
- Block files are mounted from the host at `/blocks`
- Each condition gets a fresh datadir with symlinked block files
- Page cache is flushed between conditions for fair measurement
- Results are printed as a comparison table and saved as JSON
