#!/usr/bin/env python3
"""
Assemble a standalone CUDA toolkit from NVIDIA's redistributable components.

The pip wheels ``nvidia-cuda-nvcc-cu12`` and friends are a trap: they ship
``ptxas`` and a handful of headers, but no ``nvcc``, so a build against them
gets as far as the compiler identification and then fails on a missing
``libcudadevrt``.  NVIDIA publishes the same components as standalone
archives, and those are complete.

This script downloads the archives for one CUDA version, merges them into a
toolkit root, and prints the root.  Pass that root to CMake:

    python cpp/scripts/bootstrap_cuda.py --root ./.cuda
    cmake -S cpp -B cpp/build -G Ninja -DCUDAToolkit_ROOT=./.cuda

Only ``nvcc``, the runtime and the C++ headers are fetched - not the whole
toolkit, which is several gigabytes.

Windows still needs the Windows SDK (the Universal C Runtime headers and the
import libraries).  That is a separate download and it needs an elevated
shell; this script does not attempt it.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import ssl
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

REDIST_BASE = "https://developer.download.nvidia.com/compute/cuda/redist"

# The components that a compiled extension needs: the compiler, the runtime
# it links against, and the C++ headers it compiles against.
COMPONENTS = ("cuda_nvcc", "cuda_cudart", "cuda_cccl")


def _platform_key() -> str:
    """The redistributable directory name for this machine."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "windows-x86_64"
    if system == "darwin":
        # Apple silicon and Intel have different archives, but neither is a
        # target for this extension.
        raise SystemExit("macOS is not a supported target for the CUDA extension")
    if machine in ("x86_64", "amd64"):
        return "linux-x86_64"
    if machine in ("aarch64", "arm64"):
        return "linux-sbsa"
    raise SystemExit(f"unsupported architecture: {machine}")


def fetch_manifest(version: str) -> dict:
    url = f"{REDIST_BASE}/redistrib_{version}.json"
    with urllib.request.urlopen(url, context=ssl.create_default_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size > 0:
        print(f"  cached  {destination.name}")
        return destination
    print(f"  fetching {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url, context=ssl.create_default_context()) as response:
        with tmp.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    tmp.replace(destination)
    return destination


def extract(archive: Path, workdir: Path) -> Path:
    """Unpack an archive and return the directory it unpacks into."""
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(workdir)
    else:
        with tarfile.open(archive) as tf:
            tf.extractall(workdir, filter="data")
    roots = [p for p in workdir.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise SystemExit(f"unexpected archive layout in {archive}")
    return roots[0]


def merge(source: Path, root: Path) -> None:
    """Merge the contents of one component into the toolkit root.

    The merge is recursive and never removes anything.  The components
    overlap in a way that makes a replacement wrong: the runtime ships
    ``include/cuda_runtime.h`` and the C++ headers ship ``include/cuda/std/``,
    and both live under ``include/``.  Replacing the directory with the last
    component that has one throws the runtime's headers away, and the build
    then dies with a missing ``cuda_runtime.h``.
    """
    for entry in source.iterdir():
        target = root / entry.name
        if entry.is_dir():
            if target.is_dir():
                merge(entry, target)
            elif target.exists():
                target.unlink()
                shutil.copytree(entry, target)
            else:
                shutil.copytree(entry, target)
        else:
            shutil.copy2(entry, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default="12.9.0",
        help="the CUDA release to assemble (default: 12.9.0)",
    )
    parser.add_argument(
        "--root",
        default="./.cuda",
        help="where to put the toolkit (default: ./.cuda)",
    )
    parser.add_argument(
        "--cache",
        default=None,
        help="where to keep the downloaded archives (default: <root>/.cache)",
    )
    args = parser.parse_args()

    key = _platform_key()
    root = Path(args.root).resolve()
    cache = Path(args.cache).resolve() if args.cache else root / ".cache"
    workdir = root / ".work"
    root.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    print(f"CUDA {args.version} for {key}")
    manifest = fetch_manifest(args.version)

    for component in COMPONENTS:
        entry = manifest.get(component)
        if entry is None:
            raise SystemExit(f"{component} is not in the {args.version} manifest")
        platform_entry = entry.get(key)
        if platform_entry is None:
            raise SystemExit(f"{component} has no archive for {key}")
        relative = platform_entry["relative_path"]
        print(f"{component} {entry.get('version')}")
        archive = download(f"{REDIST_BASE}/{relative}", cache / Path(relative).name)
        unpacked = extract(archive, workdir / component)
        merge(unpacked, root)

    if workdir.exists():
        shutil.rmtree(workdir)

    # The archives put the libraries in lib/ and lib/x64/, while nvcc's link
    # line looks in lib64/.  Merge them so that the driver finds both.
    target = root / "lib64"
    target.mkdir(exist_ok=True)
    for library_dir in ("lib", "lib/x64"):
        source = root / library_dir
        if not source.is_dir():
            continue
        for library in source.iterdir():
            if not library.is_file():
                continue
            destination = target / library.name
            if library.resolve() == destination.resolve():
                continue
            shutil.copy2(library, destination)

    nvcc = root / "bin" / ("nvcc.exe" if key.startswith("windows") else "nvcc")
    if not nvcc.exists():
        raise SystemExit(f"{nvcc} is missing - the archive layout changed?")

    print()
    print("Toolkit assembled:")
    print(f"  {root}")
    print()
    print("Build with:")
    print(f"  cmake -S cpp -B cpp/build -G Ninja -DCUDAToolkit_ROOT={root}")
    if key.startswith("windows"):
        print()
        print("Windows also needs the Windows SDK for the C runtime headers")
        print("and the import libraries.  Install it with the 'Desktop")
        print("development with C++' workload of the Visual Studio Build Tools.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
