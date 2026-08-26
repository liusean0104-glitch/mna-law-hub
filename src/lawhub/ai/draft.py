"""Draft generation — "幫你產生草稿", grounded and human-gated.

Three draft types that map to real deliverables in a Taiwan M&A deal:

``checklist``   法遵檢核清單 — built from the deal-flow graph, filtered by the
                deal's own facts (listed target? foreign/PRC capital? does the
                FTC threshold bite?). The *structure* is deterministic Python;
                the model only writes the prose commentary.
``memo``        交易架構備忘錄 — narrative memo over the same facts.
``disclosure``  重大訊息公告草稿 — skeleton for the MOPS announcement.

Design rule: **the skeleton is code, the prose is the model.** Anything
load-bearing (which gates apply, which articles govern, what the waiting
period is) comes from the corpus, not from generation. That keeps the
failure mode to "clumsy wording" rather than "missed a regulator".

Every draft carries ``requires_review=True``. Nothing here is filed,
published, or treated as legal advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..repository import Corpus, get_corpus
from .deal_flow import build_checklist
from .llm import LLM, get_llm

DraftKind = Literal["checklist", "memo", "disclosure"]

DISCLAIMER = ("本文件由系統依公開法規語料自動產生之草稿，非法律意見；"
              "所有條號、時限與適用結論均須由承辦人與律師覆核後始得使用。")

SYSTEM = """你是台灣併購法遵的資深承辦人，負責撰寫內部文件草稿。

規則：
1. 只根據提供的事實與法規依據撰寫，不得自行加入未提供的條號、日期或函釋字號。
2. 不確定或資料不足之處，寫「【待確認】」，不要臆測填空。
3. 用繁體中文、實務公文語氣，簡潔具體。
4. 這是草稿，供內部覆核使用，不是法律意見。"""


@dataclass
class DealFacts:
    """The deal parameters that decide which regulator gates apply."""

    target: str = "【標的公司】"
    acquirer: str = "【收購方】"
    structure: str = "合併"            # 合併 / 股份轉換 / 收購資產 / 公開收購
    target_listed: bool = True
    stake_pct: float = 100.0
    cross_border: bool = False         # 涉外資
    prc_capital: bool = False          # 涉陸資
    ftc_threshold_met: bool = True     # 是否達結合申報門檻
    consideration: str = "現金"
    notes: str = ""

    def summary(self) -> str:
        bits = [
            f"收購方：{self.acquirer}",
            f"標的：{self.target}（{'上市櫃' if self.target_listed else '非上市櫃'}）",
            f"架構：{self.structure}；對價：{self.consideration}",
            f"取得股權比例：{self.stake_pct}%",
            f"涉外資：{'是' if self.cross_border else '否'}；"
            f"涉陸資：{'是' if self.prc_capital else '否'}",
            f"是否達結合申報門檻：{'是' if self.ftc_threshold_met else '否/待評估'}",
        ]
        if self.notes:
            bits.append(f"備註：{self.notes}")
        return "\n".join(f"- {b}" for b in bits)


@dataclass
class Draft:
    kind: str
    title: str
    body: str
    steps: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    requires_review: bool = True
    disclaimer: str = DISCLAIMER
    model: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "title": self.title, "body": self.body,
            "steps": self.steps, "citations": self.citations,
            "requires_review": self.requires_review,
            "disclaimer": self.disclaimer, "model": self.model,
        }


def applicable_steps(facts: DealFacts, corpus: Corpus | None = None) -> list[dict]:
    """Filter the deal-flow graph down to the gates this deal actually hits.

    Deterministic — no model involved. This is the part that must not be
    wrong, so it is plain rules over the structured graph.
    """
    steps = build_checklist(corpus or get_corpus())
    out: list[dict] = []
    for s in steps:
        sid = s["id"]
        if sid == "tender_filing" and not (facts.target_listed
                                           and facts.structure in ("公開收購", "合併")):
            continue
        if sid == "disclose" and not facts.target_listed:
            continue
        if sid == "ftc_merger" and not facts.ftc_threshold_met:
            s = {**s, "detail": s["detail"] + "\n（本案初判未達申報門檻，"
                                              "仍請覆核第 11 條門檻計算。）"}
        if sid == "investment_review" and not (facts.cross_border or facts.prc_capital):
            continue
        out.append(s)
    return out


class Drafter:
    def __init__(self, corpus: Corpus | None = None, llm: LLM | None = None):
        self.corpus = corpus or get_corpus()
        self.llm = llm or get_llm()

    # --- shared ----------------------------------------------------------
    @staticmethod
    def _citations(steps: list[dict]) -> list[dict]:
        seen, out = set(), []
        for s in steps:
            for a in s["articles"]:
                if a["url"] in seen:
                    continue
                seen.add(a["url"])
                out.append(a)
        return out

    @staticmethod
    def _legal_basis(steps: list[dict]) -> str:
        lines = []
        for s in steps:
            refs = "、".join(f"{a['law']} §{a['no']}" for a in s["articles"]) or "—"
            lines.append(f"- [{s['phase']}] {s['title']}｜主管機關：{s['authority']}"
                         f"｜時程：{s['timing']}｜依據：{refs}")
        return "\n".join(lines)

    # --- draft types -----------------------------------------------------
    def checklist(self, facts: DealFacts) -> Draft:
        steps = applicable_steps(facts, self.corpus)
        prompt = (f"請就以下交易撰寫「法遵檢核清單」的說明段落。\n\n"
                  f"交易事實：\n{facts.summary()}\n\n"
                  f"適用關卡（已由系統依法規推導，請勿增刪關卡）：\n"
                  f"{self._legal_basis(steps)}\n\n"
                  f"請依序說明每個關卡的實務重點與應注意時程，"
                  f"並標明哪些關卡可平行進行。")
        body = self.llm.complete(SYSTEM, prompt, temperature=0.25)
        return Draft("checklist", f"{facts.target} 併購案 — 法遵檢核清單（草稿）",
                     body, steps, self._citations(steps),
                     model=getattr(self.llm, "name", "?"))

    def memo(self, facts: DealFacts) -> Draft:
        steps = applicable_steps(facts, self.corpus)
        prompt = (f"請撰寫一份內部「交易架構與法遵備忘錄」草稿。\n\n"
                  f"交易事實：\n{facts.summary()}\n\n"
                  f"法規依據（請勿引用此清單以外的條號）：\n"
                  f"{self._legal_basis(steps)}\n\n"
                  f"結構：一、交易概述　二、主要法遵關卡與時程　"
                  f"三、須提前準備事項　四、待確認事項。")
        body = self.llm.complete(SYSTEM, prompt, temperature=0.3, max_tokens=3000)
        return Draft("memo", f"{facts.target} 併購案 — 交易架構備忘錄（草稿）",
                     body, steps, self._citations(steps),
                     model=getattr(self.llm, "name", "?"))

    def disclosure(self, facts: DealFacts) -> Draft:
        steps = [s for s in applicable_steps(facts, self.corpus)
                 if s["id"] in ("disclose", "board", "special_cmte")]
        prompt = (f"請撰寫上市櫃公司「重大訊息公告」草稿，"
                  f"就董事會決議併購一事對外公告。\n\n"
                  f"交易事實：\n{facts.summary()}\n\n"
                  f"揭露依據：\n{self._legal_basis(steps)}\n\n"
                  f"請包含：1.事實發生日 2.公司名稱 3.事實內容 "
                  f"4.對公司財務業務影響 5.因應措施。"
                  f"未提供的具體數字一律寫【待確認】。")
        body = self.llm.complete(SYSTEM, prompt, temperature=0.2)
        return Draft("disclosure", f"{facts.target} 併購案 — 重大訊息公告（草稿）",
                     body, steps, self._citations(steps),
                     model=getattr(self.llm, "name", "?"))

    def draft(self, kind: DraftKind, facts: DealFacts) -> Draft:
        return {"checklist": self.checklist, "memo": self.memo,
                "disclosure": self.disclosure}[kind](facts)
