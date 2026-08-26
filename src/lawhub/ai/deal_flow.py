"""Structured M&A compliance procedure — the "deep-domain" knowledge layer.

A statute lookup answers *"what does §X say"*. Practitioners actually ask
*"I'm buying a listed company — what must I do, in what order, and by
when?"*. That is procedural knowledge, not text. This module encodes the
Taiwan public-company M&A compliance path as a graph of steps, each linked
back to the concrete articles in the corpus.

It is data, not prose, so it can drive: a checklist generator, an agent's
plan, a timeline, and (later) a reasoning engine that checks whether a
given deal has cleared each gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..repository import Corpus, get_corpus


@dataclass(frozen=True)
class Step:
    id: str
    phase: str
    title: str
    detail: str
    authority: str                       # who the gate is with
    timing: str                          # typical statutory clock
    refs: tuple[tuple[str, str], ...] = ()   # (law_key, article_no)
    parallel: bool = False               # runs concurrently with siblings


# The canonical path for acquiring a Taiwan listed company. Ordered; a few
# regulator gates in PHASE 4 run in parallel (parallel=True).
STEPS: tuple[Step, ...] = (
    Step("kickoff", "1 評估", "啟動與保密",
         "董事會啟動評估、簽署保密協議、展開實地查核（due diligence）。",
         "內部", "交易前期",
         refs=(("company", "202"),)),
    Step("board", "2 決議", "董事會決議與利益迴避",
         "董事就併購案盡善良管理人注意義務；有利害關係之董事應揭露並迴避。",
         "董事會", "董事會決議日",
         refs=(("company", "206"), ("ma", "5"))),
    Step("special_cmte", "3 審議", "特別委員會 / 審議委員會 + 獨立專家意見",
         "設特別委員會審議併購（企併法），被收購公司設審議委員會（公開收購）；"
         "取得獨立專家對對價合理性之意見書。",
         "特別/審議委員會", "股東會或應賣前",
         refs=(("ma", "6"), ("tender", "14"), ("tender", "14-1"))),
    Step("disclose", "4 揭露", "重大訊息即時揭露",
         "董事會決議合併/分割/收購/股份轉換屬應公開之重大訊息，須依時限輸入公開資訊觀測站。",
         "證交所 / 金管會", "事實發生日次一營業日交易開始前二小時等",
         refs=(("sea", "36"),)),

    # --- Phase 5: regulator gates, largely concurrent --------------------
    Step("tender_filing", "5 主管機關", "公開收購申報（如採公開收購）",
         "達門檻之股權取得應以公開收購為之，向金管會申報並交付說明書。",
         "金管會 / 證期局", "申報生效制", parallel=True,
         refs=(("sea", "43-1"), ("tender", "7"), ("tender", "9"))),
    Step("ftc_merger", "5 主管機關", "公平會結合申報",
         "達銷售金額/市占門檻之結合須申報；受理完整資料後 30 工作日內不得結合，"
         "得延長至 60 工作日。第 12 條列無須申報之情形。",
         "公平交易委員會", "30（可延長至 60）工作日等待期", parallel=True,
         refs=(("ftc", "11"), ("ftc", "12"), ("ftc", "13"))),
    Step("investment_review", "5 主管機關", "投審核准（如涉外資 / 陸資）",
         "外國人或陸資取得我國公司股權達門檻須先經核准；陸資另有國安審查。",
         "經濟部投資審議司", "外資約 1–2 個月核定；陸資另有審查", parallel=True,
         refs=(("invest", "8"), ("invest", "4"))),

    Step("shareholder", "6 股東會", "股東會決議與異議股東收買請求權",
         "合併/分割/重大營業行為須股東會特別決議；反對股東得請求公司按公平價格收買其股份。",
         "股東會", "股東會日",
         refs=(("company", "185"), ("company", "316"), ("company", "317"),
               ("ma", "12"), ("ma", "18"))),
    Step("closing", "7 交割", "交割與變更登記",
         "對價交付、股權/資產移轉、公司變更登記與後續整併。",
         "經濟部商業發展署", "交割後",
         refs=(("company", "156-3"),)),
)


@dataclass
class ChecklistItem:
    step: Step
    articles: list[dict] = field(default_factory=list)


def build_checklist(corpus: Corpus | None = None) -> list[dict]:
    """Return the deal flow with each ref resolved to a live article + URL."""
    c = corpus or get_corpus()
    out: list[dict] = []
    for s in STEPS:
        articles = []
        for law_key, no in s.refs:
            law = c.laws.get(law_key)
            if not law:
                continue
            art = next((a for a in law.articles if a.no == no), None)
            if not art:
                continue
            articles.append({
                "law": art.label_for(law.name),
                "law_key": law_key,
                "no": art.no,
                "title": art.title,
                "url": art.url(law.code),
            })
        out.append({
            "id": s.id, "phase": s.phase, "title": s.title, "detail": s.detail,
            "authority": s.authority, "timing": s.timing,
            "parallel": s.parallel, "articles": articles,
        })
    return out
