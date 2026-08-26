"""Domain models for the M&A / corporate-governance law hub.

These dataclasses are the typed, in-memory representation of the corpus.
The canonical data lives in ``data/laws.json`` and is loaded into these
models by :mod:`lawhub.repository`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

MOJ_BASE = "https://law.moj.gov.tw/LawClass/"


@dataclass(frozen=True)
class Article:
    """A single statutory article (條文).

    ``pcode``/``law_label`` are only set when an article belongs to a
    statute other than its parent law's default code — this happens for the
    投審 bucket, which spans three separate regulations.
    """

    no: str
    title: str
    desc: str
    tags: tuple[str, ...] = ()
    pcode: Optional[str] = None
    law_label: Optional[str] = None

    def code_for(self, default_pcode: str) -> str:
        return self.pcode or default_pcode

    def label_for(self, default_label: str) -> str:
        return self.law_label or default_label

    def url(self, default_pcode: str) -> str:
        code = self.code_for(default_pcode)
        return f"{MOJ_BASE}LawSingle.aspx?pcode={code}&flno={self.no}"


@dataclass(frozen=True)
class Resource:
    """A Q&A / 函釋 / 處理原則 entry — a curated external reference."""

    kind: str          # 問答集, 函釋, 處理程序, 判解系統, ...
    source: str        # 公平會, 證期局, 投審司, ...
    title: str
    desc: str
    url: str


@dataclass(frozen=True)
class Law:
    key: str
    name: str
    full_name: str
    code: str          # 全國法規資料庫 pcode of the primary statute
    hue: str           # CSS variable used by the frontend
    desc: str
    aliases: tuple[str, ...] = ()
    sub_aliases: dict[str, str] = field(default_factory=dict)
    articles: tuple[Article, ...] = ()
    resources: tuple[Resource, ...] = ()

    # --- MOJ url helpers -------------------------------------------------
    def full_text_url(self) -> str:
        return f"{MOJ_BASE}LawAll.aspx?pcode={self.code}"

    def content_search_url(self, pcode: Optional[str] = None) -> str:
        return f"{MOJ_BASE}LawSearchCNKey.aspx?BTNType=CON&pcode={pcode or self.code}"

    def statute_codes(self) -> list[str]:
        """Every distinct pcode referenced by this law's articles."""
        seen: list[str] = [self.code]
        for a in self.articles:
            c = a.code_for(self.code)
            if c not in seen:
                seen.append(c)
        return seen


@dataclass(frozen=True)
class Portal:
    name: str
    note: str
    url: str
