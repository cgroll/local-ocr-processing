"""CLI: uv run python -m docparse.models {list,check,smoke}"""
import argparse
import sys
from pathlib import Path

from .registry import DEFAULT_CONFIG, Registry, RegistryError


def cmd_list(args, registry: Registry) -> int:
    print(f"{'key':<10} {'device':<6} {'vram_mb':>7}  {'model':<26} task")
    for s in registry.specs():
        print(f"{s.key:<10} {s.device:<6} {s.vram_mb:>7}  {s.name:<26} {s.task}")
    b = registry.budget
    print(f"budget: {b.total_mb} MB total - {b.reserve_mb} MB reserve = {b.usable_mb} MB usable")
    return 0


def cmd_check(args, registry: Registry) -> int:
    fit = registry.fits(args.keys)
    print(f"{' + '.join(args.keys)}: {fit}")
    return 0 if fit.ok else 1


def cmd_smoke(args, registry: Registry) -> int:
    from .smoke import make_sample, run_smoke

    keys = args.keys or registry.keys()
    for k in keys:
        registry.get(k)
    results = run_smoke(registry, keys, make_sample(args.raw_dir))
    print(f"{'key':<10} {'status':<6} {'load_s':>7} {'infer_s':>8} {'peak_mb':>8} {'residual_mb':>11}  detail")
    for r in results:
        residual = "-" if r.residual_mb is None else r.residual_mb
        print(f"{r.key:<10} {'ok' if r.ok else 'FAIL':<6} {r.load_s:>7.1f} {r.infer_s:>8.1f} {r.peak_mb:>8} {residual:>11}  {r.detail}")
    return 0 if all(r.ok for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docparse.models")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show the registry").set_defaults(func=cmd_list)
    p = sub.add_parser("check", help="does a set of models fit the VRAM budget together")
    p.add_argument("keys", nargs="+")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("smoke", help="load each model in turn and run one tiny inference")
    p.add_argument("keys", nargs="*")
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.set_defaults(func=cmd_smoke)
    args = parser.parse_args(argv)
    try:
        return args.func(args, Registry.load(args.config))
    except RegistryError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
