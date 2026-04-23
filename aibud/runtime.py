from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import (
    DEFAULT_PROJECT,
    MAX_CONTEXT_CHARS_DEEP,
    MAX_CONTEXT_CHARS_NORMAL,
    MAX_CONTEXT_CHARS_QUICK,
    MAX_RESPONSE_CHARS,
    PROJECTS_DIR,
)
from .providers import ProviderResult, build_provider
from .skills import SKILLS
from .storage import Storage
from .tools import ToolRegistry


@dataclass
class RunOutcome:
    run: dict[str, Any]
    response: str
    summary: str
    mode: str
    cache_hit: bool = False


class AiBudRuntime:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.provider = build_provider()
        self.projects_dir = PROJECTS_DIR
        self._active_run_id: int | None = None
        self.tools = ToolRegistry(self._log_tool_event)

    def bootstrap(self) -> None:
        project = self.ensure_project(DEFAULT_PROJECT)
        if not self.storage.list_tasks():
            self.storage.create_task(
                project["id"],
                "Teach AiBud your current priorities",
                details="Use the web UI or CLI to add tasks and memory entries for the next project.",
                status="in_progress",
                priority=1,
            )
        if not self.storage.list_memories():
            self.storage.add_memory(
                "preference",
                "Reasoning visibility",
                "Expose reasoning summaries, tool calls, and execution traces without claiming hidden chain-of-thought.",
            )

    def ensure_project(self, name: str) -> dict[str, Any]:
        return self.storage.ensure_project(name, description=f"AiBud project space for {name}")

    def _log_tool_event(self, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        if self._active_run_id is not None:
            self.storage.log_event(self._active_run_id, kind, message, payload)

    def _select_skill(self, prompt: str) -> str | None:
        lowered = prompt.lower()
        if "asteroid" in lowered or ("game" in lowered and "build" in lowered):
            return "build_arcade"
        if "report" in lowered or "status summary" in lowered:
            return "write_report"
        return None

    def _route_mode(self, prompt: str, requested_mode: str) -> str:
        if requested_mode in {"quick", "normal", "deep"}:
            return requested_mode
        lowered = prompt.lower().strip()
        deep_signals = ("research", "investigate", "debug", "fix", "design", "architecture", "optimize", "refactor")
        quick_signals = ("hello", "hi", "status", "summary", "say ", "where is", "what is", "list ")
        if len(prompt) > 350 or any(token in lowered for token in deep_signals):
            return "deep"
        if len(prompt) < 90 or any(lowered.startswith(token) or token in lowered for token in quick_signals):
            return "quick"
        return "normal"

    def _context_limit(self, mode: str) -> int:
        return {
            "quick": MAX_CONTEXT_CHARS_QUICK,
            "normal": MAX_CONTEXT_CHARS_NORMAL,
            "deep": MAX_CONTEXT_CHARS_DEEP,
        }.get(mode, MAX_CONTEXT_CHARS_NORMAL)

    def _build_context(self, mode: str) -> str:
        task_limit = 2 if mode == "quick" else 4 if mode == "normal" else 6
        memory_limit = 2 if mode == "quick" else 4 if mode == "normal" else 6
        tasks = [task for task in self.storage.list_tasks_deduped() if task["status"] in {"in_progress", "queued"}][:task_limit]
        memories = self.storage.list_memories(limit=memory_limit)
        lines = ["Tasks:"]
        for task in tasks:
            lines.append(f"- [{task['status']}] {task['title']} ({task['project_name']})")
        lines.append("Memories:")
        for item in memories:
            lines.append(f"- {item['kind']}: {item['title']}")
        return "\n".join(lines)[: self._context_limit(mode)]

    def _normalize_text(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(self._normalize_text(item) for item in value if item is not None)
        if isinstance(value, dict):
            return str(value)
        return str(value)

    def _truncate_response(self, text: str) -> str:
        return text[:MAX_RESPONSE_CHARS]

    def _cache_provider_key(self, skill_name: str | None, mode: str) -> str:
        if skill_name:
            return f"skill:{skill_name}"
        return f"{self.provider.name}:{mode}"

    def run_prompt(self, prompt: str, project_name: str = DEFAULT_PROJECT, requested_mode: str = "auto") -> RunOutcome:
        project = self.ensure_project(project_name)
        canonical_project_name = project["name"]
        mode = self._route_mode(prompt, requested_mode)
        run = self.storage.create_run(project["id"], prompt, mode=mode)
        self._active_run_id = run["id"]
        self.storage.log_event(run["id"], "prompt", "Received prompt", {"prompt": prompt, "mode": mode})

        task = self.storage.create_task(
            project["id"],
            prompt[:80],
            details=prompt,
            status="in_progress",
            priority=2,
            mode=mode,
        )
        self.storage.log_event(run["id"], "task", "Created execution task", {"task_id": task["id"], "mode": mode})

        try:
            skill_name = self._select_skill(prompt)
            response = ""
            summary = ""
            cache_allowed = skill_name is not None or mode in {"quick", "normal"}
            cache_provider = self._cache_provider_key(skill_name, mode)
            if cache_allowed:
                cached = self.storage.get_cached_response(canonical_project_name, mode, cache_provider, prompt)
                if cached is not None:
                    response = cached["response"]
                    summary = cached["summary"]
                    self.storage.log_event(
                        run["id"],
                        "cache",
                        "Served response from cache",
                        {"mode": mode, "provider": cache_provider, "hits": cached["hits"]},
                    )
                    self.storage.update_task_status(task["id"], "done")
                    finished = self.storage.finish_run(run["id"], "completed", summary, response)
                    return RunOutcome(run=finished or run, response=response, summary=summary, mode=mode, cache_hit=True)
            if skill_name:
                self.storage.log_event(run["id"], "skill", "Selected skill", {"skill": skill_name})
                result = SKILLS[skill_name](self, canonical_project_name, prompt)
                response = self._truncate_response(self._normalize_text(result["response"]))
                summary = self._normalize_text(result["summary"])
            else:
                context = self._build_context(mode)
                self.storage.log_event(
                    run["id"],
                    "provider",
                    "Calling language provider",
                    {"provider": self.provider.name, "mode": mode, "context_chars": len(context)},
                )
                result = self.provider.generate(prompt, context=context, mode=mode)
                response = self._truncate_response(self._normalize_text(result.text))
                summary = self._normalize_text(result.reasoning_summary)
                self.storage.log_event(
                    run["id"],
                    "reasoning",
                    "Generated reasoning summary",
                    {"provider": result.provider_name, "summary": result.reasoning_summary, "mode": mode},
                )
                self.storage.add_memory("conversation", prompt[:60], response[:1000])

            if cache_allowed:
                self.storage.set_cached_response(canonical_project_name, mode, cache_provider, prompt, response, summary)
            self.storage.update_task_status(task["id"], "done")
            finished = self.storage.finish_run(run["id"], "completed", summary, response)
            self.storage.log_event(run["id"], "run", "Completed run", {"summary": summary, "mode": mode})
            return RunOutcome(run=finished or run, response=response, summary=summary, mode=mode)
        except Exception as exc:
            error_text = self._normalize_text(exc)
            summary = "Run failed."
            response = f"AiBud hit an error while processing this prompt.\n\n{error_text}"
            self.storage.update_task_status(task["id"], "failed")
            self.storage.log_event(
                run["id"],
                "error",
                "Run failed",
                {"error": error_text, "task_id": task["id"], "mode": mode},
            )
            failed_run = self.storage.finish_run(run["id"], "failed", summary, response)
            return RunOutcome(run=failed_run or run, response=response, summary=summary, mode=mode)
        finally:
            self._active_run_id = None
