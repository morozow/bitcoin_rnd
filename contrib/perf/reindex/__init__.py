# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Reindex mainnet benchmark package.

Provides infrastructure for measuring tracing overhead on Bitcoin Core
using real mainnet blocks via `bitcoind -reindex`.
"""

from .block_validation import (
    BlockValidationResult,
    validate_block_files,
)
from .config import BenchmarkConfig, Condition
from .datadir_setup import flush_caches, setup_condition_datadir
from .report import BenchmarkReport, format_table, generate_report, report_to_json
from .workload_validation import validate_workload, validate_transaction_density

__all__ = [
    "BenchmarkReport",
    "BlockValidationResult",
    "BenchmarkConfig",
    "Condition",
    "flush_caches",
    "format_table",
    "generate_report",
    "report_to_json",
    "setup_condition_datadir",
    "validate_block_files",
    "validate_transaction_density",
    "validate_workload",
]
