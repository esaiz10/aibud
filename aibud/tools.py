from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from .config import BASE_DIR


EventLogger = Callable[[str, str, dict[str, Any] | None], None]


class ToolRegistry:
    def __init__(self, logger: EventLogger):
        self._logger = logger

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = BASE_DIR / path
        return path.resolve()

    def list_files(self, path: str = ".") -> dict[str, Any]:
        target = self._resolve_path(path)
        self._logger("tool_call", "list_files", {"path": str(target)})
        if not target.exists():
            return {"ok": False, "error": f"{target} does not exist"}
        items = []
        for child in sorted(target.iterdir(), key=lambda item: item.name.lower())[:200]:
            items.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "kind": "dir" if child.is_dir() else "file",
                }
            )
        return {"ok": True, "items": items}

    def read_file(self, path: str, limit: int = 4000) -> dict[str, Any]:
        target = self._resolve_path(path)
        self._logger("tool_call", "read_file", {"path": str(target), "limit": limit})
        if not target.exists():
            return {"ok": False, "error": f"{target} does not exist"}
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "content": content[:limit], "truncated": len(content) > limit}

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        target = self._resolve_path(path)
        self._logger("tool_call", "write_file", {"path": str(target), "size": len(content)})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(target)}

    def run_shell(self, command: str, cwd: str | None = None, timeout: int = 20) -> dict[str, Any]:
        working_dir = self._resolve_path(cwd or str(BASE_DIR))
        self._logger("tool_call", "run_shell", {"command": command, "cwd": str(working_dir)})
        completed = subprocess.run(
            command,
            cwd=working_dir,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "command": command,
            "cwd": str(working_dir),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }

    def fetch_web(self, url: str) -> dict[str, Any]:
        self._logger("tool_call", "fetch_web", {"url": url})
        request = Request(url, headers={"User-Agent": "AiBud/0.1"})
        with urlopen(request, timeout=10) as response:
            body = response.read(4000).decode("utf-8", errors="replace")
        return {"ok": True, "url": url, "body": body}

    def describe(self) -> list[dict[str, Any]]:
        return [
            {"name": "list_files", "description": "List files in a directory."},
            {"name": "read_file", "description": "Read a local text file."},
            {"name": "write_file", "description": "Write a local text file."},
            {"name": "run_shell", "description": "Run a local shell command."},
            {"name": "fetch_web", "description": "Fetch a web page with urllib."},
        ]

    def dump_json(self) -> str:
        return json.dumps(self.describe(), indent=2)
