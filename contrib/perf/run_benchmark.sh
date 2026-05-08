#!/bin/bash
# IPC vs eBPF Tracing Benchmark — Fair Measurement
#
# Each condition runs in a separate Docker container to eliminate
# page cache bias. No shared state between conditions.
#
# Usage:
#   ./contrib/perf/run_benchmark.sh /path/to/mainnet/blocks 200000
#
# Requirements:
#   - Docker with --privileged support
#   - Pre-built image: docker build -f contrib/perf/docker/Dockerfile.ebpf_vs_ipc -t bitcoin-ebpf-bench .
#   - Mainnet block files at the specified path

set -euo pipefail

BLOCKS_DIR="${1:?Usage: $0 /path/to/blocks [num_blocks]}"
NUM_BLOCKS="${2:-200000}"
IMAGE="bitcoin-ebpf-bench"

echo "======================================================================"
echo "IPC vs eBPF Tracing Benchmark"
echo "Blocks: $NUM_BLOCKS"
echo "Block data: $BLOCKS_DIR"
echo "Each condition runs in a separate container for fair measurement."
echo "======================================================================"
echo ""

run_condition() {
    local name="$1"
    echo "[Running] $name..."
    docker run --privileged --rm \
        -v "$BLOCKS_DIR:/blocks:ro" \
        "$IMAGE" --blocks="$NUM_BLOCKS" --only="$name" 2>&1 | grep "→"
}

echo "--- Condition 1/3: Baseline ---"
run_condition baseline
echo ""

echo "--- Condition 2/3: eBPF ---"
run_condition ebpf
echo ""

echo "--- Condition 3/3: IPC ---"
run_condition ipc
echo ""

echo "======================================================================"
echo "Done. Each condition ran in an isolated container with cold cache."
echo "Compare the blocks/s values directly — no cache bias between them."
echo "======================================================================"
