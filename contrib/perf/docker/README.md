# IPC vs eBPF Tracing Benchmark

Comparative benchmark measuring tracing overhead on Bitcoin Core during `-reindex` with real mainnet blocks. Each condition runs in a separate Docker container to eliminate page cache bias.

## Requirements

- Docker with `--privileged` support (needed for eBPF/bpftrace)
- Mainnet block files synced to at least height 200,000 (~8GB)
- ~2GB disk for Docker image build

## Step 1: Get mainnet blocks

If you already have a synced Bitcoin Core node, use its `blocks/` directory directly. Otherwise sync the first 200k blocks:

```bash
mkdir -p /tmp/btc_blocks
docker build -f contrib/perf/docker/Dockerfile.ebpf_vs_ipc -t bitcoin-ebpf-bench .
docker run --rm -v /tmp/btc_blocks:/data --entrypoint /bitcoin/build/bin/bitcoind \
  bitcoin-ebpf-bench -datadir=/data/mainnet -stopatheight=200001 -printtoconsole=0
```

Block files will be at `/tmp/btc_blocks/mainnet/blocks/`.

## Step 2: Build the Docker image

```bash
docker build --no-cache -f contrib/perf/docker/Dockerfile.ebpf_vs_ipc -t bitcoin-ebpf-bench .
```

## Step 3: Run the benchmark

```bash
./contrib/perf/run_benchmark.sh /tmp/btc_blocks/mainnet/blocks 200000
```

This runs three separate Docker containers sequentially — one per condition — so each starts with a cold page cache:

1. **Baseline** — `bitcoind -reindex` with no tracing
2. **eBPF** — `bitcoind -reindex` with bpftrace attached to all 20 USDT probes
3. **IPC** — `bitcoind -reindex` with stdio_bus shadow mode and 6 worker processes

## What it measures

The workload is `bitcoind -reindex -stopatheight=N` which replays ConnectBlock for every block in the local blk*.dat files. This fires validation and UTXO cache tracepoints at realistic rates with real transaction data.

## How it works

- The Docker image builds bitcoind with USDT tracing enabled and stdiobus-cpp pulled via CMake FetchContent from https://github.com/stdiobus/stdiobus-cpp
- `run_benchmark.sh` launches each condition in a fresh container — no shared state, no warm cache from previous runs
- Results are printed per-condition as elapsed time and blocks/s
