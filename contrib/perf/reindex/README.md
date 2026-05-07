# Reindex Mainnet Benchmark

Measures tracing overhead on Bitcoin Core using real mainnet blocks via
`bitcoind -reindex`. Compares four conditions processing 10,000+ real
mainnet blocks to produce credible evidence for Bitcoin Core issue #35142.

## Conditions

| # | Condition | Description |
|---|-----------|-------------|
| 1 | Baseline | No tracing (`-stdiobus=off`, no bpftrace) |
| 2 | eBPF | bpftrace attached to all 20 USDT probes |
| 3 | IPC | stdio_bus shadow mode with all 6 workers |
| 4 | Cap'n Proto Sim | Calibrated overhead simulating Cap'n Proto IPC |

## Quick Start (Docker)

### Prerequisites

- Docker with `--privileged` support (required for eBPF kernel access)
- Mainnet block files (`blk*.dat`) from a synced Bitcoin Core node

### Build the Docker Image

```bash
docker build -f contrib/perf/docker/Dockerfile.reindex_benchmark \
    -t bitcoin-reindex-benchmark .
```

### Run the Benchmark

```bash
docker run --privileged --rm \
    -v /path/to/blocks:/blocks:ro \
    bitcoin-reindex-benchmark --stop-height=20000
```

### Save Results to Host

```bash
docker run --privileged --rm \
    -v /path/to/blocks:/blocks:ro \
    -v $(pwd)/results:/output \
    bitcoin-reindex-benchmark \
        --stop-height=20000 \
        --output /output/benchmark_report.json
```

### Run Specific Conditions Only

```bash
docker run --privileged --rm \
    -v /path/to/blocks:/blocks:ro \
    bitcoin-reindex-benchmark \
        --stop-height=20000 \
        --conditions baseline,ipc
```

## Obtaining Mainnet Block Data

The benchmark requires real mainnet `blk*.dat` files containing at least
10,000 blocks. These files can be obtained from:

1. **A fully-synced Bitcoin Core node** — Copy files from your node's
   `blocks/` directory (typically `~/.bitcoin/blocks/` on Linux or
   `~/Library/Application Support/Bitcoin/blocks/` on macOS).

2. **A partial sync** — Run `bitcoind` and stop it after syncing past
   the desired height. The first few `blk*.dat` files (blk00000.dat
   through blk00005.dat) contain blocks 0 through ~500,000.

3. **Peer sharing** — Block files are deterministic and can be shared
   between trusted parties. Each `blk*.dat` file is approximately 134MB.

Only the first few block files are needed. For `--stop-height=20000`,
`blk00000.dat` alone contains sufficient blocks (it holds blocks 0
through ~119,000).

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--block-dir` | `/blocks` | Directory containing `blk*.dat` files |
| `--stop-height` | `20000` | Block height to stop at (10,000–50,000) |
| `--datadir` | `/benchmark` | Base directory for per-condition datadirs |
| `--conditions` | `baseline,ebpf,ipc,capnproto` | Conditions to run |
| `--output` | `benchmark_report.json` | Path for JSON report |
| `--bitcoind` | auto-detected | Path to bitcoind binary |
| `--no-flush-caches` | off | Skip cache flushing between conditions |
| `--verbose` | off | Enable debug logging |

## Output

The benchmark produces:

1. **Human-readable table** (stdout) — Side-by-side comparison suitable
   for posting in GitHub issues.

2. **JSON report** (file) — Structured data with per-condition metrics,
   metadata, and competitive status determination.

### Example Output

```
======================================================================
BENCHMARK RESULTS
======================================================================

Condition       Time(s)  Blocks/s  Overhead%  Events   Status
-----------     -------  --------  ---------  ------   ------
baseline          45.2    442.5       —          —      OK
ebpf              46.1    433.8     2.0%      85,421   OK
ipc               46.8    427.4     3.5%      85,390   OK
capnproto_sim     47.3    422.8     4.6%      85,421   OK

Competitive: YES (IPC overhead 3.5% <= 2x eBPF overhead 4.0%)
======================================================================
```

## Architecture

```
Host                          Docker Container (--privileged)
┌─────────────────┐          ┌──────────────────────────────────┐
│ blk00000.dat    │──mount──▶│ /blocks/ (read-only)             │
│ blk00001.dat    │          │                                  │
│ ...             │          │ run_reindex_benchmark.py          │
└─────────────────┘          │   ├─ baseline: bitcoind -reindex │
                             │   ├─ ebpf: bitcoind + bpftrace   │
                             │   ├─ ipc: bitcoind + 6 workers   │
                             │   └─ capnproto: bitcoind + sim   │
                             │                                  │
                             │ Output: JSON + table report       │
                             └──────────────────────────────────┘
```

## Notes

- The `--privileged` flag is required for eBPF kernel access. Without it,
  the eBPF condition will be skipped with an error message.
- Block files are symlinked (not copied) into each condition's datadir to
  avoid excessive disk usage.
- Filesystem caches are flushed between conditions for isolation. This
  requires root access inside the container (available with `--privileged`).
- The benchmark continues with remaining conditions if one fails.
