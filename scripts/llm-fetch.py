"""Download and verify the pinned llama.cpp build and GGUF models for `bench llm`.

    uv run python scripts/llm-fetch.py llama-cpp [--os windows|linux]
    uv run python scripts/llm-fetch.py models --models gpt-oss-20b,gpt-oss-120b [--dir D]
    uv run python scripts/llm-fetch.py verify [--dir D]

Pins (release assets, Hugging Face revisions, sizes, sha256) live in
src/anvesana/suite/llm.py, so the benchmark and this script cannot disagree.
Model downloads resume after an interruption; every file is checked against its
sha256 before it is used, and a file that fails is renamed *.bad, never used.
llama.cpp goes to ~/.cache/anvesana/llama.cpp/<build>/, where `bench llm` finds it.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from anvesana.framework.environment import os_tag
from anvesana.suite import llm

CHUNK = 8 * 2**20


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path, size: int | None = None) -> None:
    """Resumable download to dest (via dest.part)."""
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if size is not None and have == size:
        part.replace(dest)
        return
    req = urllib.request.Request(url, headers={"User-Agent": "anvesana-llm-fetch"})
    if have:
        req.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(req) as r:
        if have and r.status != 206:
            have = 0  # server ignored the range: start again
        total = int(r.headers.get("Content-Length", 0)) + have
        with open(part, "ab" if have else "wb") as f:
            done = have
            while block := r.read(CHUNK):
                f.write(block)
                done += len(block)
                if total:
                    print(f"\r  {dest.name}: {done / 2**30:6.2f} / {total / 2**30:.2f} GiB", end="", flush=True)
    print()
    part.replace(dest)


def check(path: Path, expected: str) -> bool:
    print(f"  sha256 {path.name} ...", end=" ", flush=True)
    got = sha256(path)
    if got == expected:
        print("ok")
        return True
    bad = path.with_name(path.name + ".bad")
    path.replace(bad)
    print(f"MISMATCH (got {got}); moved to {bad.name}")
    return False


def fetch_llama_cpp(target_os: str) -> int:
    dest = llm.default_llama_dir()
    dest.mkdir(parents=True, exist_ok=True)
    base = f"https://github.com/ggml-org/llama.cpp/releases/download/{llm.LLAMA_CPP_BUILD}/"
    for asset, digest in llm.LLAMA_CPP_ASSETS[target_os]:
        archive = dest / asset
        if not (archive.exists() and sha256(archive) == digest):
            download(base + asset, archive)
            if not check(archive, digest):
                return 1
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                z.extractall(dest)
        else:
            with tarfile.open(archive) as t:
                t.extractall(dest, filter="tar")
    exe = "llama-bench.exe" if target_os == "windows" else "llama-bench"
    found = next(dest.rglob(exe), None)
    if found is None:
        print(f"{exe} not found under {dest}")
        return 1
    print(f"llama.cpp {llm.LLAMA_CPP_BUILD}: {found}")
    return 0


def fetch_models(names: list[str], models_dir: Path) -> int:
    models_dir.mkdir(parents=True, exist_ok=True)
    status = 0
    for name in names:
        spec = llm.MODELS[name]
        path = models_dir / spec["file"]
        if path.exists() and path.stat().st_size == spec["size"]:
            print(f"{name}: present, verifying")
            status |= 0 if check(path, spec["sha256"]) else 1
            continue
        url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{spec['file']}"
        print(f"{name}: {spec['size'] / 2**30:.1f} GiB from {spec['repo']}@{spec['revision'][:7]}")
        download(url, path, spec["size"])
        status |= 0 if check(path, spec["sha256"]) else 1
    return status


def verify(models_dir: Path) -> int:
    status = 0
    for name, spec in llm.MODELS.items():
        path = models_dir / spec["file"]
        if path.exists():
            status |= 0 if check(path, spec["sha256"]) else 1
        else:
            print(f"{name}: not present in {models_dir}")
    return status


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("llama-cpp", help="pinned llama.cpp CUDA build for this OS")
    a.add_argument("--os", choices=list(llm.LLAMA_CPP_ASSETS), default=os_tag())
    m = sub.add_parser("models", help="GGUF models")
    m.add_argument("--models", default="gpt-oss-20b", help="comma list of: " + ", ".join(llm.MODELS))
    m.add_argument("--dir", type=Path, default=llm.default_models_dir())
    v = sub.add_parser("verify", help="re-check the sha256 of every model present")
    v.add_argument("--dir", type=Path, default=llm.default_models_dir())
    args = p.parse_args(argv)
    if args.cmd == "llama-cpp":
        return fetch_llama_cpp(args.os)
    if args.cmd == "models":
        names = [n.strip() for n in args.models.split(",") if n.strip()]
        unknown = [n for n in names if n not in llm.MODELS]
        if unknown:
            p.error(f"unknown model(s): {', '.join(unknown)}")
        return fetch_models(names, args.dir)
    return verify(args.dir)


if __name__ == "__main__":
    sys.exit(main())
