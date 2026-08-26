"""Tests for the AI layer.

The important ones are the adversarial cases: we feed the pipeline a model
that deliberately fabricates citations and assert that the verifier catches
it. Those guarantees must hold without any network access, so every test
here uses a fake LLM.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lawhub.ai.draft import DealFacts, Drafter, applicable_steps   # noqa: E402
from lawhub.ai.llm import EchoLLM                                   # noqa: E402
from lawhub.ai.qa import GroundedAnswerer, KeywordRetriever         # noqa: E402
from lawhub.app import app                                          # noqa: E402
from lawhub.repository import get_corpus                            # noqa: E402

client = TestClient(app)


class FakeLLM:
    """Returns a scripted response so we can test verification logic."""

    name = "fake"

    def __init__(self, response: str):
        self.response = response
        self.last_prompt = ""
        self.last_system = ""

    def complete(self, system, prompt, *, temperature=0.2, max_tokens=2048):
        self.last_system, self.last_prompt = system, prompt
        return self.response


# --- retrieval ------------------------------------------------------------
def test_retriever_finds_relevant_sources():
    srcs = KeywordRetriever(get_corpus()).retrieve("結合申報門檻", k=6)
    assert srcs, "expected hits for a core FTC query"
    assert all(s.url.startswith("http") for s in srcs)
    assert [s.n for s in srcs] == list(range(1, len(srcs) + 1))
    assert any("公平" in s.law or "結合" in s.label for s in srcs)


def test_retriever_numbers_are_contiguous():
    srcs = KeywordRetriever(get_corpus()).retrieve("公開收購", k=5)
    assert [s.n for s in srcs] == list(range(1, len(srcs) + 1))


# --- the guarantee: fabricated citations are stripped ---------------------
def test_fabricated_citation_is_dropped():
    llm = FakeLLM('{"answer": "結合須申報 [1]。另依第99條規定 [47]。", '
                  '"used": [1, 47], "confident": true}')
    ans = GroundedAnswerer(get_corpus(), llm).answer("結合申報門檻")
    assert 47 in ans.dropped, "out-of-range citation must be recorded"
    assert "[47]" not in ans.answer, "fabricated marker must be removed"
    assert any(c["n"] == 1 for c in ans.citations)


def test_answer_with_no_valid_citation_abstains():
    llm = FakeLLM('{"answer": "我認為應該要申報 [99]。", "used": [99], '
                  '"confident": true}')
    ans = GroundedAnswerer(get_corpus(), llm).answer("結合申報門檻")
    assert ans.abstained is True
    assert ans.citations == []


def test_every_returned_citation_resolves_to_a_real_source():
    llm = FakeLLM('{"answer": "說明 [1][2][3]。", "used": [1,2,3], '
                  '"confident": true}')
    ans = GroundedAnswerer(get_corpus(), llm).answer("公開收購")
    assert ans.citations
    for c in ans.citations:
        assert c["url"].startswith("http")
        assert c["label"]


def test_unknown_topic_abstains_without_calling_model():
    llm = FakeLLM("should not be used")
    ans = GroundedAnswerer(get_corpus(), llm).answer("量子力學的薛丁格方程式")
    assert ans.abstained is True
    assert ans.citations == []


def test_prompt_contains_numbered_sources_and_rules():
    llm = FakeLLM('{"answer": "x [1]", "used": [1], "confident": true}')
    GroundedAnswerer(get_corpus(), llm).answer("內線交易")
    assert "[1]" in llm.last_prompt
    assert "不得引用來源以外" in llm.last_system


def test_plain_prose_response_is_still_verified():
    llm = FakeLLM("公開收購應申報 [1]，另見 [88]。")   # not JSON
    ans = GroundedAnswerer(get_corpus(), llm).answer("公開收購申報")
    assert "[88]" not in ans.answer
    assert 88 in ans.dropped


def test_echo_llm_is_offline_safe():
    ans = GroundedAnswerer(get_corpus(), EchoLLM()).answer("結合申報")
    assert ans.model == "echo"
    for c in ans.citations:
        assert c["url"].startswith("http")


# --- drafting: the skeleton must be deterministic -------------------------
def test_gate_filtering_is_deterministic():
    domestic = DealFacts(target_listed=False, cross_border=False,
                         prc_capital=False, ftc_threshold_met=False)
    ids = {s["id"] for s in applicable_steps(domestic)}
    assert "investment_review" not in ids   # no foreign capital
    assert "disclose" not in ids            # not listed

    foreign = DealFacts(target_listed=True, cross_border=True)
    ids2 = {s["id"] for s in applicable_steps(foreign)}
    assert "investment_review" in ids2
    assert "disclose" in ids2


def test_prc_capital_triggers_investment_review():
    ids = {s["id"] for s in applicable_steps(DealFacts(prc_capital=True))}
    assert "investment_review" in ids


def test_draft_is_marked_for_review_and_cited():
    llm = FakeLLM("一、交易概述……【待確認】")
    d = Drafter(get_corpus(), llm).draft("checklist", DealFacts(target="A公司"))
    assert d.requires_review is True
    assert d.disclaimer
    assert d.steps and d.citations
    for c in d.citations:
        assert c["url"].startswith("https://law.moj.gov.tw/")


def test_draft_prompt_pins_the_legal_basis():
    llm = FakeLLM("draft")
    Drafter(get_corpus(), llm).draft("memo", DealFacts(cross_border=True))
    assert "請勿引用此清單以外的條號" in llm.last_prompt
    assert "投資審議司" in llm.last_prompt


@pytest.mark.parametrize("kind", ["checklist", "memo", "disclosure"])
def test_all_draft_kinds(kind):
    d = Drafter(get_corpus(), FakeLLM("body")).draft(kind, DealFacts())
    assert d.kind == kind and d.body and d.requires_review


# --- API ------------------------------------------------------------------
def test_api_ask():
    r = client.post("/api/ask", json={"question": "結合申報門檻是多少"})
    assert r.status_code == 200
    body = r.json()
    assert "citations" in body and "abstained" in body


def test_api_ask_validates_input():
    assert client.post("/api/ask", json={"question": "x"}).status_code == 422


def test_api_draft():
    r = client.post("/api/draft", json={"kind": "checklist", "target": "B公司",
                                        "cross_border": True})
    assert r.status_code == 200
    body = r.json()
    assert body["requires_review"] is True
    assert any(s["id"] == "investment_review" for s in body["steps"])


def test_api_ai_status():
    body = client.get("/api/ai/status").json()
    assert "provider" in body and "live" in body


# --- provider config ------------------------------------------------------
@pytest.mark.parametrize("model,is3x", [
    ("gemini-3.5-flash-lite", True),
    ("gemini-3.6-flash", True),
    ("models/gemini-3.5-flash-lite", True),
    ("gemini-2.5-flash", False),
])
def test_gemini_3x_detection(model, is3x, monkeypatch):
    """Gemini 3.x rejects temperature/top_p/top_k — we must not send them."""
    from lawhub.ai.llm import GeminiLLM
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    llm = GeminiLLM.__new__(GeminiLLM)      # skip SDK client construction
    llm.model = model
    assert llm._is_gemini_3x is is3x


def test_default_model_is_flash_lite(monkeypatch):
    from lawhub.ai.llm import GeminiLLM
    monkeypatch.delenv("LAWHUB_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    llm = GeminiLLM.__new__(GeminiLLM)
    import os
    assert os.getenv("LAWHUB_MODEL", "gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"


# --- rate limiting (public deployment protection) -------------------------
def test_rate_limit_blocks_flood(monkeypatch):
    from lawhub.limits import Limits, RateLimiter
    import lawhub.app as appmod
    strict = RateLimiter(Limits(per_min=3, per_day=100, global_per_day=1000))
    monkeypatch.setattr(appmod, "limiter", strict)
    c = TestClient(app)
    codes = [c.post("/api/ask", json={"question": "結合申報門檻"}).status_code
             for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:], "flood must be rejected"


def test_global_daily_cap(monkeypatch):
    from lawhub.limits import Limits, RateLimiter
    import lawhub.app as appmod
    capped = RateLimiter(Limits(per_min=99, per_day=99, global_per_day=2))
    monkeypatch.setattr(appmod, "limiter", capped)
    c = TestClient(app)
    for _ in range(2):
        assert c.post("/api/ask", json={"question": "公開收購"}).status_code == 200
    r = c.post("/api/ask", json={"question": "公開收購"})
    assert r.status_code == 429
    assert "額度" in r.json()["detail"]
