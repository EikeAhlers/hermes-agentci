"""Suite files: a small, explicit TOML format.

A suite is a list of prompt cases plus the assertions each case must satisfy::

    name = "smoke"
    toolsets = "terminal,file"
    timeout_s = 180

    [[cases]]
    id = "creates-file"
    prompt = "Create hello.txt containing exactly: hallo"
    expect = [
      { file_contains = ["hello.txt", "hallo"] },
      { tool_used = "write_file" },
      { max_tokens = 6000 },
    ]

Nothing is inferred: a case without assertions is rejected, so a suite can never
be green by accident.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .asserts import ASSERT_NAMES

DEFAULT_TIMEOUT = 240


class SuiteError(ValueError):
    pass


@dataclass
class Case:
    id: str
    prompt: str
    expect: list[dict]
    workspace: str | None = None
    toolsets: str | None = None
    model: str | None = None

    def toolset(self, default: str) -> str:
        return self.toolsets or default


@dataclass
class Suite:
    path: Path
    name: str
    cases: list[Case]
    toolsets: str = "terminal,file"
    timeout_s: int = DEFAULT_TIMEOUT
    default_expect: list[dict] = field(default_factory=list)

    @property
    def root(self) -> Path:
        return self.path.parent


def _check_expect(expect: list[dict], where: str) -> None:
    if not isinstance(expect, list) or not expect:
        raise SuiteError(f"{where}: needs at least one entry in expect")
    for entry in expect:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise SuiteError(f"{where}: each expect entry must hold exactly one assertion, got {entry!r}")
        name = next(iter(entry))
        if name not in ASSERT_NAMES:
            raise SuiteError(
                f"{where}: unknown assertion {name!r} (known: {', '.join(sorted(ASSERT_NAMES))})"
            )


def load(path: str | Path) -> Suite:
    path = Path(path)
    if not path.exists():
        raise SuiteError(f"suite not found: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SuiteError(f"{path}: invalid TOML — {exc}") from exc

    raw_cases = data.get("cases") or []
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SuiteError(f"{path}: no [[cases]] defined")

    cases: list[Case] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases, start=1):
        case_id = str(raw.get("id") or f"case-{index}")
        if case_id in seen:
            raise SuiteError(f"{path}: duplicate case id {case_id!r}")
        seen.add(case_id)
        prompt = raw.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise SuiteError(f"{path}: case {case_id!r} has no prompt")
        expect = raw.get("expect") or data.get("expect") or []
        _check_expect(expect, f"{path}: case {case_id!r}")
        workspace = raw.get("workspace")
        if workspace is not None:
            fixture = (path.parent / workspace).resolve()
            if not fixture.is_dir():
                raise SuiteError(f"{path}: case {case_id!r} workspace {workspace!r} is not a directory")
            workspace = str(fixture)
        cases.append(
            Case(
                id=case_id,
                prompt=prompt,
                expect=expect,
                workspace=workspace,
                toolsets=raw.get("toolsets"),
                model=raw.get("model"),
            )
        )

    return Suite(
        path=path,
        name=str(data.get("name") or path.stem),
        cases=cases,
        toolsets=str(data.get("toolsets") or "terminal,file"),
        timeout_s=int(data.get("timeout_s") or DEFAULT_TIMEOUT),
    )
