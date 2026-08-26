"""Load the corpus and provide query helpers (get / search / jump).

This is the single read path over the data. Both the web API
(:mod:`lawhub.api`) and the static exporter (:mod:`scripts.export_web`)
go through here, so there is exactly one source of truth.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Iterable, Optional

from .models import Article, Law, Portal, Resource

_ARTICLE_TOKEN = re.compile(r"\d+(?:-\d+)?")


def _load_raw() -> dict:
    with resources.files("lawhub.data").joinpath("laws.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def _to_article(d: dict) -> Article:
    return Article(
        no=d["no"],
        title=d["t"],
        desc=d["d"],
        tags=tuple(d.get("tags", [])),
        pcode=d.get("pcode"),
        law_label=d.get("law"),
    )


def _to_resource(d: dict) -> Resource:
    return Resource(kind=d["k"], source=d["src"], title=d["t"], desc=d["d"], url=d["url"])


def _to_law(key: str, d: dict) -> Law:
    return Law(
        key=key,
        name=d["name"],
        full_name=d["full"],
        code=d["code"],
        hue=d["hue"],
        desc=d["desc"],
        aliases=tuple(d.get("aliases", [])),
        sub_aliases=dict(d.get("subAliases", {})),
        articles=tuple(_to_article(a) for a in d.get("articles", [])),
        resources=tuple(_to_resource(q) for q in d.get("qa", [])),
    )


@dataclass
class SearchHit:
    law_key: str
    kind: str            # "article" | "resource"
    ref: object          # Article | Resource
    score: int


class Corpus:
    """In-memory corpus with lookup, jump-parsing and search."""

    def __init__(self, laws: dict[str, Law], portals: list[Portal]):
        self.laws = laws
        self.portals = portals

    # --- construction ----------------------------------------------------
    @classmethod
    def load(cls) -> "Corpus":
        raw = _load_raw()
        laws = {k: _to_law(k, v) for k, v in raw["LAWS"].items()}
        portals = [Portal(p["name"], p["note"], p["url"]) for p in raw["PORTALS"]]
        return cls(laws, portals)

    # --- basic access ----------------------------------------------------
    def law(self, key: str) -> Law:
        return self.laws[key]

    def all_articles(self) -> Iterable[tuple[str, Article]]:
        for key, law in self.laws.items():
            for a in law.articles:
                yield key, a

    def all_resources(self) -> Iterable[tuple[str, Resource]]:
        for key, law in self.laws.items():
            for r in law.resources:
                yield key, r

    def counts(self) -> dict[str, int]:
        return {
            "laws": len(self.laws),
            "articles": sum(len(l.articles) for l in self.laws.values()),
            "resources": sum(len(l.resources) for l in self.laws.values()),
            "portals": len(self.portals),
        }

    # --- command bar: parse "證交 43-1" / "外資 4" ----------------------
    def parse_command(self, text: str) -> Optional[dict]:
        s = (text or "").strip()
        if not s:
            return None
        low = s.lower()
        law_key, matched = None, ""
        for key, law in self.laws.items():
            for alias in law.aliases:
                if alias.lower() in low and len(alias) > len(matched):
                    law_key, matched = key, alias
        token = _ARTICLE_TOKEN.search(s)
        if law_key and token:
            law = self.laws[law_key]
            pcode = law.code
            best = ""
            for alias, code in law.sub_aliases.items():
                if alias in s and len(alias) > len(best):
                    best, pcode = alias, code
            return {"type": "article", "law_key": law_key, "flno": token.group(0), "pcode": pcode}
        return {"type": "search", "query": s}

    def resolve_jump(self, text: str) -> Optional[str]:
        """Return the MOJ deep-link for a command-bar jump, or None."""
        parsed = self.parse_command(text)
        if not parsed or parsed["type"] != "article":
            return None
        return (
            f"https://law.moj.gov.tw/LawClass/LawSingle.aspx"
            f"?pcode={parsed['pcode']}&flno={parsed['flno']}"
        )

    # --- full-text-ish search over the curated corpus --------------------
    def search(self, query: str, limit: int = 50) -> list[SearchHit]:
        q = (query or "").strip().lower()
        if not q:
            return []
        hits: list[SearchHit] = []
        for key, a in self.all_articles():
            law = self.laws[key]
            hay = " ".join([a.no, a.title, a.desc, " ".join(a.tags),
                            a.label_for(law.name), law.name]).lower()
            if q in hay:
                score = 3 if q in a.title.lower() or q in a.no.lower() else 1
                hits.append(SearchHit(key, "article", a, score))
        for key, r in self.all_resources():
            law = self.laws[key]
            hay = " ".join([r.title, r.desc, r.kind, r.source, law.name]).lower()
            if q in hay:
                score = 2 if q in r.title.lower() else 1
                hits.append(SearchHit(key, "resource", r, score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]


@lru_cache(maxsize=1)
def get_corpus() -> Corpus:
    """Process-wide singleton."""
    return Corpus.load()
