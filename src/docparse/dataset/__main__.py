"""CLI: uv run python -m docparse.dataset {validate,summary,...}"""
import argparse
import sys
from pathlib import Path

import httpx

from . import download, manifest
from .sources import CANDIDATES_DIR, govdocs, nist, ntrs, seeds, write_candidates
from .summary import summarize


def cmd_validate(args) -> int:
    entries = manifest.load(args.manifest)
    errors = manifest.validate(entries, require_verified=args.verified)
    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(entries)} entries, {len(errors)} errors")
    return 1 if errors else 0


def cmd_summary(args) -> int:
    report, warnings = summarize(manifest.load(args.manifest))
    print(report)
    for w in warnings:
        print(f"WARNING {w}")
    return 0


def cmd_download(args) -> int:
    entries = manifest.load(args.manifest)
    outcomes = download.download_all(
        entries, raw_root=args.raw_dir, cache_dir=args.cache_dir, min_interval=args.min_interval,
        max_bytes=args.max_mb * 1024 * 1024, max_pages=args.max_pages,
        only=set(args.ids) if args.ids else None,
    )
    manifest.save(entries, args.manifest)  # persists hashes, page counts and kinds from first ingest
    for o in outcomes:
        if o.status == "error":
            print(f"ERROR {o.id}: {o.message}")
    counts = {s: sum(o.status == s for o in outcomes) for s in ("downloaded", "skipped", "error")}
    print(", ".join(f"{n} {s}" for s, n in counts.items()))
    return 1 if counts["error"] else 0


def cmd_candidates(args) -> int:
    if args.source == "seeds" and not args.seed_file:
        raise SystemExit("candidates seeds needs --seed-file")
    if args.source in ("ntrs", "nist") and not args.query:
        raise SystemExit(f"candidates {args.source} needs --query")
    with httpx.Client(headers={"User-Agent": download.USER_AGENT}, timeout=60) as client:
        if args.source == "ntrs":
            found = ntrs.search(client, args.query, args.limit, args.tags)
        elif args.source == "nist":
            found = nist.search(client, args.query, args.limit, args.tags)
        elif args.source == "govdocs":
            found = govdocs.search(client, args.zip, args.limit, args.seed, args.tags, args.cache_dir)
        else:
            found = seeds.read(client, args.seed_file.read_text(), args.limit)
    name = args.name or (args.seed_file.stem if args.source == "seeds" else args.source)
    path = write_candidates(name, found, args.out_dir)
    for e in found:
        print(f"{e.id[:44]:<46}{e.rights:<18}{e.title[:60]}")
    print(f"{len(found)} candidates -> {path}")
    return 0


def cmd_add(args) -> int:
    """Copy explicitly named candidates into the manifest."""
    candidates = {e.id: e for e in manifest.load(args.candidates)}
    entries = manifest.load(args.manifest) if args.manifest.exists() else []
    existing = {e.id for e in entries}
    missing = [i for i in args.ids if i not in candidates]
    if missing:
        print(f"ERROR not in {args.candidates}: {', '.join(missing)}")
        return 1
    added = [candidates[i] for i in dict.fromkeys(args.ids) if i not in existing]
    for i in dict.fromkeys(args.ids):
        if i in existing:
            print(f"skip {i}: already in manifest")
    errors = manifest.validate(entries + added)
    if errors:
        print("\n".join(f"ERROR {e}" for e in errors))
        return 1
    manifest.save(entries + added, args.manifest)
    print(f"added {len(added)}, manifest now has {len(entries) + len(added)} entries")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="docparse.dataset")
    ap.add_argument("--manifest", type=Path, default=manifest.DEFAULT_PATH)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check the manifest")
    p.add_argument("--verified", action="store_true", help="also require kind, pages and sha256")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("summary", help="counts per group, kind and tag, with warnings")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("download", help="download and verify all documents of the manifest")
    p.add_argument("ids", nargs="*", help="only these ids")
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--cache-dir", type=Path, default=download.CACHE_DIR)
    p.add_argument("--min-interval", type=float, default=download.DEFAULT_MIN_INTERVAL)
    p.add_argument("--max-mb", type=int, default=download.DEFAULT_MAX_BYTES // (1024 * 1024))
    p.add_argument("--max-pages", type=int, default=download.DEFAULT_MAX_PAGES)
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("candidates", help="search a source and write candidates (not yet in the manifest)")
    p.add_argument("source", choices=["ntrs", "nist", "seeds", "govdocs"])
    p.add_argument("--query", help="search text (ntrs, nist)")
    p.add_argument("--seed-file", type=Path, help="seed list (seeds)")
    p.add_argument("--limit", type=int, default=25, help="max candidates (govdocs: sample size)")
    p.add_argument("--zip", default="000", help="govdocs1 zip package name, e.g. 000")
    p.add_argument("--seed", type=int, default=1, help="random seed for the govdocs sample")
    p.add_argument("--cache-dir", type=Path, default=download.CACHE_DIR)
    p.add_argument("--tags", default="", help="content tags for all results, ';'-separated")
    p.add_argument("--name", help="candidates file name (default: the source), to keep several searches apart")
    p.add_argument("--out-dir", type=Path, default=CANDIDATES_DIR)
    p.set_defaults(func=cmd_candidates)

    p = sub.add_parser("add", help="add the named candidates to the manifest")
    p.add_argument("candidates", type=Path, help="candidates CSV from `candidates`")
    p.add_argument("ids", nargs="+", help="candidate ids to add (no wildcard on purpose)")
    p.set_defaults(func=cmd_add)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
