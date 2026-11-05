"""agentci plugin entry point — four tools, no hooks, no core imports."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import schemas  # noqa: E402
from agentci import tools  # noqa: E402

TOOLSET = "agentci"


def register(ctx):
    for name, schema, handler in (
        ("agentci_run", schemas.RUN, tools.run_suite),
        ("agentci_matrix", schemas.MATRIX, tools.matrix),
        ("agentci_report", schemas.REPORT, tools.show_report),
        ("agentci_init", schemas.INIT, tools.init_suite),
    ):
        ctx.register_tool(name=name, toolset=TOOLSET, schema=schema, handler=handler)

    try:
        ctx.register_automation_blueprint(
            key="agentci-regression-suite",
            title="Agent regression suite",
            description=(
                "Run the agent's test suite nightly and report regressions with token deltas, "
                "so a prompt or model change cannot silently break behaviour."
            ),
            schedule_template="0 6 * * *",
            prompt_template=(
                "Run the agentci suite at <path to suite.toml> with agentci_run. If any case "
                "fails, report the failing case ids with their failed checks and the token "
                "delta against the previous run. Do not change the suite to make it pass."
            ),
        )
    except Exception:
        pass
