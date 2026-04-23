from __future__ import annotations

import json
import sqlite3
import threading
from hashlib import sha256
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._init_db()
        self._migrate_existing_data()

    @contextmanager
    def _connect(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    priority INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 3,
                    mode TEXT NOT NULL DEFAULT 'normal',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    mode TEXT NOT NULL DEFAULT 'normal',
                    summary TEXT NOT NULL DEFAULT '',
                    response TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
                CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
                CREATE TABLE IF NOT EXISTS response_cache (
                    key TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    provider_name TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    hits INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            self._ensure_column(conn, "tasks", "mode", "TEXT NOT NULL DEFAULT 'normal'")
            self._ensure_column(conn, "runs", "mode", "TEXT NOT NULL DEFAULT 'normal'")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _migrate_existing_data(self) -> None:
        with self._lock, self._connect() as conn:
            self._merge_duplicate_projects(conn)
            self._merge_duplicate_active_tasks(conn)

    def _merge_duplicate_projects(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY id ASC"
        ).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            key = str(row["name"]).strip().lower()
            grouped.setdefault(key, []).append(row)

        for _, group in grouped.items():
            if not group:
                continue
            canonical = group[0]
            canonical_name = self._normalize_project_name(str(canonical["name"]))
            conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (canonical_name, utc_now(), canonical["id"]),
            )
            for duplicate in group[1:]:
                conn.execute(
                    "UPDATE tasks SET project_id = ? WHERE project_id = ?",
                    (canonical["id"], duplicate["id"]),
                )
                conn.execute(
                    "UPDATE runs SET project_id = ? WHERE project_id = ?",
                    (canonical["id"], duplicate["id"]),
                )
                conn.execute("DELETE FROM projects WHERE id = ?", (duplicate["id"],))

    def _merge_duplicate_active_tasks(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE status IN ('queued', 'in_progress')
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        grouped: dict[tuple[int, str], list[sqlite3.Row]] = {}
        for row in rows:
            key = (int(row["project_id"]), self._normalize_task_title(str(row["title"])).lower())
            grouped.setdefault(key, []).append(row)

        for (_, _), group in grouped.items():
            if len(group) < 2:
                continue
            keeper = group[0]
            for duplicate in group[1:]:
                merged_details = self._normalize_task_title(str(duplicate["details"] or ""))
                keeper_details = self._normalize_task_title(str(keeper["details"] or ""))
                combined_details = keeper_details or merged_details
                if merged_details and merged_details not in combined_details:
                    combined_details = f"{combined_details}\n\nMerged duplicate note: {merged_details}".strip()
                conn.execute(
                    """
                    UPDATE tasks
                    SET details = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (combined_details, utc_now(), keeper["id"]),
                )
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'merged', updated_at = ?
                    WHERE id = ?
                    """,
                    (utc_now(), duplicate["id"]),
                )

    def _row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    def _rows_to_dicts(self, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [self._row_to_dict(row) for row in rows if row is not None]

    def _normalize_project_name(self, name: str) -> str:
        text = " ".join((name or "").split()).strip()
        return text.title() if text else "Inbox"

    def _normalize_task_title(self, title: str) -> str:
        return " ".join((title or "").split()).strip()

    def ensure_project(self, name: str, description: str = "") -> dict[str, Any]:
        normalized_name = self._normalize_project_name(name)
        now = utc_now()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE lower(name) = lower(?)",
                (normalized_name,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO projects(name, description, created_at, updated_at)
                    VALUES(?, ?, ?, ?)
                    """,
                    (normalized_name, description, now, now),
                )
            else:
                conn.execute(
                    "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                    (normalized_name, now, row["id"]),
                )
            row = conn.execute("SELECT * FROM projects WHERE lower(name) = lower(?)", (normalized_name,)).fetchone()
        return self._row_to_dict(row) or {}

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY priority ASC, updated_at DESC, id DESC"
            ).fetchall()
        items = self._rows_to_dicts(rows)
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in items:
            key = str(item["name"]).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            item["name"] = self._normalize_project_name(str(item["name"]))
            deduped.append(item)
        return deduped

    def create_task(
        self,
        project_id: int,
        title: str,
        details: str = "",
        status: str = "queued",
        priority: int = 3,
        mode: str = "normal",
    ) -> dict[str, Any]:
        normalized_title = self._normalize_task_title(title)
        now = utc_now()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM tasks
                WHERE project_id = ?
                  AND lower(title) = lower(?)
                  AND status IN ('queued', 'in_progress')
                ORDER BY id DESC
                LIMIT 1
                """,
                (project_id, normalized_title),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    """
                    UPDATE tasks
                    SET details = ?, status = ?, priority = ?, mode = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (details, status, priority, mode, now, existing["id"]),
                )
                row = conn.execute("SELECT * FROM tasks WHERE id = ?", (existing["id"],)).fetchone()
                return self._row_to_dict(row) or {}
            cursor = conn.execute(
                """
                INSERT INTO tasks(project_id, title, details, status, priority, mode, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, normalized_title, details, status, priority, mode, now, now),
            )
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_dict(row) or {}

    def update_task_status(self, task_id: int, status: str) -> dict[str, Any] | None:
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id),
            )
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_dict(row)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tasks.*, projects.name AS project_name
                FROM tasks
                JOIN projects ON projects.id = tasks.project_id
                ORDER BY
                    CASE tasks.status
                        WHEN 'in_progress' THEN 0
                        WHEN 'queued' THEN 1
                        ELSE 2
                    END,
                    tasks.priority ASC,
                    tasks.updated_at DESC
                """
            ).fetchall()
        return self._rows_to_dicts(rows)

    def list_tasks_deduped(self) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        items: list[dict[str, Any]] = []
        for task in self.list_tasks():
            key = (
                str(task["project_name"]).strip().lower(),
                str(task["title"]).strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(task)
        return items

    def add_memory(self, kind: str, title: str, content: str) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO memories(kind, title, content, created_at) VALUES(?, ?, ?, ?)",
                (kind, title, content, now),
            )
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_dict(row) or {}

    def list_memories(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return self._rows_to_dicts(rows)

    def add_report(self, title: str, body: str) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO reports(title, body, created_at) VALUES(?, ?, ?)",
                (title, body, now),
            )
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_dict(row) or {}

    def list_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reports ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return self._rows_to_dicts(rows)

    def create_run(self, project_id: int, prompt: str, mode: str = "normal") -> dict[str, Any]:
        now = utc_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs(project_id, prompt, status, mode, created_at, updated_at)
                VALUES(?, ?, 'running', ?, ?, ?)
                """,
                (project_id, prompt, mode, now, now),
            )
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_dict(row) or {}

    def finish_run(self, run_id: int, status: str, summary: str, response: str) -> dict[str, Any] | None:
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, summary = ?, response = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, summary, response, now, run_id),
            )
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._row_to_dict(row)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT runs.*, projects.name AS project_name
                FROM runs
                JOIN projects ON projects.id = runs.project_id
                ORDER BY runs.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return self._rows_to_dicts(rows)

    def log_event(self, run_id: int, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        now = utc_now()
        payload_json = json.dumps(payload or {}, ensure_ascii=True)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events(run_id, kind, message, payload_json, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (run_id, kind, message, payload_json, now),
            )

    def list_events(self, run_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            if run_id is None:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events WHERE run_id = ? ORDER BY id DESC LIMIT ?",
                    (run_id, limit),
                ).fetchall()
        items = self._rows_to_dicts(rows)
        for item in items:
            item["payload"] = json.loads(item.pop("payload_json", "{}"))
        return items

    def overview(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            projects = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
            tasks = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
            memories = conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
            reports = conn.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"]
            runs = conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"]
            events = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        return {
            "projects": projects,
            "tasks": tasks,
            "memories": memories,
            "reports": reports,
            "runs": runs,
            "events": events,
        }

    def build_cache_key(self, project_name: str, mode: str, provider_name: str, prompt: str) -> str:
        raw = f"{project_name.strip().lower()}|{mode}|{provider_name}|{prompt.strip()}"
        return sha256(raw.encode("utf-8")).hexdigest()

    def get_cached_response(
        self,
        project_name: str,
        mode: str,
        provider_name: str,
        prompt: str,
    ) -> dict[str, Any] | None:
        key = self.build_cache_key(project_name, mode, provider_name, prompt)
        now = utc_now()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM response_cache WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE response_cache SET last_used_at = ?, hits = hits + 1 WHERE key = ?",
                (now, key),
            )
            row = conn.execute("SELECT * FROM response_cache WHERE key = ?", (key,)).fetchone()
        return self._row_to_dict(row)

    def set_cached_response(
        self,
        project_name: str,
        mode: str,
        provider_name: str,
        prompt: str,
        response: str,
        summary: str,
    ) -> None:
        key = self.build_cache_key(project_name, mode, provider_name, prompt)
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO response_cache(
                    key, project_name, mode, provider_name, prompt, response, summary, created_at, last_used_at, hits
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(key) DO UPDATE SET
                    response=excluded.response,
                    summary=excluded.summary,
                    provider_name=excluded.provider_name,
                    last_used_at=excluded.last_used_at
                """,
                (key, project_name, mode, provider_name, prompt, response, summary, now, now),
            )
