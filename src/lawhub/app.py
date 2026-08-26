"""FastAPI application: JSON API + the static single-page frontend.

Run locally with::

    uvicorn lawhub.app:app --reload

The API surface (``/api/*``) is deliberately the same corpus the frontend
uses, so any future AI feature (semantic search, an agent, a Q&A endpoint)
can build on the same typed data rather than scraping the HTML.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .limits import is_public, limiter
from .repository import get_corpus
from .serialize import frontend_payload, law_dict

WEB_DIR = Path(__file__).resolve().parents[2] / "web"

app = FastAPI(
    title="M&A / Corporate-Governance Law Hub",
    version="0.1.0",
    description="Taiwan M&A and corporate-governance legal reference API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", **get_corpus().counts()}


@app.get("/api/bootstrap")
def bootstrap() -> JSONResponse:
    """Everything the frontend needs in one payload ({LAWS, PORTALS})."""
    return JSONResponse(frontend_payload(get_corpus()))


@app.get("/api/laws")
def list_laws() -> list[dict]:
    c = get_corpus()
    return [
        {"key": k, "name": l.name, "code": l.code,
         "articles": len(l.articles), "resources": len(l.resources)}
        for k, l in c.laws.items()
    ]


@app.get("/api/laws/{key}")
def get_law(key: str) -> dict:
    c = get_corpus()
    if key not in c.laws:
        raise HTTPException(404, f"unknown law '{key}'")
    return {"key": key, **law_dict(c.laws[key])}


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), limit: int = 50) -> dict:
    c = get_corpus()
    hits = c.search(q, limit=limit)
    out = []
    for h in hits:
        law = c.laws[h.law_key]
        if h.kind == "article":
            a = h.ref
            out.append({
                "kind": "article", "law": law.name, "law_key": h.law_key,
                "no": a.no, "title": a.title, "desc": a.desc,
                "url": a.url(law.code), "score": h.score,
            })
        else:
            r = h.ref
            out.append({
                "kind": "resource", "law": law.name, "law_key": h.law_key,
                "source": r.source, "type": r.kind, "title": r.title,
                "desc": r.desc, "url": r.url, "score": h.score,
            })
    return {"query": q, "count": len(out), "results": out}


@app.get("/api/deal-flow")
def deal_flow() -> dict:
    """Structured Taiwan public-company M&A compliance procedure."""
    from .ai.deal_flow import build_checklist
    steps = build_checklist(get_corpus())
    return {"count": len(steps), "steps": steps}


# --- AI layer -------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    k: int = Field(8, ge=1, le=20)


class DraftRequest(BaseModel):
    kind: str = Field("checklist", pattern="^(checklist|memo|disclosure)$")
    target: str = "【標的公司】"
    acquirer: str = "【收購方】"
    structure: str = "合併"
    target_listed: bool = True
    stake_pct: float = 100.0
    cross_border: bool = False
    prc_capital: bool = False
    ftc_threshold_met: bool = True
    consideration: str = "現金"
    notes: str = ""


@app.post("/api/ask")
def ask(req: AskRequest, request: Request) -> dict:
    """Grounded Q&A. Every citation is verified against the corpus."""
    limiter.check(request)
    from .ai.qa import GroundedAnswerer
    return GroundedAnswerer(get_corpus()).answer(req.question, k=req.k).to_dict()


@app.post("/api/draft")
def draft(req: DraftRequest, request: Request) -> dict:
    """Generate a human-review-required draft document."""
    limiter.check(request)
    from .ai.draft import DealFacts, Drafter
    facts = DealFacts(**req.model_dump(exclude={"kind"}))
    return Drafter(get_corpus()).draft(req.kind, facts).to_dict()  # type: ignore[arg-type]


@app.get("/api/ai/status")
def ai_status() -> dict:
    """Which provider is live — lets the UI warn when running offline."""
    from .ai.llm import get_llm, is_live
    llm = get_llm()
    return {
        "provider": getattr(llm, "name", "?"),
        "live": is_live(llm),
        "public": is_public(),
        "limits": limiter.snapshot(),
    }


@app.get("/api/jump")
def jump(cmd: str = Query(..., min_length=1)) -> dict:
    """Parse a command like '證交 43-1' and return the deep-link."""
    c = get_corpus()
    parsed = c.parse_command(cmd)
    if not parsed:
        raise HTTPException(400, "empty command")
    if parsed["type"] == "search":
        return {"type": "search", "query": parsed["query"]}
    return {
        "type": "article",
        "law_key": parsed["law_key"],
        "flno": parsed["flno"],
        "pcode": parsed["pcode"],
        "url": c.resolve_jump(cmd),
    }


# --- static frontend (mounted last so /api/* wins) -----------------------
if WEB_DIR.exists():
    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (WEB_DIR / "index.html").read_text(encoding="utf-8")

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
