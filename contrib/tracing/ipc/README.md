# IPC-based Tracing Workers

Parallel stdio_bus IPC consumers for **every** Bitcoin Core USDT tracepoint.
These are functional equivalents of the `contrib/tracing/*.py` / `*.bt` scripts
but receive events over a `stdin` NDJSON stream published by the in-process
`StdioBusSdkHooks` instead of kernel eBPF/USDT.

Why two paths?
--------------
Operators see measurably different per-event latency between the eBPF/USDT
pipeline and the stdio_bus IPC pipeline on different hosts. To reason about it
we collect *both* streams during the same workload and join them by a stable
event identifier.

Coverage (1:1 with every USDT tracepoint in Bitcoin Core)
---------------------------------------------------------

| Tracepoint                               | IPC worker                                   |
|------------------------------------------|----------------------------------------------|
| `net:inbound_message`                    | `p2p_traffic.py`                             |
| `net:outbound_message`                   | `p2p_traffic.py`                             |
| `net:inbound_connection`                 | `p2p_connections.py`                         |
| `net:outbound_connection`                | `p2p_connections.py`                         |
| `net:closed_connection`                  | `p2p_connections.py`                         |
| `net:evicted_inbound_connection`         | `p2p_connections.py`                         |
| `net:misbehaving_connection`             | `p2p_connections.py`                         |
| `mempool:added`                          | `mempool_monitor.py`                         |
| `mempool:removed`                        | `mempool_monitor.py`                         |
| `mempool:replaced`                       | `mempool_monitor.py`                         |
| `mempool:rejected`                       | `mempool_monitor.py`                         |
| `validation:block_connected`             | `connectblock_benchmark.py`                  |
| `utxocache:add`                          | `utxocache_utxos.py`                         |
| `utxocache:spent`                        | `utxocache_utxos.py`                         |
| `utxocache:uncache`                      | `utxocache_utxos.py`                         |
| `utxocache:flush`                        | `utxocache_flush.py`                         |
| `coin_selection:selected_coins`          | `coin_selection.py`                          |
| `coin_selection:normal_create_tx_*`      | `coin_selection.py`                          |
| `coin_selection:attempting_aps_create_tx`| `coin_selection.py`                          |
| `coin_selection:aps_create_tx_internal`  | `coin_selection.py`                          |
| **all of the above**                     | `all_events_recorder.py` (catch-all CSV)     |

Advantages over eBPF/USDT
-------------------------
- No root privileges required
- No BCC/bpftrace dependency
- Cross-platform (Linux, macOS, Windows)
- Testable in CI without VM
- Typed interface (JSON, extensible to Cap'n Proto)

Event format
------------
Each line on `stdin` is a JSON-RPC envelope produced by
`StdioBusSdkHooks::SerializeEvent()`:

```json
{"jsonrpc":"2.0","method":"stdio_bus.event","params":{"type":"mempool_added","txid":"...","vsize":250,"fee":1234,"timestamp_us":178...}}
```

Workers use the `params.type` field to dispatch events. A small number of
older workers also accept legacy `method` strings (`mempool.tx_added`, …).

Standalone tests
----------------
Each worker can be exercised with a manually piped event:

```bash
echo '{"params":{"type":"peer_closed","peer_id":4,"addr":"1.2.3.4:8333","conn_type":"outbound-full-relay","network":0,"time_established":120,"timestamp_us":100}}' \
    | ./p2p_connections.py
```

End-to-end (stdio_bus pipeline)
-------------------------------

```bash
bitcoind -regtest -stdiobus=shadow
# bitcoind spawns the worker from contrib/perf/stdiobus_trace.json
```

Latency benchmarking
--------------------
To compare the eBPF pipeline against stdio_bus IPC for any tracepoint on the
same workload:

```bash
# Terminal 1 — capture stdio_bus IPC events into CSV.
bitcoind -regtest -stdiobus=shadow \
    2>&1 | python3 contrib/tracing/ipc/all_events_recorder.py --csv /tmp/ipc.csv &

# Terminal 2 — capture eBPF events into CSV.
sudo python3 contrib/tracing/all_tracepoints_ebpf_recorder.py \
    --pid $(pidof bitcoind) --csv /tmp/ebpf.csv &

# Run a representative workload (wallet tx, block accept, etc.).
# Stop both recorders, then join and report percentiles:
python3 contrib/tracing/compare_latency.py \
    --ipc /tmp/ipc.csv --ebpf /tmp/ebpf.csv --out /tmp/merged.csv
```

`compare_latency.py` writes per-event deltas and prints a P50/P95/P99 table
grouped by tracepoint name.
