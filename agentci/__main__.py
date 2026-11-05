"""CLI: CI-friendly entry point (exit code 1 on a failed case).

    python -m agentci run agentci.toml
    python -m agentci run agentci.toml --only smoke --parallel 4 --model deepseek/deepseek-v4.1-flash-fast
    python -m agentci matrix agentci.toml --models a,b
    python -m agentci report
    python -m agentci init agentci.toml
"""

from __future__ import annotations

import argparse
import json
import sys

from . import tools


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentci", description="Run agent tests like real tests.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a suite")
    run.add_argument("suite")
    run.add_argument("--only")
    run.add_argument("--parallel", type=int, default=3)
    run.add_argument("--model")
    run.add_argument("--timeout", type=int)
    run.add_argument("--keep", action="store_true", help="keep workspaces")
    run.add_argument("--no-baseline", action="store_true")
    run.add_argument("--json", action="store_true", help="machine-readable output")

    matrix = sub.add_parser("matrix", help="same suite, several models")
    matrix.add_argument("suite")
    matrix.add_argument("--models", required=True, help="comma-separated model ids")
    matrix.add_argument("--parallel", type=int, default=2)

    report = sub.add_parser("report", help="show the latest run")
    report.add_argument("run_id", nargs="?")

    init = sub.add_parser("init", help="write a starter suite")
    init.add_argument("path", nargs="?", default="agentci.toml")
    init.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "run":
        result = tools.run_suite(
            args.suite,
            only=args.only,
            parallel=args.parallel,
            model=args.model,
            timeout_s=args.timeout,
            keep_workspaces=args.keep,
            compare_previous=not args.no_baseline,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("error"):
            print(f"error: {result['error']}", file=sys.stderr)
        else:
            print(result["table"])
            if result.get("changes_table"):
                print(result["changes_table"])
            print(f"\nreport: {result['report_html']}")
        return 0 if result.get("ok") else 1

    if args.command == "matrix":
        result = tools.matrix(args.suite, [m.strip() for m in args.models.split(",") if m.strip()],
                              parallel=args.parallel)
        print(result.get("error") or result["table"])
        return 0 if result.get("ok") else 1

    if args.command == "report":
        result = tools.show_report(args.run_id)
        print(result.get("error") or result["table"])
        return 0 if result.get("ok") else 1

    if args.command == "init":
        result = tools.init_suite(args.path, force=args.force)
        print(result.get("error") or f"suite written: {result['suite']} (fixture: {result['fixture']})")
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
