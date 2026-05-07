#!/bin/bash
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
#
# eBPF vs IPC comparative benchmark orchestrator.
#
# 1. Builds Docker image with USDT-enabled bitcoind + bpftrace
# 2. Runs eBPF overhead measurement inside container (--privileged)
# 3. Runs IPC overhead measurement on host (uses existing build)
# 4. Prints side-by-side comparison
#
# USAGE:
#   ./contrib/perf/run_comparison.sh [BLOCKS]
#
# Requires: Docker, Python 3, existing host build with stdio_bus

set -euo pipefail

BLOCKS="${1:-500}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE_NAME="bitcoin-ebpf-bench"
RESULTS_DIR="$REPO_ROOT/contrib/perf/results"

echo "============================================================"
echo "eBPF vs IPC Comparative Benchmark"
echo "Blocks per condition: $BLOCKS"
echo "============================================================"
echo ""

# --- Step 1: Build Docker image ---
echo "[Step 1/3] Building Docker image ($IMAGE_NAME)..."
docker build \
    -f "$REPO_ROOT/contrib/perf/docker/Dockerfile.ebpf_vs_ipc" \
    -t "$IMAGE_NAME" \
    "$REPO_ROOT" 2>&1 | tail -5
echo ""

# --- Step 2: Run eBPF benchmark in container ---
echo "[Step 2/3] Running eBPF benchmark in Docker (--privileged)..."
EBPF_JSON=$(docker run --privileged --rm "$IMAGE_NAME" --blocks="$BLOCKS" 2>&1 | tee /dev/stderr | tail -1)
echo ""

# --- Step 3: Run IPC benchmark on host ---
echo "[Step 3/3] Running IPC benchmark on host..."
python3 "$REPO_ROOT/contrib/perf/run_ipc_benchmark_suite_full.py" --blocks="$BLOCKS" --only all_parity 2>&1 | tail -10
echo ""

# --- Step 4: Compare ---
echo "============================================================"
echo "COMPARISON"
echo "============================================================"

# Parse eBPF result
EBPF_OVERHEAD=$(echo "$EBPF_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['ebpf']['overhead_pct'])" 2>/dev/null || echo "N/A")
EBPF_BPS=$(echo "$EBPF_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['ebpf']['blocks_per_s'])" 2>/dev/null || echo "N/A")
BASELINE_BPS=$(echo "$EBPF_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['baseline']['blocks_per_s'])" 2>/dev/null || echo "N/A")

# Parse IPC result
IPC_REPORT="$RESULTS_DIR/full_parity_suite_report.json"
IPC_OVERHEAD=$(python3 -c "import json; d=json.load(open('$IPC_REPORT')); print(d.get('all_parity',{}).get('overhead_pct','N/A'))" 2>/dev/null || echo "N/A")
IPC_BPS=$(python3 -c "import json; d=json.load(open('$IPC_REPORT')); print(d.get('all_parity',{}).get('shadow_blocks_per_s','N/A'))" 2>/dev/null || echo "N/A")
IPC_BASELINE=$(python3 -c "import json; d=json.load(open('$IPC_REPORT')); print(d.get('all_parity',{}).get('baseline_blocks_per_s','N/A'))" 2>/dev/null || echo "N/A")

printf "%-20s %12s %12s %12s\n" "Method" "Baseline" "Traced" "Overhead"
printf "%-20s %12s %12s %12s\n" "------" "--------" "------" "--------"
printf "%-20s %10s b/s %10s b/s %10s%%\n" "eBPF (Docker)" "$BASELINE_BPS" "$EBPF_BPS" "$EBPF_OVERHEAD"
printf "%-20s %10s b/s %10s b/s %10s%%\n" "IPC (Host)" "$IPC_BASELINE" "$IPC_BPS" "$IPC_OVERHEAD"
echo ""
echo "Note: Overhead % is relative to each environment's own baseline."
echo "      Direct blocks/s comparison across environments is not meaningful"
echo "      (different hardware virtualization). Compare OVERHEAD % only."
echo "============================================================"
