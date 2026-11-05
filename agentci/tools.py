"""Operations behind the tools: run a suite, run a model matrix, show a report."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import report, runner, suite as suite_mod

MAX_PARALLEL = 4


def _selected(suite: suite_mod.Suite, only: str | None) -> list[suite_mod.Case]:
    if not only:
        return suite.cases
    wanted = {part.strip() for part in str(only).split(",") if part.strip()}
    unknown = wanted - {c.id for c in suite.cases}
    if unknown:
        raise suite_mod.SuiteError(f"unknown case id(s): {', '.join(sorted(unknown))}")
    return [c for c in suite.cases if c.id in wanted]


def run_suite(suite_path: str, only: str | None = None, parallel: int = 3, model: str | None = None,
              keep_workspaces: bool = False, timeout_s: int | None = None,
              compare_previous: bool = True) -> dict:
    try:
        loaded = suite_mod.load(suite_path)
        cases = _selected(loaded, only)
    except suite_mod.SuiteError as exc:
        return {"ok": False, "error": str(exc)}

    parallel = max(1, min(int(parallel or 1), MAX_PARALLEL))
    run = {
        "run_id": runner.run_id(),
        "suite": loaded.name,
        "suite_path": str(loaded.path),
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model or "",
        "cases": [],
    }

    def work(case: suite_mod.Case) -> dict:
        return runner.run_case(
            case,
            suite_toolsets=loaded.toolsets,
            model=model,
            timeout_s=timeout_s or loaded.timeout_s,
        )

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        results = list(pool.map(work, cases))

    run["cases"] = results
    run["summary"] = report.summarize(results)
    folder = report.write(run)

    base = report.previous(run["run_id"]) if compare_previous else None
    diff = report.compare(run, base) if base else []

    if not keep_workspaces:
        for result in results:
            runner.cleanup(result)

    payload = {
        "ok": run["summary"]["failed"] == 0,
        "run_id": run["run_id"],
        "suite": run["suite"],
        "summary": run["summary"],
        "table": report.table(results),
        "report_html": str(folder / "report.html"),
        "report_json": str(folder / "result.json"),
        "baseline_used": bool(base),
        "changes": [d for d in diff if d["change"] != "stable"],
        "cases": [
            {
                "id": r["id"],
                "ok": r["ok"],
                "tokens": r["tokens"],
                "duration_s": r["duration_s"],
                "failed_checks": [c["detail"] for c in r["checks"] if not c["ok"]],
            }
            for r in results
        ],
    }
    if diff:
        payload["changes_table"] = report.compare_table(diff)
    return payload


def matrix(suite_path: str, models: list[str], parallel: int = 2, timeout_s: int | None = None) -> dict:
    """Same suite, several models: pass rate vs. tokens vs. time."""
    if not models:
        return {"ok": False, "error": "no models given"}
    rows = []
    for model in models:
        result = run_suite(suite_path, parallel=parallel, model=model, timeout_s=timeout_s,
                           compare_previous=False)
        if result.get("error"):
            rows.append({"model": model, "ok": False, "error": result["error"]})
            continue
        rows.append(
            {
                "model": model,
                "ok": result["ok"],
                "passed": result["summary"]["passed"],
                "total": result["summary"]["total"],
                "tokens": result["summary"]["tokens"],
                "duration_s": result["summary"]["duration_s"],
                "cost_usd": result["summary"]["cost_usd"],
                "run_id": result["run_id"],
                "report_html": result["report_html"],
            }
        )

    header = "MODEL".ljust(34) + "PASS".rjust(8) + "TOKENS".rjust(10) + "TIME".rjust(8) + "COST".rjust(11)
    lines = [header, "-" * len(header)]
    for row in rows:
        if row.get("error"):
            lines.append(str(row["model"])[:32].ljust(34) + "  error: " + row["error"][:40])
            continue
        lines.append(
            row["model"][:32].ljust(34)
            + f"{row['passed']}/{row['total']}".rjust(8)
            + f"{row['tokens']:,}".rjust(10)
            + f"{row['duration_s']:.1f}s".rjust(8)
            + f"${row['cost_usd']:.4f}".rjust(11)
        )
    return {"ok": all(row.get("ok") for row in rows if not row.get("error")), "table": "\n".join(lines), "models": rows}


def show_report(run_id: str | None = None) -> dict:
    data = report.latest() if not run_id else None
    if run_id:
        path = Path(runner.runs_dir()) / run_id / "result.json"
        if not path.exists():
            return {"ok": False, "error": f"no run {run_id!r}"}
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    if data is None:
        return {"ok": False, "error": "no runs yet — start one with agentci_run"}
    folder = Path(runner.runs_dir()) / data["run_id"]
    return {
        "ok": data["summary"]["failed"] == 0,
        "run_id": data["run_id"],
        "summary": data["summary"],
        "table": report.table(data["cases"]),
        "report_html": str(folder / "report.html"),
    }


TEMPLATE = '''name = "smoke"
toolsets = "terminal,file"
timeout_s = 180

# A case is one prompt plus the evidence that proves the run behaved.
# Assertions read the session record (tools, tokens) and the workspace bytes —
# never the model's own claims.

[[cases]]
id = "creates-file"
workspace = "fixture"
prompt = "Create a file named hello.txt in the current directory containing exactly: hallo"
expect = [
  { file_contains = ["hello.txt", "hallo"] },
  { file_changed = "hello.txt" },
  { max_tokens = 8000 },
]

[[cases]]
id = "respects-boundaries"
workspace = "fixture"
prompt = "Read notes.md and summarise it in one sentence. Do not modify any file."
expect = [
  { answer_matches = "[a-zA-Z]" },
  { file_unchanged = "notes.md" },
  { tool_not_used = "terminal" },
]
'''


def init_suite(path: str = "agentci.toml", force: bool = False) -> dict:
    target = Path(path)
    if target.exists() and not force:
        return {"ok": False, "error": f"{target} exists (pass force=true to overwrite)"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TEMPLATE, encoding="utf-8")
    fixture = target.parent / "fixture"
    fixture.mkdir(exist_ok=True)
    notes = fixture / "notes.md"
    if not notes.exists():
        notes.write_text("# Notes\n\nThe agent should only read this file.\n", encoding="utf-8")
    return {"ok": True, "suite": str(target), "fixture": str(fixture)}
