# Reindex Mainnet Benchmark

Measures tracing overhead on Bitcoin Core using real mainnet blocks via
`bitcoind -reindex`. Compares five conditions processing 200,000 real
mainnet blocks to produce credible evidence for Bitcoin Core issue #35142.

## Conditions

| # | Condition | Description |
|---|-----------|-------------|
| 1 | `baseline` | No tracing (`-stdiobus=off`, no bpftrace) |
| 2 | `ebpf` | bpftrace attached to all 20 USDT probes, kernel counters only |
| 3 | `ebpf_full` | bpftrace with printf per event (data extraction via perf ring buffer) |
| 4 | `ipc` | stdio Bus shadow mode with all 6 IPC workers |
| 5 | `raw_ipc` | Raw Unix pipes with same 6 workers (no protocol library) |

Optional: `capnproto` — calibrated overhead simulating Cap'n Proto IPC.

## Quick Start

### Prerequisites

- Docker with `--privileged` support (required for eBPF kernel access)
- Mainnet block files (`blk*.dat`) covering at least 200,000 blocks
- Python 3.10+ on host (for isolated runner)

### Build the Docker Image

```bash
docker build -f contrib/perf/docker/Dockerfile.reindex_benchmark \
    -t bitcoin-reindex-benchmark .
```

### Run (Recommended: Isolated with Warmup)

Each condition runs in a separate container with a warmup pass to
eliminate page cache bias:

```bash
python3 contrib/perf/run_benchmark_isolated.py \
    --block-dir /path/to/blocks \
    --stop-height 200000 \
    --conditions baseline,ebpf,ebpf_full,ipc,raw_ipc
```

This:
1. Runs a warmup baseline (primes all cache layers, not measured)
2. Runs each condition in a separate `docker run`
3. Computes overhead% relative to baseline
4. Prints formatted table
5. Saves results to `contrib/perf/results/<timestamp>/`

### Run (Quick: Single Container)

```bash
docker run --privileged --rm \
    -v /path/to/blocks:/blocks \
    -v /sys/kernel/debug:/sys/kernel/debug \
    bitcoin-reindex-benchmark \
    --block-dir /blocks --stop-height 200000 \
    --conditions baseline,ebpf,ebpf_full,ipc,raw_ipc
```

Note: sequential execution in one container may have cache bias
(baseline pays cold-cache cost, later conditions benefit from warm cache).

### Run via GitHub Actions (EC2)

The workflow `.github/workflows/benchmark.yml` runs the benchmark on a
dedicated EC2 instance (c6i.2xlarge, 8 vCPU) with optional EBS snapshot
for pre-synced blocks:

1. Go to Actions → "Tracing Overhead Benchmark" → Run workflow
2. Set parameters (instance type, stop height, conditions, snapshot ID)
3. Results are committed to `.github/benchmark-results/<timestamp>/`

## Obtaining Mainnet Block Data

The benchmark requires real mainnet `blk*.dat` files containing at least
200,000 blocks. Sources:

1. **Synced node** — Copy `~/.bitcoin/blocks/blk0000{0..5}.dat`
   (first 6 files cover blocks 0–200,000+)

2. **Partial sync** — `bitcoind -stopatheight=200001`

3. **EBS snapshot** — For CI, create a snapshot once and reuse.

## CLI Options (in-container)

| Option | Default | Description |
|--------|---------|-------------|
| `--block-dir` | `/blocks` | Directory containing `blk*.dat` files |
| `--stop-height` | `20000` | Block height to stop at (10,000–850,000) |
| `--conditions` | all | Comma-separated conditions to run |
| `--output` | `benchmark_report.json` | Path for JSON report |
| `--no-flush-caches` | off | Skip cache flushing between conditions |
| `--verbose` | off | Enable debug logging |

## CLI Options (host isolated runner)

| Option | Default | Description |
|--------|---------|-------------|
| `--block-dir` | `/tmp/btc_blocks/mainnet/blocks` | Host path to blocks |
| `--stop-height` | `200000` | Block height |
| `--conditions` | `baseline,ebpf,ebpf_full,ipc,raw_ipc` | Conditions |
| `--image` | `bitcoin-reindex-benchmark` | Docker image name |
| `--no-warmup` | off | Skip warmup (not recommended) |
| `--no-cache-flush` | off | Skip cache flush (only used without warmup) |
| `--results-dir` | `results/<timestamp>` | Override output directory |

## Example Output

```
==============================================================================
BENCHMARK RESULTS (isolated runs, warm cache, no I/O bias)
==============================================================================

| Condition    |  Time(s) | Blocks/s |  Overhead% |     Events | Status   |
|--------------|----------|----------|------------|------------|----------|
| baseline     |   466.26 |    428.9 |          — |          0 | OK       |
| ebpf         |   493.44 |    405.3 |      5.83% |   31142458 | OK       |
| ebpf_full    |   849.71 |    235.4 |     82.24% |   31142458 | OK       |
| ipc          |   489.00 |    409.0 |      4.88% |          0 | OK       |
| raw_ipc      |   495.58 |    403.6 |      6.29% |          0 | OK       |

Block range: 0-200000
==============================================================================
```

## Measurement Method

- **Metric:** Wall-clock time from `bitcoind` process start to exit
- **Blocks/s:** `stop_height / elapsed_seconds`
- **Overhead%:** `((condition_time - baseline_time) / baseline_time) × 100`
- **Warmup:** One unmeasured baseline run primes all cache layers before measurement
- **Isolation:** Each condition runs in a separate Docker container

This is a real-system metric including all overhead: startup, I/O,
validation, tracing pipeline, shutdown.

## Architecture

```
Host (run_benchmark_isolated.py)
├── Warmup: docker run baseline (not measured, primes cache)
├── Measure: docker run baseline
├── Measure: docker run ebpf
├── Measure: docker run ebpf_full
├── Measure: docker run ipc
├── Measure: docker run raw_ipc
└── Output: results/<timestamp>/report.json + table

Each container:
┌──────────────────────────────────────────┐
│ bitcoind -reindex -stopatheight=200000   │
│   + condition-specific tracing           │
│                                          │
│ Conditions:                              │
│   baseline: -stdiobus=off                │
│   ebpf:     -stdiobus=off + bpftrace     │
│   ebpf_full: -stdiobus=off + bpftrace    │
│   ipc:      -stdiobus=shadow + 6 workers │
│   raw_ipc:  -stdiobus=raw_pipe + 6 workers│
└──────────────────────────────────────────┘
```
