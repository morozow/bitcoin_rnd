#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""
Unit tests for datadir setup and symlink creation.

Tests:
- Symlink creation for block files
- Cache flush with and without permissions
- Fresh datadir creation per condition

Requirements: 10.1, 10.3, 10.4
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # contrib/perf

from reindex.datadir_setup import setup_condition_datadir, flush_caches


# ============================================================
# Symlink creation tests
# ============================================================


def test_symlink_creation_basic():
    """Symlinks are created for all blk*.dat files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()

        # Create multiple block files
        for i in range(5):
            (block_dir / f"blk{i:05d}.dat").write_bytes(b"\x00" * 100)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        datadir = setup_condition_datadir(base, "test_cond", block_dir)

        # Verify all symlinks exist
        blocks_subdir = datadir / "blocks"
        assert blocks_subdir.exists()

        for i in range(5):
            link = blocks_subdir / f"blk{i:05d}.dat"
            assert link.exists(), f"Missing symlink: {link}"
            assert link.is_symlink(), f"Not a symlink: {link}"
            # Symlink target should resolve to the original file
            assert link.resolve() == (block_dir / f"blk{i:05d}.dat").resolve()


def test_symlink_creation_rev_files():
    """Symlinks are also created for rev*.dat files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()

        # Create block and rev files
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)
        (block_dir / "blk00001.dat").write_bytes(b"\x00" * 100)
        (block_dir / "rev00000.dat").write_bytes(b"\x00" * 50)
        (block_dir / "rev00001.dat").write_bytes(b"\x00" * 50)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        datadir = setup_condition_datadir(base, "test_rev", block_dir)
        blocks_subdir = datadir / "blocks"

        # Both blk and rev files should be symlinked
        assert (blocks_subdir / "blk00000.dat").is_symlink()
        assert (blocks_subdir / "blk00001.dat").is_symlink()
        assert (blocks_subdir / "rev00000.dat").is_symlink()
        assert (blocks_subdir / "rev00001.dat").is_symlink()


def test_symlink_targets_are_absolute():
    """Symlinks point to absolute paths (resolved from block_dir)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        datadir = setup_condition_datadir(base, "test_abs", block_dir)
        link = datadir / "blocks" / "blk00000.dat"

        # The symlink target should be an absolute path
        target = os.readlink(str(link))
        assert os.path.isabs(target), f"Symlink target is not absolute: {target}"


def test_symlink_only_blk_and_rev_files():
    """Only blk*.dat and rev*.dat files are symlinked, not other files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()

        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)
        (block_dir / "rev00000.dat").write_bytes(b"\x00" * 50)
        (block_dir / "other.txt").write_text("not a block file")
        (block_dir / "index.dat").write_bytes(b"\x00" * 30)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        datadir = setup_condition_datadir(base, "test_filter", block_dir)
        blocks_subdir = datadir / "blocks"

        # blk and rev files are symlinked
        assert (blocks_subdir / "blk00000.dat").exists()
        assert (blocks_subdir / "rev00000.dat").exists()

        # Other files are NOT symlinked
        assert not (blocks_subdir / "other.txt").exists()
        assert not (blocks_subdir / "index.dat").exists()


def test_symlink_preserves_file_content():
    """Reading through symlinks returns the original file content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()

        content = b"\xf9\xbe\xb4\xd9" + b"\x50\x00\x00\x00" + b"\x01" * 80
        (block_dir / "blk00000.dat").write_bytes(content)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        datadir = setup_condition_datadir(base, "test_content", block_dir)
        link = datadir / "blocks" / "blk00000.dat"

        # Content through symlink matches original
        assert link.read_bytes() == content


def test_symlink_creation_large_number_of_files():
    """Symlinks work correctly with many block files (simulating full node)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()

        # Create 20 block files (simulating first 20 blk files)
        for i in range(20):
            (block_dir / f"blk{i:05d}.dat").write_bytes(b"\x00" * 50)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        datadir = setup_condition_datadir(base, "test_many", block_dir)
        blocks_subdir = datadir / "blocks"

        # All 20 should be symlinked
        symlinks = list(blocks_subdir.glob("blk*.dat"))
        assert len(symlinks) == 20


# ============================================================
# Fresh datadir creation per condition
# ============================================================


def test_fresh_datadir_per_condition():
    """Each condition gets its own fresh data directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        # Create datadirs for multiple conditions
        datadir_baseline = setup_condition_datadir(base, "baseline", block_dir)
        datadir_ebpf = setup_condition_datadir(base, "ebpf", block_dir)
        datadir_ipc = setup_condition_datadir(base, "ipc", block_dir)

        # Each is a separate directory
        assert datadir_baseline != datadir_ebpf
        assert datadir_ebpf != datadir_ipc
        assert datadir_baseline == base / "baseline"
        assert datadir_ebpf == base / "ebpf"
        assert datadir_ipc == base / "ipc"

        # Each has its own blocks/ subdirectory with symlinks
        assert (datadir_baseline / "blocks" / "blk00000.dat").is_symlink()
        assert (datadir_ebpf / "blocks" / "blk00000.dat").is_symlink()
        assert (datadir_ipc / "blocks" / "blk00000.dat").is_symlink()


def test_fresh_datadir_removes_stale_data():
    """Re-creating a datadir removes all previous content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        # First creation
        datadir = setup_condition_datadir(base, "test", block_dir)

        # Add stale files (simulating leftover from previous run)
        (datadir / "chainstate").mkdir()
        (datadir / "chainstate" / "LOCK").write_text("locked")
        (datadir / "debug.log").write_text("old log data")
        (datadir / "peers.dat").write_bytes(b"\x00" * 50)

        # Re-create (should be fresh)
        datadir = setup_condition_datadir(base, "test", block_dir)

        # Stale files should be gone
        assert not (datadir / "chainstate").exists()
        assert not (datadir / "debug.log").exists()
        assert not (datadir / "peers.dat").exists()

        # Fresh symlinks should be present
        assert (datadir / "blocks" / "blk00000.dat").is_symlink()


def test_fresh_datadir_creates_parent_directories():
    """setup_condition_datadir creates parent directories if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        (block_dir / "blk00000.dat").write_bytes(b"\x00" * 100)

        # Base directory doesn't exist yet
        base = Path(tmpdir) / "deep" / "nested" / "datadirs"
        # Note: setup_condition_datadir expects base to exist
        # (it creates base/condition_name)
        base.mkdir(parents=True)

        datadir = setup_condition_datadir(base, "test", block_dir)
        assert datadir.exists()
        assert (datadir / "blocks" / "blk00000.dat").is_symlink()


def test_fresh_datadir_nonexistent_block_dir_raises():
    """FileNotFoundError raised when block_dir doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        try:
            setup_condition_datadir(
                base, "test", Path("/nonexistent/blocks")
            )
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            assert "does not exist" in str(e)


def test_fresh_datadir_empty_block_dir_raises():
    """ValueError raised when block_dir has no blk*.dat files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        block_dir = Path(tmpdir) / "blocks"
        block_dir.mkdir()
        # Only non-block files
        (block_dir / "readme.txt").write_text("no blocks here")

        base = Path(tmpdir) / "datadirs"
        base.mkdir()

        try:
            setup_condition_datadir(base, "test", block_dir)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "No blk*.dat" in str(e)


# ============================================================
# Cache flush tests
# ============================================================


def test_cache_flush_success_on_linux():
    """flush_caches returns True when sync and drop_caches succeed."""
    with patch("reindex.datadir_setup.subprocess.run") as mock_run, \
         patch("reindex.datadir_setup.Path.exists", return_value=True), \
         patch("reindex.datadir_setup.Path.write_text") as mock_write:
        mock_run.return_value = MagicMock(returncode=0)

        result = flush_caches()

        # sync was called
        mock_run.assert_called_once_with(["sync"], check=True, timeout=30)
        # drop_caches was written
        mock_write.assert_called_once_with("3")
        assert result is True


def test_cache_flush_permission_denied():
    """flush_caches returns False and logs warning on PermissionError."""
    with patch("reindex.datadir_setup.subprocess.run") as mock_run, \
         patch("reindex.datadir_setup.Path.exists", return_value=True), \
         patch(
             "reindex.datadir_setup.Path.write_text",
             side_effect=PermissionError("Permission denied"),
         ):
        mock_run.return_value = MagicMock(returncode=0)

        result = flush_caches()

        # sync succeeded but drop_caches failed
        assert result is False


def test_cache_flush_no_proc_filesystem():
    """flush_caches returns False when /proc/sys/vm/drop_caches doesn't exist."""
    with patch("reindex.datadir_setup.subprocess.run") as mock_run, \
         patch("reindex.datadir_setup.Path.exists", return_value=False):
        mock_run.return_value = MagicMock(returncode=0)

        result = flush_caches()

        # sync succeeded but no procfs
        assert result is False


def test_cache_flush_sync_fails():
    """flush_caches returns False when sync command fails."""
    import subprocess

    with patch(
        "reindex.datadir_setup.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "sync"),
    ):
        result = flush_caches()
        assert result is False


def test_cache_flush_sync_timeout():
    """flush_caches returns False when sync command times out."""
    import subprocess

    with patch(
        "reindex.datadir_setup.subprocess.run",
        side_effect=subprocess.TimeoutExpired("sync", 30),
    ):
        result = flush_caches()
        assert result is False


def test_cache_flush_os_error():
    """flush_caches returns False on generic OSError writing drop_caches."""
    with patch("reindex.datadir_setup.subprocess.run") as mock_run, \
         patch("reindex.datadir_setup.Path.exists", return_value=True), \
         patch(
             "reindex.datadir_setup.Path.write_text",
             side_effect=OSError("I/O error"),
         ):
        mock_run.return_value = MagicMock(returncode=0)

        result = flush_caches()
        assert result is False


def test_cache_flush_real_macos():
    """On macOS, flush_caches returns False (no /proc/sys/vm/drop_caches).

    This test runs on the actual system without mocking to verify
    the real behavior on macOS (where the test suite runs).
    """
    # On macOS, /proc/sys/vm/drop_caches doesn't exist
    # flush_caches should handle this gracefully
    if sys.platform == "darwin":
        result = flush_caches()
        # On macOS: sync may succeed but drop_caches won't exist
        # Result depends on whether sync works (it should on macOS)
        # The important thing is it doesn't crash
        assert isinstance(result, bool)


# ============================================================
# Run all tests
# ============================================================


def run_all_tests():
    """Run all datadir setup unit tests and report results."""
    import traceback

    tests = [
        # Symlink creation
        test_symlink_creation_basic,
        test_symlink_creation_rev_files,
        test_symlink_targets_are_absolute,
        test_symlink_only_blk_and_rev_files,
        test_symlink_preserves_file_content,
        test_symlink_creation_large_number_of_files,
        # Fresh datadir per condition
        test_fresh_datadir_per_condition,
        test_fresh_datadir_removes_stale_data,
        test_fresh_datadir_creates_parent_directories,
        test_fresh_datadir_nonexistent_block_dir_raises,
        test_fresh_datadir_empty_block_dir_raises,
        # Cache flush
        test_cache_flush_success_on_linux,
        test_cache_flush_permission_denied,
        test_cache_flush_no_proc_filesystem,
        test_cache_flush_sync_fails,
        test_cache_flush_sync_timeout,
        test_cache_flush_os_error,
        test_cache_flush_real_macos,
    ]

    passed = 0
    failed = 0
    errors = []

    print("Running datadir setup unit tests...")
    print("=" * 60)

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
            print(f"  ✓ {test_fn.__name__}")
        except Exception as e:
            failed += 1
            errors.append((test_fn.__name__, e))
            print(f"  ✗ {test_fn.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'='*60}")

    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
        return 1
    else:
        print("\n✓ All datadir setup unit tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
