from __future__ import annotations

import argparse

from .config import DB_PATH
from .runtime import AiBudRuntime
from .server import serve
from .storage import Storage


def build_runtime() -> AiBudRuntime:
    runtime = AiBudRuntime(Storage(DB_PATH))
    runtime.bootstrap()
    return runtime


def print_section(title: str, body: str) -> None:
    print(f"\n{title}")
    print("=" * len(title))
    print(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="AiBud local assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="Run a prompt through AiBud")
    ask.add_argument("prompt", help="Prompt to execute")
    ask.add_argument("--project", default="Inbox", help="Project name")
    ask.add_argument("--mode", default="auto", choices=["auto", "quick", "normal", "deep"], help="Execution mode")

    serve_cmd = sub.add_parser("serve", help="Run the web dashboard")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8765)

    sub.add_parser("status", help="Show current state")
    sub.add_parser("seed", help="Seed the database with starter content")

    args = parser.parse_args()
    runtime = build_runtime()

    if args.command == "ask":
        outcome = runtime.run_prompt(args.prompt, project_name=args.project, requested_mode=args.mode)
        print_section(
            "AiBud Summary",
            f"Mode: {outcome.mode}\nCache hit: {'yes' if outcome.cache_hit else 'no'}\n\n{outcome.summary or 'No summary recorded.'}",
        )
        print_section("AiBud Response", outcome.response)
        return
    if args.command == "serve":
        serve(runtime, host=args.host, port=args.port)
        return
    if args.command == "seed":
        runtime.bootstrap()
        runtime.storage.add_memory("preference", "Build style", "Ground-up Python, visible traces, no orchestration frameworks.")
        runtime.storage.add_report("Bootstrap report", "AiBud is seeded and ready for prompts.")
        print("AiBud seed data refreshed.")
        return
    if args.command == "status":
        payload = {
            "overview": runtime.storage.overview(),
            "projects": runtime.storage.list_projects(),
            "tasks": runtime.storage.list_tasks_deduped()[:10],
            "runs": runtime.storage.list_runs()[:10],
        }
        overview_lines = [f"{key}: {value}" for key, value in payload["overview"].items()]
        project_lines = [
            f"- {project['name']} [{project['status']}] priority={project['priority']}"
            for project in payload["projects"]
        ] or ["- none"]
        task_lines = [
            f"- {task['title']} [{task['status']}] ({task['project_name']})"
            for task in payload["tasks"]
        ] or ["- none"]
        run_lines = [
            f"- {run['project_name']} [{run['status']}] {run['prompt']}"
            for run in payload["runs"]
        ] or ["- none"]

        print_section("Overview", "\n".join(overview_lines))
        print_section("Projects", "\n".join(project_lines))
        print_section("Tasks", "\n".join(task_lines))
        print_section("Recent Runs", "\n".join(run_lines))


if __name__ == "__main__":
    main()
