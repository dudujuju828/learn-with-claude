"""Optional Excalidraw diagram support for the tutor.

The tutor persona can be given one MCP tool — ``create_diagram`` from the
`excalidraw-skills <https://github.com/dudujuju828/excalidraw_skills>`_ server —
so that when a picture genuinely beats words (workflows, multi-part structures)
it draws one into the user's Obsidian vault.

Diagrams are enabled when both of these resolve:

* a vault path — ``--vault`` or ``EXCALIDRAW_VAULT_PATH`` / ``OBSIDIAN_VAULT_PATH``
  (the same variables the MCP server itself reads), and
* the server itself — ``npm install -g excalidraw-skills``, or point
  ``EXCALIDRAW_MCP_ENTRY`` at a checkout's ``dist/index.js``.

Otherwise the tutor falls back to pure text.

Note: the server must be spawned as ``node <entry.js>`` directly. Spawning via
``npx`` looks equivalent but is too slow for the claude CLI's MCP health check
on Windows, and the server silently fails to attach.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

# Fully-qualified tool name as claude-code exposes it: mcp__<server>__<tool>.
DIAGRAM_TOOL = "mcp__excalidraw__create_diagram"

INSTALL_HINT = "npm install -g excalidraw-skills"


def resolve_vault(explicit: str | None = None) -> str | None:
    """Vault directory from --vault or the excalidraw-skills env vars."""
    candidate = (
        explicit
        or os.environ.get("EXCALIDRAW_VAULT_PATH")
        or os.environ.get("OBSIDIAN_VAULT_PATH")
    )
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    return str(path.resolve()) if path.is_dir() else None


@lru_cache(maxsize=1)
def server_entry() -> str | None:
    """Path to the excalidraw-skills server script, or None if not installed."""
    override = os.environ.get("EXCALIDRAW_MCP_ENTRY")
    if override:
        path = Path(override).expanduser()
        return str(path) if path.is_file() else None

    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        proc = subprocess.run(
            [npm, "root", "-g"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    entry = Path(proc.stdout.strip()) / "excalidraw-skills" / "dist" / "index.js"
    return str(entry) if entry.is_file() else None


def excalidraw_mcp_config(vault: str) -> dict | None:
    """MCP config for the tutor session, or None if the server isn't installed."""
    entry = server_entry()
    if entry is None:
        return None
    return {
        "mcpServers": {
            "excalidraw": {
                "command": shutil.which("node") or "node",
                "args": [entry],
                "env": {
                    "EXCALIDRAW_VAULT_PATH": vault,
                    "EXCALIDRAW_FOLDER": os.environ.get(
                        "EXCALIDRAW_FOLDER", "Excalidraw/Lessons"
                    ),
                },
            }
        }
    }
