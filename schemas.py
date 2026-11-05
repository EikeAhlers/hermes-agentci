"""JSON schemas for the agentci tools (strict objects, no free-form blobs)."""

RUN = {
    "type": "object",
    "properties": {
        "suite": {"type": "string", "description": "Path to the suite file (.toml)."},
        "only": {"type": "string", "description": "Comma-separated case ids to run (default: all)."},
        "parallel": {"type": "integer", "description": "Concurrent runs, 1-4.", "minimum": 1, "maximum": 4},
        "model": {"type": "string", "description": "Override the model for every case (e.g. deepseek/deepseek-v4.1-flash-fast)."},
        "keep_workspaces": {"type": "boolean", "description": "Keep the throwaway workspaces for inspection."},
        "timeout_s": {"type": "integer", "description": "Per-case timeout in seconds.", "minimum": 10},
        "compare_previous": {"type": "boolean", "description": "Diff against the previous run of this suite."},
    },
    "required": ["suite"],
    "additionalProperties": False,
}

MATRIX = {
    "type": "object",
    "properties": {
        "suite": {"type": "string"},
        "models": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "parallel": {"type": "integer", "minimum": 1, "maximum": 4},
    },
    "required": ["suite", "models"],
    "additionalProperties": False,
}

REPORT = {
    "type": "object",
    "properties": {"run_id": {"type": "string", "description": "Run id (default: the latest run)."}},
    "additionalProperties": False,
}

INIT = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Where to write the starter suite."},
        "force": {"type": "boolean", "description": "Overwrite an existing file."},
    },
    "additionalProperties": False,
}
