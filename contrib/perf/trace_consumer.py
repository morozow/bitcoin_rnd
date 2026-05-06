#!/usr/bin/env python3
"""
Dummy trace consumer worker for stdio_bus benchmarks.

Reads NDJSON events from stdin, counts them, discards content.
This simulates a real tracing consumer that receives events
through the full stdio_bus pipeline (fork/exec, pipe IPC).

Outputs periodic stats to stderr for debugging.
"""
import sys
import time

count = 0
start = time.monotonic()

for line in sys.stdin:
    count += 1
    # Every 1000 events, report to stderr (not stdout — stdout is for responses)
    if count % 1000 == 0:
        elapsed = time.monotonic() - start
        rate = count / elapsed if elapsed > 0 else 0
        print(f"[trace_consumer] {count} events, {rate:.0f} evt/s", file=sys.stderr)

elapsed = time.monotonic() - start
print(f"[trace_consumer] DONE: {count} events in {elapsed:.2f}s", file=sys.stderr)
