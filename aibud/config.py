from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = BASE_DIR / "projects"
STATIC_DIR = BASE_DIR / "aibud" / "static"
DB_PATH = DATA_DIR / "aibud.db"


def load_local_env() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


load_local_env()

DEFAULT_PROJECT = "Inbox"
DEFAULT_PROVIDER = os.environ.get("AIBUD_PROVIDER", "ollama").strip().lower()
OLLAMA_HOST = os.environ.get("AIBUD_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("AIBUD_OLLAMA_MODEL", "gemma3:4b")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/")
OPENAI_QUICK_MODEL = os.environ.get("AIBUD_OPENAI_QUICK_MODEL", "openai/gpt-oss-20b")
OPENAI_NORMAL_MODEL = os.environ.get("AIBUD_OPENAI_NORMAL_MODEL", os.environ.get("AIBUD_OPENAI_FAST_MODEL", "openai/gpt-oss-20b"))
OPENAI_MODEL = os.environ.get("AIBUD_OPENAI_MODEL", "openai/gpt-oss-120b")
ANTHROPIC_MODEL = os.environ.get("AIBUD_ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_CONTEXT_CHARS_QUICK = int(os.environ.get("AIBUD_MAX_CONTEXT_CHARS_QUICK", "350"))
MAX_CONTEXT_CHARS_NORMAL = int(os.environ.get("AIBUD_MAX_CONTEXT_CHARS_NORMAL", "1200"))
MAX_CONTEXT_CHARS_DEEP = int(os.environ.get("AIBUD_MAX_CONTEXT_CHARS_DEEP", "2600"))
MAX_RESPONSE_CHARS = int(os.environ.get("AIBUD_MAX_RESPONSE_CHARS", "6000"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
