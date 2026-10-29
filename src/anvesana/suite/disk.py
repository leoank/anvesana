"""NVMe storage benchmark with OS caches bypassed on both platforms
(port of stress_disk.ps1 / stress_disk.sh).

  Windows: CreateFileW with FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH
  Linux:   O_DIRECT (| O_SYNC for writes)

Both need sector-aligned buffers, which anonymous mmap provides. Note the
original PowerShell version only set WriteThrough, so its reads were served
from the Windows file cache and overstate read performance.

The test file defaults to the home directory: /tmp is often tmpfs on Linux,
which would measure RAM instead of the SSD (and rejects O_DIRECT).
"""

from __future__ import annotations

import ctypes
import mmap
import os
import random
import sys
import threading
import time
from pathlib import Path

from ..framework.console import banner, report, step, summary
from ..framework.records import Metric

NAME = "disk"
VERSION = 1  # bump when results stop being comparable with earlier runs
DESCRIPTION = "NVMe sequential and 4K random I/O, unbuffered (port of stress_disk.ps1)"

BLOCK_4K = 4096


class _Overlapped(ctypes.Structure):
    """Carries the file offset for positional I/O on a synchronous Windows handle."""
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", ctypes.c_uint32), ("OffsetHigh", ctypes.c_uint32), ("hEvent", ctypes.c_void_p)]


class RawFile:
    """Unbuffered positional I/O on one file handle."""

    def __init__(self, path: str, write: bool, create: bool = False):
        self.path = path
        if sys.platform == "win32":
            self._open_windows(write, create)
        else:
            flags = (os.O_RDWR | os.O_SYNC) if write else os.O_RDONLY
            if create:
                flags |= os.O_CREAT | os.O_TRUNC
            self.fd = os.open(path, flags | os.O_DIRECT, 0o600)

    def _open_windows(self, write: bool, create: bool):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = ctypes.c_void_p
        k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                    ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        k32.ReadFile.argtypes = k32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                                          ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        generic_read, generic_write = 0x80000000, 0x40000000
        no_buffering, write_through = 0x20000000, 0x80000000
        access = generic_read | (generic_write if write else 0)
        disposition = 2 if create else 3  # CREATE_ALWAYS / OPEN_EXISTING
        flags = no_buffering | (write_through if write else 0)
        handle = k32.CreateFileW(self.path, access, 1, None, disposition, flags, None)  # FILE_SHARE_READ
        if handle in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        self._k32, self.handle = k32, handle

    def pwrite(self, buf: mmap.mmap, offset: int, length: int):
        if sys.platform == "win32":
            done = ctypes.c_uint32()
            ov = _Overlapped(None, None, offset & 0xFFFFFFFF, offset >> 32, None)
            addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
            if not self._k32.WriteFile(self.handle, addr, length, ctypes.byref(done), ctypes.byref(ov)):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            os.pwrite(self.fd, memoryview(buf)[:length], offset)

    def pread(self, buf: mmap.mmap, offset: int, length: int):
        if sys.platform == "win32":
            done = ctypes.c_uint32()
            ov = _Overlapped(None, None, offset & 0xFFFFFFFF, offset >> 32, None)
            addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
            if not self._k32.ReadFile(self.handle, addr, length, ctypes.byref(done), ctypes.byref(ov)):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            os.preadv(self.fd, [memoryview(buf)[:length]], offset)

    def close(self):
        if sys.platform == "win32":
            self._k32.CloseHandle(self.handle)
        else:
            os.close(self.fd)


def _aligned(nbytes: int, fill: bytes | None = None) -> mmap.mmap:
    buf = mmap.mmap(-1, nbytes)  # page aligned
    if fill:
        buf.write(fill * (nbytes // len(fill)))
    return buf


def seq_write(path: str, total_mb: int, block_mb: int = 4) -> float:
    block = block_mb * 2**20
    buf = _aligned(block, os.urandom(BLOCK_4K))  # incompressible
    f = RawFile(path, write=True, create=True)
    t0 = time.perf_counter()
    for i in range(total_mb // block_mb):
        f.pwrite(buf, i * block, block)
    elapsed = time.perf_counter() - t0
    f.close()
    return total_mb / elapsed


def seq_read(path: str, total_mb: int, block_mb: int = 4) -> float:
    block = block_mb * 2**20
    buf = _aligned(block)
    f = RawFile(path, write=False)
    t0 = time.perf_counter()
    for i in range(total_mb // block_mb):
        f.pread(buf, i * block, block)
    elapsed = time.perf_counter() - t0
    f.close()
    return total_mb / elapsed


def random_4k(path: str, offsets: list[int], write: bool) -> tuple[float, float]:
    """Queue depth 1. Returns (IOPS, mean latency ms)."""
    buf = _aligned(BLOCK_4K, b"\x55")
    f = RawFile(path, write=write)
    op = f.pwrite if write else f.pread
    t0 = time.perf_counter()
    for off in offsets:
        op(buf, off, BLOCK_4K)
    elapsed = time.perf_counter() - t0
    f.close()
    return len(offsets) / elapsed, elapsed * 1000 / len(offsets)


def random_4k_read_qd(path: str, file_blocks: int, threads: int, seconds: float) -> float:
    """Queue depth N via N threads with their own handles (the GIL is released during I/O)."""
    counts = [0] * threads
    stop = threading.Event()

    def worker(i):
        rng = random.Random(i)
        buf = _aligned(BLOCK_4K)
        f = RawFile(path, write=False)
        n = 0
        while not stop.is_set():
            f.pread(buf, rng.randrange(file_blocks) * BLOCK_4K, BLOCK_4K)
            n += 1
        counts[i] = n
        f.close()

    pool = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    t0 = time.perf_counter()
    for t in pool:
        t.start()
    time.sleep(seconds)
    stop.set()
    for t in pool:
        t.join()
    return sum(counts) / (time.perf_counter() - t0)


def add_arguments(p):
    p.add_argument("--path", default=str(Path.home() / ".bench_disk.tmp"), help="test file location")
    p.add_argument("--size-mb", type=int, default=2048, help="sequential test size")
    p.add_argument("--rand-ops", type=int, default=5000)
    p.add_argument("--qd", type=int, default=8, help="threads for the queue-depth random read test")


def run(args) -> list[Metric]:
    path = args.path
    banner("NVIDIA RTX Spark - NVMe Storage Benchmark", f"Target file: {path}", "Caches bypassed (unbuffered / O_DIRECT)")
    metrics = []
    try:
        step(f"[1/5] Sequential write ({args.size_mb} MB, 4 MiB blocks)...")
        w = seq_write(path, args.size_mb)
        report("Sequential write", w, "MB/s")

        step(f"[2/5] Sequential read ({args.size_mb} MB, 4 MiB blocks)...")
        r = seq_read(path, args.size_mb)
        report("Sequential read", r, "MB/s")

        file_blocks = args.size_mb * 2**20 // BLOCK_4K
        rng = random.Random(42)
        offsets = [rng.randrange(file_blocks) * BLOCK_4K for _ in range(args.rand_ops)]

        step(f"[3/5] Random 4K write QD1 ({args.rand_ops} ops, write-through)...")
        wi, wl = random_4k(path, offsets, write=True)
        report("Random 4K write", wi, "IOPS", f"(latency {wl:.3f} ms)")

        step(f"[4/5] Random 4K read QD1 ({args.rand_ops} ops)...")
        ri, rl = random_4k(path, offsets, write=False)
        report("Random 4K read", ri, "IOPS", f"(latency {rl:.3f} ms)")

        step(f"[5/5] Random 4K read QD{args.qd} (5s)...")
        rq = random_4k_read_qd(path, file_blocks, args.qd, 5.0)
        report(f"Random 4K read QD{args.qd}", rq, "IOPS")

        metrics = [
            Metric("disk.seq_write", w, "MB/s"),
            Metric("disk.seq_read", r, "MB/s"),
            Metric("disk.rand4k_write_qd1", wi, "IOPS"),
            Metric("disk.rand4k_write_qd1_latency", wl, "ms", higher_is_better=False),
            Metric("disk.rand4k_read_qd1", ri, "IOPS"),
            Metric("disk.rand4k_read_qd1_latency", rl, "ms", higher_is_better=False),
            Metric(f"disk.rand4k_read_qd{args.qd}", rq, "IOPS"),
        ]
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    summary("Disk Benchmark Summary", metrics)
    return metrics
