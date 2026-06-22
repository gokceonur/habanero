"""Tool usage logging — appends to ~/.habanero/tool_usage.jsonl (legacy ~/.pepper) on every MCP tool call."""

from __future__ import annotations

import json
import os
import time
import uuid

from .pepper_common import habanero_home_dir

_SESSION_ID = uuid.uuid4().hex[:12]
# Append to the canonical ~/.habanero log, or the legacy ~/.pepper one if it exists.
_USAGE_PATH = habanero_home_dir("tool_usage.jsonl")
_USAGE_DIR = os.path.dirname(_USAGE_PATH)


def log_tool_call(tool_name: str) -> None:
    """Append one line to the usage log. Fire-and-forget, never raises."""
    try:
        os.makedirs(_USAGE_DIR, exist_ok=True)
        entry = json.dumps(
            {"tool": tool_name, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": _SESSION_ID},
            separators=(",", ":"),
        )
        with open(_USAGE_PATH, "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass  # Never block MCP on logging failures


def get_usage_summary(days: int = 30) -> dict:
    """Read the usage log and return tool counts for the last N days."""
    cutoff = time.time() - days * 86400
    counts: dict[str, int] = {}
    sessions: set[str] = set()
    total = 0
    try:
        with open(_USAGE_PATH) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    ts = time.mktime(time.strptime(entry["ts"], "%Y-%m-%dT%H:%M:%S"))
                    if ts >= cutoff:
                        tool = entry["tool"]
                        counts[tool] = counts.get(tool, 0) + 1
                        sessions.add(entry.get("session", ""))
                        total += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except FileNotFoundError:
        pass
    return {
        "days": days,
        "total_calls": total,
        "sessions": len(sessions),
        "tools": dict(sorted(counts.items(), key=lambda x: -x[1])),
    }
