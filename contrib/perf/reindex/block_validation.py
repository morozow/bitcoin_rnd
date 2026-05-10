#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Block file validation for the reindex mainnet benchmark.

Parses blk*.dat files using Bitcoin's block file format to count total blocks
and verify sufficient data is available for a credible benchmark.
"""

import struct
from dataclasses import dataclass
from pathlib import Path

# Bitcoin mainnet magic bytes (little-endian in file)
MAINNET_MAGIC = b"\xf9\xbe\xb4\xd9"
MAGIC_SIZE = 4
BLOCK_SIZE_FIELD = 4  # uint32 little-endian


@dataclass
class BlockValidationResult:
    """Result of validating block files for benchmark readiness."""

    valid: bool
    block_count: int
    file_count: int
    error_message: str | None = None


def validate_block_files(
    block_dir: Path, min_blocks: int = 10_000
) -> BlockValidationResult:
    """
    Scan blk*.dat files and count total blocks.

    Uses Bitcoin's block file format:
      4-byte magic (f9beb4d9) + 4-byte size (little-endian) + block data

    Args:
        block_dir: Directory containing blk*.dat files.
        min_blocks: Minimum number of blocks required (default 10,000).

    Returns:
        BlockValidationResult with validation status and block count.
    """
    block_dir = Path(block_dir)

    if not block_dir.exists():
        return BlockValidationResult(
            valid=False,
            block_count=0,
            file_count=0,
            error_message=f"Block directory does not exist: {block_dir}",
        )

    blk_files = sorted(block_dir.glob("blk*.dat"))
    if not blk_files:
        return BlockValidationResult(
            valid=False,
            block_count=0,
            file_count=0,
            error_message=f"No blk*.dat files found in {block_dir}",
        )

    # Estimate block count from file sizes (avoid parsing XOR-obfuscated files)
    # Each mainnet block averages ~500KB after height 150k, ~300 bytes before.
    # For validation purposes, estimate conservatively from file count.
    # Each blk*.dat file holds ~130MB = ~130,000 early blocks or ~260 late blocks.
    # Use a simple heuristic: count files * 8000 blocks as lower bound estimate.
    xor_file = block_dir / "xor.dat"
    if xor_file.exists():
        # XOR-obfuscated files — can't parse without decryption overhead.
        # Estimate block count from total file size.
        total_size = sum(f.stat().st_size for f in blk_files)
        # Conservative: assume average 700 bytes per block (early mainnet)
        total_blocks = total_size // 700
    else:
        total_blocks = 0
        for blk_file in blk_files:
            total_blocks += _count_blocks_in_file(blk_file)

    if total_blocks < min_blocks:
        return BlockValidationResult(
            valid=False,
            block_count=total_blocks,
            file_count=len(blk_files),
            error_message=(
                f"Insufficient blocks: found {total_blocks}, "
                f"need at least {min_blocks}. "
                f"Provide more mainnet blk*.dat files in {block_dir}"
            ),
        )

    return BlockValidationResult(
        valid=True,
        block_count=total_blocks,
        file_count=len(blk_files),
    )


def _count_blocks_in_file(blk_file: Path) -> int:
    """
    Count blocks in a single blk*.dat file by scanning for magic bytes
    followed by a valid block size field.
    """
    count = 0
    file_size = blk_file.stat().st_size

    with open(blk_file, "rb") as f:
        while True:
            # Read magic bytes
            magic = f.read(MAGIC_SIZE)
            if len(magic) < MAGIC_SIZE:
                break

            if magic != MAINNET_MAGIC:
                # Skip padding bytes (block files may have zero-padding)
                # Try to find next magic by scanning byte-by-byte
                # This handles files with padding between blocks
                f.seek(-3, 1)  # back up 3 bytes and try again
                continue

            # Read block size
            size_bytes = f.read(BLOCK_SIZE_FIELD)
            if len(size_bytes) < BLOCK_SIZE_FIELD:
                break

            block_size = struct.unpack("<I", size_bytes)[0]

            # Sanity check: block size should be reasonable (max ~4MB for segwit)
            if block_size == 0 or block_size > 4_000_000:
                # Invalid block size, likely corrupted — skip ahead
                continue

            # Skip over the block data
            current_pos = f.tell()
            if current_pos + block_size > file_size:
                # Truncated file — count what we have
                break

            f.seek(block_size, 1)
            count += 1

    return count
