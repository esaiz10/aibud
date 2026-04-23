from __future__ import annotations


def build_report_skill(runtime, project_name: str, prompt: str) -> dict:
    tasks = runtime.storage.list_tasks_deduped()[:10]
    memories = runtime.storage.list_memories(limit=8)
    body = [
        f"# AiBud Report: {project_name}",
        "",
        f"Prompt: {prompt}",
        "",
        "## Active tasks",
    ]
    if tasks:
        body.extend(f"- [{task['status']}] {task['title']} ({task['project_name']})" for task in tasks)
    else:
        body.append("- No tasks yet.")
    body.extend(["", "## Recent memories"])
    if memories:
        seen_memory_titles = set()
        for item in memories:
            key = (item["kind"], item["title"])
            if key in seen_memory_titles:
                continue
            seen_memory_titles.add(key)
            body.append(f"- {item['kind']}: {item['title']}")
    else:
        body.append("- No memory entries yet.")
    text = "\n".join(body)
    report = runtime.storage.add_report(f"{project_name} status report", text)
    runtime.storage.add_memory("report", "Generated status report", text)
    return {
        "summary": "Generated a status report from current tasks and memory.",
        "response": text,
        "report_id": report["id"],
    }
