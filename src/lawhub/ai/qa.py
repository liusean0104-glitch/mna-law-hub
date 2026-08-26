"""Grounded Q&A — "有引註的問答" with cite-or-abstain enforcement.

Pipeline:

1. **Retrieve** candidate passages from the curated corpus (articles +
   official Q&A/函釋). Keyword scoring today; swap in embeddings later by
   replacing :class:`KeywordRetriever` — the interface is stable.
2. **Prompt** the model with *numbered* sources and a hard instruction:
   cite only ``[n]`` markers that exist, and say you don't know rather than
   guess.
3. **Verify** — this is the part that matters. We parse the ``[n]`` markers
   out of the model's answer and check every one against the sources we
   actually supplied. Fabricated or out-of-range citations are stripped and
   recorded. If nothing survives, the answer is *abstained*.

The verification step is deliberately deterministic Python, not another
model call: the guarantee "every citation resolves to a real official URL"
must not itself depend on an LLM.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..repository import Corpus, get_corpus
from .llm import LLM, get_llm, is_live

_CITE = re.compile(r"\[(\d{1,2})\]")

SYSTEM = """你是台灣併購與公司治理法規的研究助理。

嚴格規則：
1. 只能根據下方提供的「來源」回答。不得引用來源以外的法條、函釋或判決。
2. 每個實質主張後面必須加上引註標記，格式為 [1]、[2]，數字必須對應下方來源編號。
3. 來源不足以回答時，明說「提供的來源不足以回答這個問題」，不要臆測、不要補足。
4. 不要杜撰條號、函釋字號或日期。若來源未寫明，就不要寫。
5. 用繁體中文，簡潔、實務導向。
6. 你提供的是法規研究整理，不是法律意見。

回答格式：先給結論，再分點說明，每點附引註。"""

JSON_SYSTEM = SYSTEM + """

輸出必須是單一 JSON 物件，不要加 markdown 標記：
{"answer": "帶有 [n] 引註的回答", "used": [1,3], "confident": true}
confident 為 false 表示來源不足。"""


@dataclass
class Source:
    """A numbered, citable passage handed to the model."""

    n: int
    kind: str            # article | resource
    law: str
    label: str           # "公平交易法 §11" or the resource title
    text: str
    url: str

    def as_prompt_block(self) -> str:
        return f"[{self.n}] {self.label}（{self.law}）\n{self.text}\n來源：{self.url}"

    def as_citation(self) -> dict:
        return {"n": self.n, "kind": self.kind, "law": self.law,
                "label": self.label, "url": self.url}


@dataclass
class GroundedAnswer:
    question: str
    answer: str
    citations: list[dict] = field(default_factory=list)
    abstained: bool = False
    dropped: list[int] = field(default_factory=list)   # fabricated markers
    model: str = ""
    considered: int = 0

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": self.citations,
            "abstained": self.abstained,
            "dropped_citations": self.dropped,
            "model": self.model,
            "sources_considered": self.considered,
        }


class KeywordRetriever:
    """Scores corpus entries against the query.

    Chinese text doesn't tokenise on whitespace, so we score on character
    bigrams plus whole-query containment — crude but effective for a
    curated corpus of this size, and dependency-free.
    """

    def __init__(self, corpus: Corpus | None = None):
        self.corpus = corpus or get_corpus()

    @staticmethod
    def _bigrams(s: str) -> set[str]:
        s = re.sub(r"\s+", "", s.lower())
        return {s[i:i + 2] for i in range(len(s) - 1)} or {s}

    def _score(self, query: str, hay: str, title: str) -> float:
        q, h = query.lower(), hay.lower()
        score = 0.0
        if q in h:
            score += 10
        if q in title.lower():
            score += 6
        qb, hb = self._bigrams(query), self._bigrams(hay)
        if qb:
            score += 8 * len(qb & hb) / len(qb)
        return score

    def retrieve(self, query: str, k: int = 8) -> list[Source]:
        c = self.corpus
        scored: list[tuple[float, Source]] = []

        for law_key, a in c.all_articles():
            law = c.laws[law_key]
            label = f"{a.label_for(law.name)} §{a.no}　{a.title}"
            hay = " ".join([a.no, a.title, a.desc, " ".join(a.tags), law.name])
            s = self._score(query, hay, a.title)
            if s > 0:
                scored.append((s, Source(
                    0, "article", a.label_for(law.name), label,
                    f"{a.title}：{a.desc}", a.url(law.code))))

        for law_key, r in c.all_resources():
            law = c.laws[law_key]
            hay = " ".join([r.title, r.desc, r.kind, r.source, law.name])
            s = self._score(query, hay, r.title) * 0.9   # slight statute bias
            if s > 0:
                scored.append((s, Source(
                    0, "resource", law.name, f"{r.title}（{r.source}・{r.kind}）",
                    r.desc, r.url)))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = [src for _, src in scored[:k]]
        for i, src in enumerate(top, 1):
            src.n = i
        return top


class GroundedAnswerer:
    """Retrieve → prompt → verify citations."""

    def __init__(self, corpus: Corpus | None = None, llm: LLM | None = None):
        self.corpus = corpus or get_corpus()
        self.retriever = KeywordRetriever(self.corpus)
        self.llm = llm or get_llm()

    # --- the guarantee ---------------------------------------------------
    @staticmethod
    def _verify(answer: str, sources: list[Source]) -> tuple[str, list[dict], list[int]]:
        """Strip citations that don't resolve to a supplied source."""
        valid = {s.n: s for s in sources}
        dropped: list[int] = []

        def repl(m: re.Match) -> str:
            n = int(m.group(1))
            if n in valid:
                return m.group(0)
            dropped.append(n)
            return ""          # remove the fabricated marker

        cleaned = _CITE.sub(repl, answer)
        used = sorted({int(m) for m in _CITE.findall(cleaned)})
        citations = [valid[n].as_citation() for n in used]
        return cleaned.strip(), citations, sorted(set(dropped))

    def answer(self, question: str, k: int = 8) -> GroundedAnswer:
        sources = self.retriever.retrieve(question, k=k)

        if not sources:
            return GroundedAnswer(
                question=question,
                answer="提供的來源不足以回答這個問題。這個語料庫收錄的是併購與公司"
                       "治理的精選條文與官方問答，建議改用官方全文檢索。",
                abstained=True, model=getattr(self.llm, "name", "?"),
            )

        block = "\n\n".join(s.as_prompt_block() for s in sources)
        prompt = (f"問題：{question}\n\n來源：\n{block}\n\n"
                  f"請依規則回答，並在每個主張後標註 [n] 引註。")

        raw = self.llm.complete(JSON_SYSTEM, prompt, temperature=0.15)

        text, confident = raw, True
        try:
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(),
                                     flags=re.M).strip())
            text = str(data.get("answer", raw))
            confident = bool(data.get("confident", True))
        except (json.JSONDecodeError, AttributeError):
            pass   # model returned prose; verify it as-is

        text, citations, dropped = self._verify(text, sources)
        abstained = (not citations) or (not confident and not is_live(self.llm))

        if not citations and is_live(self.llm):
            text = ("提供的來源不足以回答這個問題（回答未能對應到任何官方來源）。\n\n"
                    + text)
            abstained = True

        return GroundedAnswer(
            question=question, answer=text, citations=citations,
            abstained=abstained, dropped=dropped,
            model=getattr(self.llm, "name", "?"), considered=len(sources),
        )
