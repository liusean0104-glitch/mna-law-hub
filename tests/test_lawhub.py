"""Tests for the corpus logic and the HTTP API."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lawhub.app import app                    # noqa: E402
from lawhub.repository import get_corpus      # noqa: E402

client = TestClient(app)


# --- corpus ---------------------------------------------------------------
def test_corpus_counts():
    c = get_corpus()
    counts = c.counts()
    assert counts["laws"] == 6
    assert counts["articles"] >= 50
    assert counts["resources"] >= 30


@pytest.mark.parametrize(
    "cmd,pcode,flno",
    [
        ("證交 43-1", "G0400001", "43-1"),
        ("公司 156", "J0080001", "156"),
        ("公平 11", "J0150002", "11"),
        ("企併 12", "J0080041", "12"),
        ("外資 4", "J0040002", "4"),     # sub-alias routing
        ("陸資 4", "Q0040015", "4"),     # same flno, different statute
        ("赴陸 4", "Q0040001", "4"),
    ],
)
def test_command_routing(cmd, pcode, flno):
    parsed = get_corpus().parse_command(cmd)
    assert parsed["type"] == "article"
    assert parsed["pcode"] == pcode
    assert parsed["flno"] == flno


def test_keyword_falls_through_to_search():
    assert get_corpus().parse_command("內線交易")["type"] == "search"


def test_search_matches_articles_and_resources():
    hits = get_corpus().search("結合")
    kinds = {h.kind for h in hits}
    assert "article" in kinds
    assert "resource" in kinds


# --- API ------------------------------------------------------------------
def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_bootstrap_shape():
    data = client.get("/api/bootstrap").json()
    assert set(data) == {"LAWS", "PORTALS"}
    assert "ftc" in data["LAWS"] and "invest" in data["LAWS"]


def test_get_law_404():
    assert client.get("/api/laws/nope").status_code == 404


def test_api_jump():
    j = client.get("/api/jump", params={"cmd": "證交 43-1"}).json()
    assert j["type"] == "article"
    assert j["url"].endswith("pcode=G0400001&flno=43-1")


def test_api_search():
    r = client.get("/api/search", params={"q": "公開收購"}).json()
    assert r["count"] > 0
    assert all("url" in item for item in r["results"])


# --- deal flow ------------------------------------------------------------
def test_deal_flow_resolves_articles():
    from lawhub.ai.deal_flow import build_checklist
    steps = build_checklist(get_corpus())
    assert len(steps) >= 8
    # every referenced article resolved to a real URL
    for s in steps:
        for a in s["articles"]:
            assert a["url"].startswith("https://law.moj.gov.tw/")
    # the three phase-5 regulator gates are marked parallel
    parallel = [s for s in steps if s["parallel"]]
    assert len(parallel) == 3


def test_api_deal_flow():
    r = client.get("/api/deal-flow").json()
    assert r["count"] >= 8
    ftc = [s for s in r["steps"] if s["id"] == "ftc_merger"][0]
    assert any(a["no"] == "11" for a in ftc["articles"])
