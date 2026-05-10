# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Condition runners for the reindex mainnet benchmark.

Each runner implements the ConditionRunner protocol and handles
condition-specific setup, tracing attachment, and metric collection.
"""

from .base import ConditionRunner, ReindexResult, TracingMetrics, run_reindex
from .baseline import BaselineRunner
from .capnproto_sim import CapnProtoSimRunner
from .ebpf import EbpfRunner
from .ebpf_full import EbpfFullRunner
from .ipc import IpcRunner
from .raw_ipc import RawIpcRunner

__all__ = [
    "BaselineRunner",
    "CapnProtoSimRunner",
    "ConditionRunner",
    "EbpfRunner",
    "EbpfFullRunner",
    "IpcRunner",
    "RawIpcRunner",
    "ReindexResult",
    "TracingMetrics",
    "run_reindex",
]
