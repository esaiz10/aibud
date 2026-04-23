from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import (
    ANTHROPIC_MODEL,
    DEFAULT_PROVIDER,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OPENAI_BASE_URL,
    OPENAI_NORMAL_MODEL,
    OPENAI_QUICK_MODEL,
    OPENAI_MODEL,
)


@dataclass
class ProviderResult:
    text: str
    reasoning_summary: str
    provider_name: str


class Provider(Protocol):
    name: str

    def generate(self, prompt: str, context: str = "", mode: str = "normal") -> ProviderResult:
        ...


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_coerce_text(item) for item in value if item is not None)
    if isinstance(value, dict):
        if "text" in value:
            return _coerce_text(value["text"])
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def _extract_json_object(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return {}
    return {}


class LocalProvider:
    name = "local"

    def generate(self, prompt: str, context: str = "", mode: str = "normal") -> ProviderResult:
        prompt_lower = prompt.lower()
        if "bug" in prompt_lower or "fix" in prompt_lower:
            reasoning = "Detected an engineering request, so I emphasized reproducibility, scope, and next actions."
            text = (
                "I can help break this down, trace the likely failure surface, and record concrete follow-up tasks. "
                "Use the task board to prioritize the fix, then attach logs or files through the tool layer."
            )
        elif "research" in prompt_lower or "investigate" in prompt_lower:
            reasoning = "Detected a research request, so I focused on discovery, notes, and report generation."
            text = (
                "This looks like research work. I would gather sources, preserve findings as memory entries, "
                "and then emit a structured report with open questions and recommendations."
            )
        else:
            reasoning = "No special workflow matched, so I produced a concise default assistant response."
            text = (
                "AiBud is ready. I can track the project, keep durable notes, emit reports, and run local tools "
                "through the observability layer."
            )
        if context:
            text += f"\n\nContext snapshot:\n{context[:600]}"
        return ProviderResult(text=text, reasoning_summary=reasoning, provider_name=self.name)


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str = OLLAMA_MODEL, host: str = OLLAMA_HOST) -> None:
        self.model = model
        self.host = host

    def _request(self, payload: dict) -> dict:
        request = Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def generate(self, prompt: str, context: str = "", mode: str = "normal") -> ProviderResult:
        system = (
            "You are AiBud, a pragmatic local AI assistant. "
            "Reply as JSON with keys reasoning_summary and response. "
            "The reasoning_summary must be a short observable summary, not hidden chain-of-thought."
        )
        formatted_prompt = json.dumps({"prompt": prompt, "context": context})
        try:
            raw = self._request(
                {
                    "model": self.model,
                    "system": system,
                    "prompt": formatted_prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2},
                }
            )
            parsed = json.loads(raw.get("response", "") or "{}")
            return ProviderResult(
                text=_coerce_text(parsed.get("response", "")),
                reasoning_summary=_coerce_text(parsed.get("reasoning_summary", "")),
                provider_name=f"{self.name}:{self.model}",
            )
        except (URLError, TimeoutError, json.JSONDecodeError, OSError):
            return LocalProvider().generate(prompt, context=context)


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        kwargs = {"api_key": os.environ["OPENAI_API_KEY"]}
        if OPENAI_BASE_URL:
            kwargs["base_url"] = OPENAI_BASE_URL
        self.client = OpenAI(**kwargs)

    def _model_for_mode(self, mode: str) -> str:
        if mode == "quick":
            return OPENAI_QUICK_MODEL
        if mode == "normal":
            return OPENAI_NORMAL_MODEL
        return OPENAI_MODEL

    def _fallback_result(self, text: str, model: str) -> ProviderResult:
        plain = (text or "").strip() or "AiBud completed the request."
        summary = plain.splitlines()[0][:160] if plain else "Completed request."
        return ProviderResult(
            text=plain,
            reasoning_summary=summary,
            provider_name=f"{self.name if not OPENAI_BASE_URL else f'{self.name}-compatible'}:{model}",
        )

    def generate(self, prompt: str, context: str = "", mode: str = "normal") -> ProviderResult:
        system = (
            "You are AiBud, a pragmatic local AI assistant. "
            "Reply with a JSON object containing keys reasoning_summary and response. "
            "The reasoning_summary must be a brief observable summary, not hidden chain-of-thought. "
            "If you cannot comply perfectly, still answer usefully."
        )
        payload = {"prompt": prompt, "context": context}
        model = self._model_for_mode(mode)
        try:
            response = self.client.chat.completions.create(
                model=model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload)},
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            parsed = _extract_json_object(text)
            if parsed:
                return ProviderResult(
                    text=_coerce_text(parsed.get("response", "")),
                    reasoning_summary=_coerce_text(parsed.get("reasoning_summary", "")),
                    provider_name=f"{self.name if not OPENAI_BASE_URL else f'{self.name}-compatible'}:{model}",
                )
            return self._fallback_result(text, model)
        except Exception:
            return LocalProvider().generate(prompt, context=context, mode=mode)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, prompt: str, context: str = "", mode: str = "normal") -> ProviderResult:
        system = (
            "You are AiBud, a pragmatic local AI assistant. "
            "Reply with JSON containing reasoning_summary and response. "
            "The reasoning_summary must be a brief observable summary, not hidden chain-of-thought."
        )
        response = self.client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=900,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps({"prompt": prompt, "context": context}),
                }
            ],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()
        parsed = _extract_json_object(text)
        if not parsed:
            return ProviderResult(
                text=text,
                reasoning_summary=(text.splitlines()[0][:160] if text else "Completed request."),
                provider_name=self.name,
            )
        return ProviderResult(
            text=_coerce_text(parsed.get("response", "")),
            reasoning_summary=_coerce_text(parsed.get("reasoning_summary", "")),
            provider_name=self.name,
        )


def build_provider() -> Provider:
    provider = DEFAULT_PROVIDER
    if provider == "ollama":
        return OllamaProvider()
    if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
        try:
            return OpenAIProvider()
        except Exception:
            return LocalProvider()
    if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicProvider()
        except Exception:
            return LocalProvider()
    if provider == "auto":
        try:
            return OllamaProvider()
        except Exception:
            pass
        if os.environ.get("OPENAI_API_KEY"):
            try:
                return OpenAIProvider()
            except Exception:
                pass
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                return AnthropicProvider()
            except Exception:
                pass
    return LocalProvider()
