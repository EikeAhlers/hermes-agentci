"""Unit tests — no model calls, no network, no real Hermes runs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agentci import asserts, report, suite, tools  # noqa: E402


def write_suite(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "agentci.toml"
    path.write_text(body, encoding="utf-8")
    return path


GOOD = """
name = "smoke"
toolsets = "file"
[[cases]]
id = "one"
prompt = "do it"
workspace = "fix"
expect = [ { file_exists = "x.txt" } ]
"""


def test_load_rejects_missing_expect(tmp_path):
    (tmp_path / "fix").mkdir()
    path = write_suite(tmp_path, 'name="x"\n[[cases]]\nid="a"\nprompt="p"\nexpect = []\n')
    with pytest.raises(suite.SuiteError, match="at least one"):
        suite.load(path)


def test_load_rejects_unknown_assertion(tmp_path):
    (tmp_path / "fix").mkdir()
    path = write_suite(tmp_path, GOOD.replace("file_exists", "file_exists_typo"))
    with pytest.raises(suite.SuiteError, match="unknown assertion"):
        suite.load(path)


def test_load_rejects_duplicate_ids(tmp_path):
    (tmp_path / "fix").mkdir()
    body = GOOD + GOOD.replace('id = "one"', 'id = "one"').split("[[cases]]")[1]
    path = write_suite(tmp_path, body)
    with pytest.raises(suite.SuiteError, match="duplicate"):
        suite.load(path)


def test_load_resolves_workspace(tmp_path):
    (tmp_path / "fix").mkdir()
    path = write_suite(tmp_path, GOOD)
    loaded = suite.load(path)
    assert loaded.cases[0].workspace == str((tmp_path / "fix").resolve())
    assert loaded.toolsets == "file"


def test_load_rejects_missing_workspace(tmp_path):
    path = write_suite(tmp_path, GOOD)
    with pytest.raises(suite.SuiteError, match="not a directory"):
        suite.load(path)


def make_obs(tmp_path: Path, **kwargs) -> asserts.Observation:
    (tmp_path / "hello.txt").write_text("hallo welt", encoding="utf-8")
    (tmp_path / "keep.md").write_text("untouched", encoding="utf-8")
    return asserts.Observation(workspace=tmp_path, answer="Hallo Welt", **kwargs)


def test_outcome_assertions(tmp_path):
    obs = make_obs(tmp_path, tools=["terminal"], tokens_in=900, tokens_out=100, duration_s=12.0, exit_code=0)
    checks = asserts.run_expect(
        [
            {"file_exists": "hello.txt"},
            {"file_contains": ["hello.txt", "hallo"]},
            {"answer_contains": "hallo"},
            {"tool_used": "terminal"},
            {"tool_not_used": "write_file"},
            {"max_tokens": 2000},
            {"max_duration_s": 20},
            {"exit_code": 0},
            {"command": ["test -f hello.txt"]},
        ],
        obs,
    )
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]


def test_failing_assertion_reports_detail(tmp_path):
    obs = make_obs(tmp_path)
    checks = asserts.run_expect([{"file_contains": ["hello.txt", "tschuess"]}], obs)
    assert checks[0]["ok"] is False
    assert "does not contain" in checks[0]["detail"]


def test_file_unchanged_detects_edit(tmp_path):
    obs = make_obs(tmp_path)
    obs.before = {"keep.md": asserts._hash(tmp_path / "keep.md")}
    (tmp_path / "keep.md").write_text("changed", encoding="utf-8")
    ok, detail = asserts.check_file_unchanged(obs, "keep.md")
    assert ok is False and "changed" in detail


def test_assertion_never_crashes_run(tmp_path):
    obs = make_obs(tmp_path)
    checks = asserts.run_expect([{"file_contains": "not-a-pair"}], obs)
    assert checks[0]["ok"] is False


def test_summary_and_compare():
    current = {
        "cases": [
            {"id": "a", "ok": False, "tokens": 300, "checks": []},
            {"id": "b", "ok": True, "tokens": 100, "checks": []},
        ]
    }
    base = {"cases": [{"id": "a", "ok": True, "tokens": 200}, {"id": "c", "ok": True, "tokens": 50}]}
    summary = report.summarize(current["cases"])
    assert summary["failed"] == 1 and summary["tokens"] == 400
    diff = {d["id"]: d for d in report.compare(current, base)}
    assert diff["a"]["change"] == "regression" and diff["a"]["tokens_delta"] == 100
    assert diff["b"]["change"] == "new"
    assert "regression" in report.compare_table(report.compare(current, base))


def test_html_report_contains_checks():
    run = {
        "run_id": "r1",
        "suite": "smoke",
        "started": "now",
        "cases": [{"id": "a", "ok": False, "tokens": 5, "duration_s": 1.0,
                   "checks": [{"assert": "file_exists", "ok": False, "detail": "missing"}], "answer": ""}],
        "summary": {"total": 1, "passed": 0, "failed": 1, "tokens": 5, "duration_s": 1.0, "cost_usd": 0.0},
    }
    html = report.html_report(run)
    assert "smoke" in html and "missing" in html and "0/1 passed" in html


def test_init_is_idempotent(tmp_path):
    target = tmp_path / "agentci.toml"
    assert tools.init_suite(str(target))["ok"] is True
    assert tools.init_suite(str(target))["ok"] is False
    assert tools.init_suite(str(target), force=True)["ok"] is True
    assert (tmp_path / "fixture" / "notes.md").exists()
    suite.load(target)  # template must be valid


def test_run_suite_reports_suite_errors_cleanly():
    result = tools.run_suite("does-not-exist.toml")
    assert result["ok"] is False and "not found" in result["error"]
