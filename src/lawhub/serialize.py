"""Turn models back into the JSON shape the frontend expects.

The browser app was written against a specific object shape
(``LAWS``/``PORTALS`` with short keys like ``t``/``d``/``qa``). Keeping the
serializer here means the Python models can evolve without breaking the
static frontend — this layer is the contract.
"""

from __future__ import annotations

from .models import Article, Law, Portal, Resource
from .repository import Corpus


def article_dict(a: Article) -> dict:
    d = {"no": a.no, "t": a.title, "d": a.desc, "tags": list(a.tags)}
    if a.pcode:
        d["pcode"] = a.pcode
    if a.law_label:
        d["law"] = a.law_label
    return d


def resource_dict(r: Resource) -> dict:
    return {"k": r.kind, "src": r.source, "t": r.title, "d": r.desc, "url": r.url}


def law_dict(law: Law) -> dict:
    d = {
        "name": law.name,
        "full": law.full_name,
        "code": law.code,
        "hue": law.hue,
        "desc": law.desc,
        "aliases": list(law.aliases),
        "articles": [article_dict(a) for a in law.articles],
        "qa": [resource_dict(r) for r in law.resources],
    }
    if law.sub_aliases:
        d["subAliases"] = dict(law.sub_aliases)
    return d


def portal_dict(p: Portal) -> dict:
    return {"name": p.name, "note": p.note, "url": p.url}


def frontend_payload(corpus: Corpus) -> dict:
    """The exact ``{LAWS, PORTALS}`` object the browser reads."""
    return {
        "LAWS": {k: law_dict(v) for k, v in corpus.laws.items()},
        "PORTALS": [portal_dict(p) for p in corpus.portals],
    }
