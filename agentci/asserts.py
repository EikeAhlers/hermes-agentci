"""Assertions — every check returns (ok, human detail).

The rule of this module: a check may only look at things that are *observable
after the run* — the session record (tools, tokens), the workspace bytes, the
child's exit code. Nothing is inferred from the model's own claims, because a
model that says "I created hello.txt" is not evidence that hello.txt exists.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Observation:
    """What actually happened during one case run."""

    answer: str = ""
    tools: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    duration_s: float = 0.0
    exit_code: int = 0
    stdout: str = ""
    workspace: Path | None = None
    before: dict[str, str] = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(obs: Observation) -> dict[str, str]:
    if obs.workspace is None:
        return {}
    out: dict[str, str] = {}
    for path in obs.workspace.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            out[path.relative_to(obs.workspace).as_posix()] = _hash(path)
    return out


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def check_answer_contains(obs: Observation, value) -> tuple[bool, str]:
    needles = [str(v) for v in _as_list(value)]
    missing = [n for n in needles if n.lower() not in obs.answer.lower()]
    if missing:
        return False, f"answer is missing {missing!r}"
    return True, f"answer contains {needles!r}"


def check_answer_not_contains(obs: Observation, value) -> tuple[bool, str]:
    needles = [str(v) for v in _as_list(value)]
    found = [n for n in needles if n.lower() in obs.answer.lower()]
    if found:
        return False, f"answer contains forbidden {found!r}"
    return True, f"answer free of {needles!r}"


def check_answer_matches(obs: Observation, value) -> tuple[bool, str]:
    pattern = str(value)
    if re.search(pattern, obs.answer, re.MULTILINE):
        return True, f"answer matches /{pattern}/"
    return False, f"answer does not match /{pattern}/"


def _path(obs: Observation, name) -> Path:
    if obs.workspace is None:
        raise AssertionError("no workspace for this case")
    return obs.workspace / str(name)


def check_file_exists(obs: Observation, value) -> tuple[bool, str]:
    names = [str(v) for v in _as_list(value)]
    missing = [n for n in names if not _path(obs, n).exists()]
    if missing:
        return False, f"missing file(s): {missing}"
    return True, f"present: {names}"


def check_file_absent(obs: Observation, value) -> tuple[bool, str]:
    names = [str(v) for v in _as_list(value)]
    present = [n for n in names if _path(obs, n).exists()]
    if present:
        return False, f"file(s) should not exist: {present}"
    return True, f"absent as expected: {names}"


def check_file_contains(obs: Observation, value) -> tuple[bool, str]:
    pairs = value if isinstance(value, list) and value and isinstance(value[0], list) else [value]
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False, f"file_contains needs [path, text], got {pair!r}"
        name, needle = str(pair[0]), str(pair[1])
        path = _path(obs, name)
        if not path.exists():
            return False, f"{name} does not exist"
        body = path.read_text(encoding="utf-8", errors="replace")
        if needle.lower() not in body.lower():
            return False, f"{name} does not contain {needle!r}"
    return True, f"content verified: {pairs!r}"


def check_file_unchanged(obs: Observation, value) -> tuple[bool, str]:
    names = [str(v) for v in _as_list(value)] or list(obs.before)
    changed = []
    for name in names:
        path = _path(obs, name)
        was = obs.before.get(name)
        now = _hash(path) if path.exists() else None
        if was != now:
            changed.append(name)
    if changed:
        return False, f"file(s) changed: {changed}"
    return True, f"untouched: {names}"


def check_file_changed(obs: Observation, value) -> tuple[bool, str]:
    names = [str(v) for v in _as_list(value)]
    same = []
    for name in names:
        path = _path(obs, name)
        was = obs.before.get(name)
        now = _hash(path) if path.exists() else None
        if was == now:
            same.append(name)
    if same:
        return False, f"file(s) unchanged but should differ: {same}"
    return True, f"changed: {names}"


def check_tool_used(obs: Observation, value) -> tuple[bool, str]:
    names = [str(v) for v in _as_list(value)]
    missing = [n for n in names if n not in obs.tools]
    if missing:
        return False, f"tool(s) never called: {missing} (used: {obs.tools})"
    return True, f"called: {names}"


def check_tool_not_used(obs: Observation, value) -> tuple[bool, str]:
    names = [str(v) for v in _as_list(value)]
    used = [n for n in names if n in obs.tools]
    if used:
        return False, f"forbidden tool(s) called: {used}"
    return True, f"not called: {names}"


def check_max_tokens(obs: Observation, value) -> tuple[bool, str]:
    limit = int(value)
    if obs.tokens > limit:
        return False, f"{obs.tokens:,} tokens exceeds budget {limit:,}"
    return True, f"{obs.tokens:,} tokens within {limit:,}"


def check_min_tokens(obs: Observation, value) -> tuple[bool, str]:
    limit = int(value)
    if obs.tokens < limit:
        return False, f"{obs.tokens:,} tokens below floor {limit:,}"
    return True, f"{obs.tokens:,} tokens at least {limit:,}"


def check_max_duration_s(obs: Observation, value) -> tuple[bool, str]:
    limit = float(value)
    if obs.duration_s > limit:
        return False, f"{obs.duration_s:.1f}s over limit {limit:.1f}s"
    return True, f"{obs.duration_s:.1f}s within {limit:.1f}s"


def check_exit_code(obs: Observation, value) -> tuple[bool, str]:
    want = int(value)
    if obs.exit_code != want:
        return False, f"exit {obs.exit_code} != {want}"
    return True, f"exit {want}"


def check_command(obs: Observation, value) -> tuple[bool, str]:
    if isinstance(value, (list, tuple)):
        command, want = str(value[0]), int(value[1]) if len(value) > 1 else 0
    else:
        command, want = str(value), 0
    if obs.workspace is None:
        return False, "command assertion needs a workspace"
    proc = subprocess.run(command, shell=True, cwd=obs.workspace, capture_output=True, text=True, timeout=120)
    if proc.returncode != want:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        return False, f"`{command}` exited {proc.returncode} (want {want}): {tail}"
    return True, f"`{command}` exited {want}"


ASSERTS = {
    "answer_contains": check_answer_contains,
    "answer_not_contains": check_answer_not_contains,
    "answer_matches": check_answer_matches,
    "file_exists": check_file_exists,
    "file_absent": check_file_absent,
    "file_contains": check_file_contains,
    "file_unchanged": check_file_unchanged,
    "file_changed": check_file_changed,
    "tool_used": check_tool_used,
    "tool_not_used": check_tool_not_used,
    "max_tokens": check_max_tokens,
    "min_tokens": check_min_tokens,
    "max_duration_s": check_max_duration_s,
    "exit_code": check_exit_code,
    "command": check_command,
}

ASSERT_NAMES = tuple(ASSERTS)


def run_expect(expect: list[dict], obs: Observation) -> list[dict]:
    results = []
    for entry in expect:
        name, value = next(iter(entry.items()))
        fn = ASSERTS.get(name)
        if fn is None:
            results.append({"assert": name, "ok": False, "detail": "unknown assertion"})
            continue
        try:
            ok, detail = fn(obs, value)
        except Exception as exc:  # assertion must never crash the run
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        results.append({"assert": name, "ok": bool(ok), "detail": detail, "value": value})
    return results
