"""Download the MLX model weights for the Apple Silicon backend into `models/`.

Why this exists (same reason as ~/repos/EEP/scripts/get_models.py): on a corporate network the
Hugging Face file CDN (`cas-server.xethub.hf.co` / `us.aws.cdn.hf.co`) is blocked by the TLS proxy
with a 403, so `mlx_vlm.load("mlx-community/...")` cannot fetch weights. ModelScope mirrors the same
repos from a host that gets through. We fetch there and load from disk; the loaders look under
`models/<repo-basename>` first (see docparse/models/mlx_backends.py: resolve_model).

Usage:
    uv run python scripts/get_mlx_models.py            # fetch all three MLX models
    uv run python scripts/get_mlx_models.py --list     # show what would be fetched
    uv run python scripts/get_mlx_models.py embedding  # just one (vl | embedding | describe)

Run with -I is not required; this script only reads from the network and writes under models/.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# The corporate gateway terminates TLS with its own CA that lives in the macOS keychain but not in
# certifi; truststore makes stdlib TLS read the system trust store (the correct fix, not verify=off).
try:
    import truststore

    truststore.inject_into_ssl()
except ModuleNotFoundError:
    pass  # not needed off the proxied network

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

API = "https://www.modelscope.cn/api/v1/models/{repo}/repo/files?Recursive=true"
RESOLVE = "https://www.modelscope.cn/models/{repo}/resolve/master/{path}"

# docparse model key -> (ModelScope repo, local dir name under models/).
# The local dir name must match the HF repo basename in registry.py's mlx_model_id, so resolve_model
# finds it (mlx-community/embeddinggemma-2-bf16 -> models/embeddinggemma-2-bf16).
WANTED: dict[str, tuple[str, str]] = {
    "vl": ("mlx-community/PaddleOCR-VL-bfloat16", "PaddleOCR-VL-bfloat16"),
    "embedding": ("mlx-community/embeddinggemma-2-bf16", "embeddinggemma-2-bf16"),
    "describe": ("mlx-community/Qwen2.5-VL-3B-Instruct-4bit", "Qwen2.5-VL-3B-Instruct-4bit"),
}


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "docparse-model-fetch/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def rel_of(p: Path) -> str:
    try:
        return str(p.relative_to(MODELS))
    except ValueError:
        return p.name


def _download(url: str, dest: Path, expected: int, *, restart_at: int = 0) -> int:
    headers = {"User-Agent": "docparse-model-fetch/0.1"}
    mode = "wb"
    if restart_at:
        headers["Range"] = f"bytes={restart_at}-"
        mode = "ab"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, mode) as fh:
        done = restart_at
        last_report = done
        while chunk := r.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if expected and done - last_report > 200 << 20:
                print(f"      ... {rel_of(dest):<40} {done / 1e6:7.0f}/{expected / 1e6:.0f} MB", flush=True)
                last_report = done
    return done


def list_files(repo: str) -> list[tuple[str, int]]:
    data = json.loads(_get(API.format(repo=repo)))
    out = []
    for f in data.get("Data", {}).get("Files", []):
        p = f.get("Path")
        if p and not f.get("Directory") and not p.startswith(".git"):
            out.append((p, int(f.get("Size") or 0)))
    return out


def fetch(repo: str, local_name: str, *, dry: bool = False) -> Path:
    dest_root = MODELS / local_name
    files = list_files(repo)
    total = sum(s for _, s in files)
    print(f"[{repo}] {len(files)} files, {total / 1e6:.0f} MB -> {dest_root}", flush=True)
    if dry:
        return dest_root

    def one(item: tuple[str, int]) -> str:
        rel, size = item
        dest = dest_root / rel
        if dest.exists() and dest.stat().st_size == size:
            return f"skip  {rel}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = RESOLVE.format(repo=repo, path=rel)
        tmp = dest.with_suffix(dest.suffix + ".part")
        for attempt in range(1, 6):
            have = tmp.stat().st_size if tmp.exists() else 0
            try:
                got = _download(url, tmp, size, restart_at=have)
                if size and got < size:
                    raise IOError(f"short read {got}/{size}")
                tmp.replace(dest)
                return f"ok    {rel} ({size / 1e6:.1f} MB)"
            except Exception as exc:  # noqa: BLE001 - retry anything transient
                if attempt == 5:
                    return f"FAIL  {rel}: {type(exc).__name__}: {exc}"
                time.sleep(3 * attempt)
        return f"FAIL  {rel}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        for line in pool.map(one, files):
            print("   ", line, flush=True)
    return dest_root


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="only report what would be downloaded")
    ap.add_argument("only", nargs="?", choices=sorted(WANTED), help="restrict to one model key")
    args = ap.parse_args()

    MODELS.mkdir(exist_ok=True)
    failed = False
    for key, (repo, local) in WANTED.items():
        if args.only and args.only != key:
            continue
        try:
            fetch(repo, local, dry=args.list)
        except urllib.error.HTTPError as exc:
            print(f"[{repo}] HTTP {exc.code} — repo not mirrored on ModelScope?", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
