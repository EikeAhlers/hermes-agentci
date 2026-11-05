"""Run one case: throwaway workspace, one headless child, real observation."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from . import session
from .asserts import Observation, _files, run_expect
from .paths import runs_dir
from .suite import Case

STRIP_ENV = ("HERMES_SESSION", "HERMES_SESSION_ID", "HERMES_SESSION_NAME", "HERMES_TASK_ID")


def hermes_bin() -> str:
    for name in ("hermes", "hermes.exe", "hermes.cmd", "hermes.bat"):
        found = shutil.which(name)
        if found:
            return found
    return "hermes"


def clean_env() -> dict:
    env = dict(os.environ)
    for key in STRIP_ENV:
        env.pop(key, None)
    return env


def make_workspace(case: Case) -> Path:
    """Copy the fixture into a fresh directory under our runs folder."""
    root = Path(tempfile.mkdtemp(prefix=f"case-{case.id}-", dir=str(runs_dir())))
    if case.workspace:
        for item in Path(case.workspace).iterdir():
            if item.name in (".git", "__pycache__"):
                continue
            target = root / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
    return root


def build_command(case: Case, suite_toolsets: str, model: str | None) -> list[str]:
    cmd = [hermes_bin(), "-z", case.prompt, "--yolo", "-t", case.toolset(suite_toolsets)]
    chosen = model or case.model
    if chosen:
        cmd += ["-m", chosen]
    return cmd


def run_case(case: Case, suite_toolsets: str = "terminal,file", model: str | None = None,
             timeout_s: int = 240, tmp_home: str | None = None) -> dict:
    workspace = make_workspace(case)
    before = _files(Observation(workspace=workspace))
    env = clean_env()
    if tmp_home:
        env["HERMES_HOME"] = tmp_home
    started_wall = time.time()
    started = time.time()
    cmd = build_command(case, suite_toolsets, model)

    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            stdin=subprocess.DEVNULL,
        )
        stdout, stderr, code = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        code = 124
    duration = time.time() - started

    record = session.find(str(workspace), started_wall - 2)
    obs = Observation(
        answer=record.get("answer", "") if record else (stdout or "")[-4000:],
        tools=record.get("tool_list", []) if record else [],
        tokens_in=int(record.get("input_tokens") or 0) if record else 0,
        tokens_out=int(record.get("output_tokens") or 0) if record else 0,
        duration_s=round(duration, 2),
        exit_code=code,
        stdout=stdout[-4000:],
        workspace=workspace,
        before=before,
    )

    checks = run_expect(case.expect, obs)
    ok = all(c["ok"] for c in checks) and not timed_out
    return {
        "id": case.id,
        "ok": ok,
        "timed_out": timed_out,
        "checks": checks,
        "tokens_in": obs.tokens_in,
        "tokens_out": obs.tokens_out,
        "tokens": obs.tokens,
        "duration_s": obs.duration_s,
        "exit_code": code,
        "session_id": record.get("id", ""),
        "model": (record.get("model") or model or ""),
        "cost_usd": float(record.get("estimated_cost_usd") or 0.0),
        "tools": obs.tools,
        "workspace": str(workspace),
        "answer": obs.answer[:1200],
        "stderr": stderr[-800:],
    }


def cleanup(result: dict, keep: bool = False) -> None:
    if keep:
        return
    workspace = result.get("workspace")
    if workspace and Path(workspace).exists():
        shutil.rmtree(workspace, ignore_errors=True)


def run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def python_exe() -> str:
    return sys.executable
