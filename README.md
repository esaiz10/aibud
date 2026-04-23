# AiBud

A ground-up AI ecosystem built with pure Python and a whole lot of spunk. No LiteLLM, no LangChain — just the standard library and whatever model you want to plug in.

It's been quite the journey, but the results have been worth it.

## What it does

AiBud helps with anything on your system — OpenClaw-style shell access, coding, research, and whatever else comes to mind. It also ships with:

- **Project tracking** — tasks, priorities, and status you and AiBud share side-by-side
- **Memory** — persistent notes and findings that carry across sessions
- **Skills** — specialized workflows like code generation and report writing
- **Reports** — structured summaries AiBud can emit on demand
- **Full web frontend visibility** — see every tool call, internal thought, and trace event in real time

The tasks on the web dashboard are the same tasks AiBud is working from. You can prioritize and manage them together on larger projects.

## Highlights

- Asked for an Asteroids game. Got one in under a minute.
- Finds and fixes bugs without being hand-held.
- Adapts as you add more tools and skills.
- JARVIS-style assistant energy without the cloud dependency.

## Stack

- **Backend:** Python standard library only (no frameworks)
- **HTTP server:** `ThreadingHTTPServer`
- **Database:** SQLite with WAL mode
- **Frontend:** Vanilla JS, HTML5, CSS3
- **LLM providers:** Ollama (default), OpenAI, Anthropic, or local fallback

## Setup

1. Copy `.env.example` to `.env` and fill in your API keys (if not using Ollama)
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python main.py`
4. Open the web UI at `http://localhost:8080`

## Configuration

| Env var | Default | Description |
|---|---|---|
| `AIBUD_PROVIDER` | `ollama` | LLM backend (`ollama`, `openai`, `anthropic`, `auto`) |
| `AIBUD_OLLAMA_MODEL` | `gemma3:4b` | Ollama model to use |
| `AIBUD_OPENAI_MODEL` | `openai/gpt-oss-120b` | OpenAI model |
| `AIBUD_ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Anthropic model |
| `AIBUD_OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama host |

This has truly made computing fun again.
