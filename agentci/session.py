"""Read the child run's own session record — the only trustworthy witness.

The harness does not parse the model's prose to decide whether the run was fine.
After the child exits it opens the profile's ``state.db`` read-only and pulls the
session row that belongs to the throwaway workspace: tokens, tool names, model,
and the final assistant message.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .paths import state_db

COLUMNS = (
    "id, model, cwd, started_at, ended_at, input_tokens, output_tokens, "
    "cache_read_tokens, tool_names, tool_call_count, estimated_cost_usd, source"
)


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{state_db().as_posix()}?mode=ro", uri=True, timeout=10)


def find(cwd: str, since: float, max_wait: float = 15.0) -> dict:
    """Newest session whose cwd is this workspace and which started after ``since``."""
    import time

    target = str(Path(cwd).resolve())
    deadline = time.time() + max_wait
    row = None
    while time.time() < deadline:
        try:
            with _connect() as conn:
                row = conn.execute(
                    f"select {COLUMNS} from sessions where cwd = ? and started_at >= ? "
                    "order by started_at desc limit 1",
                    (target, since),
                ).fetchone()
        except sqlite3.Error:
            row = None
        if row:
            break
        time.sleep(0.5)

    if not row:
        # Windows may record the path with different separators; fall back to a
        # time-only match rather than silently reporting zero tokens.
        try:
            with _connect() as conn:
                row = conn.execute(
                    f"select {COLUMNS} from sessions where started_at >= ? order by started_at desc limit 1",
                    (since,),
                ).fetchone()
        except sqlite3.Error:
            return {}

    if not row:
        return {}

    keys = [c.strip() for c in COLUMNS.split(",")]
    data = dict(zip(keys, row))
    data["tool_list"] = tools_used(data["id"])
    data["answer"] = final_answer(data["id"])
    return data


def tools_used(session_id: str) -> list[str]:
    """Distinct tool names, taken from the message rows (``tool_name`` column) —
    the sessions table only carries an opaque hash, not the names."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "select distinct tool_name from messages where session_id = ? and tool_name is not null",
                (session_id,),
            ).fetchall()
    except sqlite3.Error:
        return []
    names = [str(r[0]) for r in rows if r[0]]
    if names:
        return names
    return sorted({call["name"] for call in tool_calls(session_id) if call.get("name")})


def final_answer(session_id: str) -> str:
    try:
        with _connect() as conn:
            rows = conn.execute(
                "select role, content, tool_name from messages where session_id = ? "
                "order by id desc limit 40",
                (session_id,),
            ).fetchall()
    except sqlite3.Error:
        return ""
    for role, content, tool_name in rows:
        if role == "assistant" and content and not tool_name:
            return str(content)
    return ""


def tool_calls(session_id: str) -> list[dict]:
    """Every tool call in order, with the tool that produced each result."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "select tool_name, tool_calls, content from messages where session_id = ? order by id",
                (session_id,),
            ).fetchall()
    except sqlite3.Error:
        return []
    out: list[dict] = []
    for tool_name, calls, content in rows:
        if calls:
            try:
                for call in json.loads(calls):
                    fn = (call or {}).get("function") or {}
                    out.append({"name": fn.get("name") or "", "args": fn.get("arguments") or ""})
            except (json.JSONDecodeError, TypeError):
                continue
        if tool_name:
            out.append({"name": tool_name, "result": str(content or "")[:400]})
    return out
