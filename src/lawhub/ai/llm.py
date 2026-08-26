"""LLM provider abstraction.

Defaults to Gemini (``google-genai``) but the rest of the codebase only
depends on the :class:`LLM` protocol, so swapping to Claude/OpenAI/a local
model means adding one class here — not touching the RAG or drafting logic.

Configuration is environment-driven::

    export GEMINI_API_KEY=...          # required for the Gemini provider
    export LAWHUB_LLM=gemini           # gemini | echo   (default: gemini)
    export LAWHUB_MODEL=gemini-3.5-flash-lite

If no API key is present the loader falls back to :class:`EchoLLM`, which
returns a deterministic canned response. That keeps the test suite and CI
fully offline — no network, no key, no cost.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol


class LLMError(RuntimeError):
    """Raised when a provider is misconfigured or the call fails."""


class LLM(Protocol):
    """Minimal contract: text in, text out."""

    name: str

    def complete(self, system: str, prompt: str, *, temperature: float = 0.2,
                 max_tokens: int = 2048) -> str: ...


# --------------------------------------------------------------------------
class GeminiLLM:
    """Google Gemini via the ``google-genai`` SDK.

    Gemini 3.x dropped support for the sampling knobs (``temperature``,
    ``top_p``, ``top_k``): they are ignored at best and can error at worst.
    We therefore omit them for any 3.x model and only pass them for older
    ones, so switching models never breaks the call.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.getenv("LAWHUB_MODEL", "gemini-3.5-flash-lite")
        self.name = f"gemini:{self.model}"
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY is not set")
        try:
            from google import genai  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "google-genai is not installed — run: pip install google-genai"
            ) from exc
        self._genai = genai
        self._client = genai.Client(api_key=key)

    @property
    def _is_gemini_3x(self) -> bool:
        m = re.sub(r"^models/", "", self.model)
        return m.startswith("gemini-3")

    def complete(self, system: str, prompt: str, *, temperature: float = 0.2,
                 max_tokens: int = 2048) -> str:
        from google.genai import types  # type: ignore

        cfg: dict = {"system_instruction": system, "max_output_tokens": max_tokens}
        if not self._is_gemini_3x:
            cfg["temperature"] = temperature

        try:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(**cfg),
            )
        except Exception as exc:  # pragma: no cover - network dependent
            raise LLMError(f"Gemini call failed: {exc}") from exc
        return (resp.text or "").strip()


# --------------------------------------------------------------------------
class EchoLLM:
    """Offline stub used when no API key is configured.

    It does not invent legal content. It returns a structured response built
    only from the context it was given, so the pipeline (and its
    cite-or-abstain checks) can be exercised without a network call.
    """

    name = "echo"

    def complete(self, system: str, prompt: str, *, temperature: float = 0.2,
                 max_tokens: int = 2048) -> str:
        refs = re.findall(r"\[(\d+)\]", prompt)
        if "JSON" in system or "JSON" in prompt:
            uniq = sorted({int(r) for r in refs})[:3]
            return json.dumps({
                "answer": "（離線模式：未設定 API 金鑰，此為示範輸出，"
                          "僅列出檢索到的來源，未做法律分析。）",
                "used": uniq or [1],
                "confident": False,
            }, ensure_ascii=False)
        return ("（離線模式：未設定 API 金鑰。）\n"
                "已檢索到的來源編號：" + ", ".join(dict.fromkeys(refs)) if refs
                else "（離線模式：未檢索到來源。）")


# --------------------------------------------------------------------------
def get_llm() -> LLM:
    """Build the configured provider, falling back to the offline stub."""
    choice = os.getenv("LAWHUB_LLM", "gemini").lower()
    if choice == "echo":
        return EchoLLM()
    if choice == "gemini":
        try:
            return GeminiLLM()
        except LLMError:
            return EchoLLM()
    raise LLMError(f"unknown LAWHUB_LLM provider: {choice}")


def is_live(llm: LLM) -> bool:
    """True when a real model (not the offline stub) is in use."""
    return getattr(llm, "name", "") != "echo"
