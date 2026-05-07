# stdio_bus performance benchmarks

Throughput benchmarks that measure `bitcoind` overhead when forwarding
events through the stdio_bus IPC pipeline versus running with
`-stdiobus=off`.

## Scripts

### `stdio_bus_benchmark.py` — single scenario baseline vs shadow

Runs `bitcoind -regtest`, generates N blocks with `-stdiobus=off`, then
again with `-stdiobus=shadow`, and reports the blocks/s delta.

```bash
python3 contrib/perf/stdio_bus_benchmark.py --blocks 500
```

### `run_ipc_benchmark_suite.py` — original 4-scenario suite

Runs `stdio_bus_benchmark.py` for 4 IPC worker configurations
(block_benchmark, mempool_monitor, p2p_traffic, all_combined) and prints
an overhead table like:

```
SUMMARY: IPC Tracing Overhead by Scenario
==========================================================================
Scenario                    Overhead     Baseline          IPC   Pass
-----------------------------------------------------------------
block_benchmark               +4.79%      20.10b/s      19.51b/s      ✗
mempool_monitor              +11.07%      19.80b/s      17.59b/s      ✗
p2p_traffic                   +7.13%      19.54b/s      18.14b/s      ✗
all_combined                 +23.18%      21.18b/s      16.78b/s      ✗
```

### `run_ipc_benchmark_suite_full.py` — **full USDT-parity suite**

Extends the 4-scenario suite with scenarios for the remaining 12 USDT
tracepoints covered by the newer IPC workers:

| Scenario              | USDT tracepoints covered                                                       |
|-----------------------|--------------------------------------------------------------------------------|
| `block_benchmark`     | `validation:block_connected`                                                   |
| `mempool_monitor`     | `mempool:added/removed/replaced/rejected`                                      |
| `p2p_traffic`         | `net:inbound_message`, `net:outbound_message`                                  |
| `p2p_connections`     | `net:inbound_connection`, `outbound_connection`, `closed_connection`, `evicted_inbound_connection`, `misbehaving_connection` |
| `utxocache_utxos`     | `utxocache:add`, `utxocache:spent`, `utxocache:uncache` — hot path             |
| `coin_selection`      | `coin_selection:selected_coins`, `normal_create_tx_internal`, `attempting_aps_create_tx`, `aps_create_tx_internal` |
| `all_events_recorder` | All 20 events through a single CSV writer (catch-all)                          |
| `all_parity`          | All parity workers running simultaneously (worst-case back-pressure)           |

Run it:

```bash
python3 contrib/perf/run_ipc_benchmark_suite_full.py --blocks 500
```

Sample output (500 blocks on M-series macOS, representative shape only —
absolute numbers depend heavily on the host):

```
SUMMARY: IPC Tracing Overhead by Scenario (full parity)
==========================================================================
Scenario                    Overhead     Baseline          IPC   Pass
-----------------------------------------------------------------
block_benchmark               +4.79%      20.10b/s      19.51b/s      ✗
mempool_monitor              +11.07%      19.80b/s      17.59b/s      ✗
p2p_traffic                   +7.13%      19.54b/s      18.14b/s      ✗
p2p_connections               +2.40%      20.11b/s      19.63b/s      ✓
utxocache_utxos              +14.20%      19.99b/s      17.15b/s      ✗
coin_selection                +0.10%      20.04b/s      20.02b/s      ✓
all_events_recorder          +18.50%      20.10b/s      16.38b/s      ✗
all_parity                   +35.70%      20.14b/s      12.95b/s      ✗
```

The pass threshold is 2 % blocks/s overhead (same as the original suite).

## Reading the report

Each scenario column:

- **Overhead** — `(baseline_blocks_per_s − ipc_blocks_per_s) / baseline_blocks_per_s × 100 %`
- **Baseline** — blocks/s with `-stdiobus=off`
- **IPC** — blocks/s with `-stdiobus=shadow` and the worker attached
- **Pass** — `True` if overhead < 2 %

JSON results are written to `contrib/perf/results/full_parity_suite_report.json`.

## Relationship to the eBPF/IPC latency comparison

This suite measures **throughput** (blocks/s). For **per-event latency**
side-by-side with eBPF/USDT, use `contrib/tracing/compare_latency.py`
together with `contrib/tracing/ipc/all_events_recorder.py` and
`contrib/tracing/all_tracepoints_ebpf_recorder.py`. See
`contrib/tracing/ipc/README.md` for the workflow.
