#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Data directory setup utilities for the reindex mainnet benchmark.

Handles creation of fresh per-condition data directories with symlinked
block files, and filesystem cache flushing between conditions.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_condition_datadir(
    base: Path, condition_name: str, block_dir: Path
) -> Path:
    """Create a fresh data directory for a benchmark condition.

    Creates a new directory at base/condition_name/ with a blocks/
    subdirectory containing symlinks to all blk*.dat and rev*.dat files
    from block_dir.

    Args:
        base: Base directory for all condition datadirs.
        condition_name: Name of the condition (used as subdirectory name).
        block_dir: Source directory containing mainnet blk*.dat files.

    Returns:
        Path to the created data directory.

    Raises:
        FileNotFoundError: If block_dir does not exist.
        ValueError: If no blk*.dat files found in block_dir.
    """
    block_dir = Path(block_dir)
    base = Path(base)

    if not block_dir.exists():
        raise FileNotFoundError(
            f"Block directory does not exist: {block_dir}"
        )

    blk_files = sorted(block_dir.glob("blk*.dat"))
    if not blk_files:
        raise ValueError(f"No blk*.dat files found in {block_dir}")

    # Create fresh datadir (remove if exists from previous run)
    datadir = base / condition_name
    if datadir.exists():
        shutil.rmtree(datadir)
    datadir.mkdir(parents=True)

    # Create blocks subdirectory with symlinks
    blocks_subdir = datadir / "blocks"
    blocks_subdir.mkdir()

    for blk_file in blk_files:
        link_path = blocks_subdir / blk_file.name
        link_path.symlink_to(blk_file.resolve())

    # Also symlink rev*.dat files if present (needed for some operations)
    rev_files = sorted(block_dir.glob("rev*.dat"))
    for rev_file in rev_files:
        link_path = blocks_subdir / rev_file.name
        link_path.symlink_to(rev_file.resolve())

    logger.info(
        "Created datadir for %s: %s (%d block files symlinked)",
        condition_name,
        datadir,
        len(blk_files),
    )

    return datadir


def flush_caches() -> bool:
    """Flush filesystem caches to eliminate page cache effects.

    Executes `sync` followed by writing to /proc/sys/vm/drop_caches.
    Falls back gracefully if permissions are insufficient.

    Returns:
        True if caches were successfully flushed, False otherwise.
    """
    try:
        # Sync pending writes to disk
        subprocess.run(["sync"], check=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning("sync command failed: %s", e)
        return False

    try:
        # Drop page cache, dentries, and inodes
        drop_caches_path = Path("/proc/sys/vm/drop_caches")
        if drop_caches_path.exists():
            drop_caches_path.write_text("3")
            logger.info("Filesystem caches flushed successfully")
            return True
        else:
            logger.warning(
                "/proc/sys/vm/drop_caches not found — "
                "not running on Linux or procfs not mounted"
            )
            return False
    except PermissionError:
        logger.warning(
            "Permission denied writing to /proc/sys/vm/drop_caches. "
            "Run with --privileged or as root to enable cache flushing. "
            "Proceeding without cache flush."
        )
        return False
    except OSError as e:
        logger.warning("Failed to flush caches: %s", e)
        return False
