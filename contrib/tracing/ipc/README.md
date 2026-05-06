# IPC-based Tracing Workers

These scripts are IPC equivalents of the eBPF/USDT tracing scripts in `contrib/tracing/`.
They receive events via stdin (NDJSON) through stdio_bus IPC instead of kernel tracepoints.

## Advantages over eBPF/USDT
- No root privileges required
- No BCC/bpftrace dependency
- Cross-platform (Linux, macOS, Windows)
- Testable in CI without VM
- Typed interface (JSON, extensible to Cap'n Proto)

## Scripts

| IPC Worker | eBPF Equivalent | Events Used |
|---|---|---|
| `mempool_monitor.py` | `../mempool_monitor.py` | mempool:added, removed, replaced, rejected |
| `connectblock_benchmark.py` | `../connectblock_benchmark.bt` | validation:block_connected |
| `p2p_traffic.py` | `../log_p2p_traffic.bt` + `../p2p_monitor.py` | net:inbound_message, outbound_message |
| `utxocache_flush.py` | `../log_utxocache_flush.py` | utxocache:flush |

## Usage

These are stdio_bus workers — they read NDJSON from stdin:

```bash
# Standalone test (pipe events manually):
echo '{"method":"block.validated","params":{"height":100,"received_us":1000,"validated_us":2000,"accepted":true,"tx_count":5}}' | python3 connectblock_benchmark.py

# Via stdio_bus (automatic — configured in stdiobus_trace.json):
bitcoind -regtest -stdiobus=shadow
```
