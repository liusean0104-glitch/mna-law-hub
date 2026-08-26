"""Interface stub for the grounded-answer (RAG) layer — see docs/ROADMAP.md.

Deliberately dependency-free: this defines the *contract* a retrieval
backend must satisfy so the product can be built against it before any
vector DB / model is chosen. The guiding rule for a legal-domain system is
**cite-or-abstain**: every answer must carry citations to official sources,
and the system must refuse when it cannot ground a claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Citation:
    law_key: str
    no: str
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class GroundedAnswer:
    question: str
    answer: str
    citations: tuple[Citation, ...]
    abstained: bool = False           # True when nothing could be grounded


class Retriever(Protocol):
    """A retrieval backend (keyword today, embeddings later)."""

    def retrieve(self, query: str, k: int = 8) -> list[Citation]: ...


class Answerer(Protocol):
    """Turns retrieved citations into a grounded, cite-or-abstain answer."""

    def answer(self, question: str, k: int = 8) -> GroundedAnswer: ...
