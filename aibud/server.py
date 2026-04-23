from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import STATIC_DIR


class AiBudHandler(BaseHTTPRequestHandler):
    runtime = None

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        mime, _ = mimetypes.guess_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(STATIC_DIR / "index.html")
            return
        if parsed.path.startswith("/static/"):
            self._send_file(STATIC_DIR / parsed.path.removeprefix("/static/"))
            return
        if parsed.path == "/api/overview":
            self._send_json({"ok": True, "overview": self.runtime.storage.overview()})
            return
        if parsed.path == "/api/projects":
            self._send_json({"ok": True, "projects": self.runtime.storage.list_projects()})
            return
        if parsed.path == "/api/tasks":
            self._send_json({"ok": True, "tasks": self.runtime.storage.list_tasks()})
            return
        if parsed.path == "/api/memories":
            self._send_json({"ok": True, "memories": self.runtime.storage.list_memories()})
            return
        if parsed.path == "/api/reports":
            self._send_json({"ok": True, "reports": self.runtime.storage.list_reports()})
            return
        if parsed.path == "/api/runs":
            self._send_json({"ok": True, "runs": self.runtime.storage.list_runs()})
            return
        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            run_id = query.get("run_id", [None])[0]
            payload = self.runtime.storage.list_events(int(run_id)) if run_id else self.runtime.storage.list_events()
            self._send_json({"ok": True, "events": payload})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._read_json()
        if parsed.path == "/api/ask":
            prompt = payload.get("prompt", "").strip()
            project_name = payload.get("project", "Inbox").strip() or "Inbox"
            mode = payload.get("mode", "auto").strip() or "auto"
            if not prompt:
                self._send_json({"ok": False, "error": "prompt is required"}, status=400)
                return
            outcome = self.runtime.run_prompt(prompt, project_name=project_name, requested_mode=mode)
            is_failed = outcome.run.get("status") == "failed"
            self._send_json(
                {
                    "ok": not is_failed,
                    "run": outcome.run,
                    "summary": outcome.summary,
                    "response": outcome.response,
                    "mode": outcome.mode,
                    "cache_hit": outcome.cache_hit,
                    "error": outcome.response if is_failed else "",
                },
                status=500 if is_failed else 200,
            )
            return
        if parsed.path == "/api/tasks":
            project = self.runtime.ensure_project(payload.get("project", "Inbox"))
            task = self.runtime.storage.create_task(
                project["id"],
                payload.get("title", "Untitled task"),
                details=payload.get("details", ""),
                status=payload.get("status", "queued"),
                priority=int(payload.get("priority", 3)),
            )
            self._send_json({"ok": True, "task": task})
            return
        if parsed.path == "/api/memories":
            memory = self.runtime.storage.add_memory(
                payload.get("kind", "note"),
                payload.get("title", "Untitled memory"),
                payload.get("content", ""),
            )
            self._send_json({"ok": True, "memory": memory})
            return
        self.send_error(HTTPStatus.NOT_FOUND)


def serve(runtime, host: str = "127.0.0.1", port: int = 8765) -> None:
    AiBudHandler.runtime = runtime
    server = ThreadingHTTPServer((host, port), AiBudHandler)
    print(f"AiBud web client listening at http://{host}:{port}")
    server.serve_forever()
