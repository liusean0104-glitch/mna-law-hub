/* AI layer UI — grounded Q&A and draft generation.
   Kept in its own file so the original app.js stays untouched. */

const API = (window.__API_BASE__ || "");
let aiStatus = { live: false, provider: "?" };

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}

/* ---------- sidebar nav ---------- */
function renderAiNav() {
  const el = document.getElementById("aiNav");
  if (!el) return;
  const items = [
    { id: "ask", label: "有引註問答", icon: "◈" },
    { id: "draft", label: "產生草稿", icon: "▤" },
  ];
  el.innerHTML = "";
  items.forEach((it) => {
    const b = document.createElement("button");
    b.className = "nav-law" + (view.mode === it.id ? " active" : "");
    b.style.setProperty("--accent", "var(--gold)");
    b.innerHTML = `<span class="spine"></span><span class="nm">${it.icon}　${it.label}</span>`;
    b.onclick = () => { openAi(it.id); closeDrawer && closeDrawer(); };
    el.appendChild(b);
  });
}

function openAi(mode) {
  view = { mode, law: null, tab: "art", query: "" };
  renderLawNav(); renderAiNav(); renderFavs();
  const m = document.getElementById("main");
  m.innerHTML = "";
  if (!apiAvailable) return renderStaticNotice(m, mode);
  mode === "ask" ? renderAsk(m) : renderDraft(m);
  window.scrollTo(0, 0);
}

function renderStaticNotice(m, mode) {
  const label = mode === "ask" ? "有引註的問答" : "產生草稿";
  m.innerHTML = `
    <div class="breadcrumb">AI 助理 · ${label}</div>
    <h1 class="page-h">${label}</h1>
    <p class="page-sub">這個頁面是<b>靜態版本</b>，只提供法規查詢功能。
      AI 功能需要後端伺服器（會呼叫模型 API），無法在純靜態網站上執行。</p>
    <div class="ai-warn">
      想使用 AI 功能，請依 <code>docs/DEPLOY.md</code> 自行部署一份含後端的服務，
      並設定自己的 <code>GEMINI_API_KEY</code>；或在本機執行
      <code>uvicorn lawhub.app:app</code>。
    </div>
    <div class="fulltext">
      <b>本站可用的功能：</b>六部法規的條文速查與深連結、關鍵字搜尋、
      官方問答與函釋入口、收藏、深色模式。左側選單即可使用。
    </div>`;
  window.scrollTo(0, 0);
}

function statusBanner() {
  if (aiStatus.live) return "";
  return `<div class="ai-warn">⚠️ 目前為<b>離線示範模式</b>（未偵測到 API 金鑰）。
    設定環境變數 <code>GEMINI_API_KEY</code> 後重啟服務即可啟用真實模型。
    離線模式不會產生法律分析內容。</div>`;
}

/* ---------- Q&A ---------- */
function renderAsk(m) {
  m.innerHTML = `
    <div class="breadcrumb">AI 助理 · 有引註問答</div>
    <h1 class="page-h">有引註的問答</h1>
    <p class="page-sub">回答只能引用本語料庫中的條文與官方問答，
      每個主張都附可點擊的來源；無法對應到來源時會直接拒答，不會臆測。</p>
    ${statusBanner()}
    <div class="ai-box">
      <textarea id="askQ" class="ai-input" rows="3"
        placeholder="例如：達到什麼門檻的併購要向公平會申報結合？等待期多久？"></textarea>
      <div class="ai-row">
        <div class="ai-chips" id="askChips"></div>
        <button class="ai-btn" id="askBtn">送出提問</button>
      </div>
    </div>
    <div id="askOut"></div>`;

  const chips = ["結合申報門檻與等待期", "強制公開收購的門檻", "異議股東收買請求權",
                 "陸資投資需要許可嗎", "併購時董事的忠實義務"];
  const cEl = m.querySelector("#askChips");
  chips.forEach((c) => {
    const b = document.createElement("button");
    b.className = "ai-chip"; b.textContent = c;
    b.onclick = () => { m.querySelector("#askQ").value = c; doAsk(); };
    cEl.appendChild(b);
  });
  m.querySelector("#askBtn").onclick = doAsk;
  m.querySelector("#askQ").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) doAsk();
  });
}

async function doAsk() {
  const q = document.getElementById("askQ").value.trim();
  const out = document.getElementById("askOut");
  if (!q) return;
  out.innerHTML = `<div class="ai-loading">檢索語料並產生回答中…</div>`;
  try {
    const r = await api("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    renderAnswer(out, r);
  } catch (e) {
    out.innerHTML = `<div class="ai-warn">呼叫失敗：${escapeHtml(String(e.message || e))}</div>`;
  }
}

function renderAnswer(out, r) {
  const cites = r.citations || [];
  const byN = Object.fromEntries(cites.map((c) => [c.n, c]));
  // turn [n] markers into clickable superscripts
  const body = escapeHtml(r.answer).replace(/\[(\d+)\]/g, (mm, n) => {
    const c = byN[n];
    if (!c) return "";
    return `<a class="cite-mark" href="${c.url}" target="_blank" rel="noopener"
              title="${escapeHtml(c.label)}">${n}</a>`;
  }).replace(/\n/g, "<br>");

  const banner = r.abstained
    ? `<div class="ai-abstain">🚫 <b>已拒答</b>：來源不足以支撐結論。這是刻意的設計 ——
         寧可不答，也不臆測條號。</div>` : "";

  const dropped = (r.dropped_citations || []).length
    ? `<div class="ai-dropped">🛡️ 已攔截 ${r.dropped_citations.length} 個無法對應到來源的引註
         （${r.dropped_citations.join(", ")}），已自動移除。</div>` : "";

  out.innerHTML = `
    ${banner}
    <div class="ai-answer">${body}</div>
    ${dropped}
    ${cites.length ? `
      <div class="section-head" style="margin-top:26px"><h2>引註來源</h2>
        <span class="count">${cites.length} 筆</span></div>
      <div class="qa-list">
        ${cites.map((c) => `
          <a class="qa" href="${c.url}" target="_blank" rel="noopener"
             style="--accent:var(--gold)">
            <div class="qa-head"><span class="qa-kind">[${c.n}]</span>
              <span class="qa-src">${escapeHtml(c.law)}</span>
              <span class="qa-ext">↗</span></div>
            <div class="qa-t">${escapeHtml(c.label)}</div>
          </a>`).join("")}
      </div>` : ""}
    <div class="fulltext" style="margin-top:24px">
      <b>提醒：</b>這是法規研究整理，不是法律意見。模型：${escapeHtml(r.model || "?")}，
      檢索來源 ${r.sources_considered || 0} 筆。結論仍請覆核官方原文。
    </div>`;
}

/* ---------- Draft ---------- */
function renderDraft(m) {
  m.innerHTML = `
    <div class="breadcrumb">AI 助理 · 產生草稿</div>
    <h1 class="page-h">產生草稿</h1>
    <p class="page-sub">填入交易事實，系統先以程式推導適用的主管機關關卡（這部分不交給模型），
      再由模型撰寫說明文字。所有產出都標記為<b>待人工覆核</b>。</p>
    ${statusBanner()}
    <div class="ai-box">
      <div class="form-grid">
        <label>文件類型
          <select id="dKind">
            <option value="checklist">法遵檢核清單</option>
            <option value="memo">交易架構備忘錄</option>
            <option value="disclosure">重大訊息公告</option>
          </select></label>
        <label>收購方 <input id="dAcq" value="甲公司"></label>
        <label>標的公司 <input id="dTgt" value="乙公司"></label>
        <label>交易架構
          <select id="dStruct">
            <option>合併</option><option>公開收購</option>
            <option>股份轉換</option><option>收購資產</option>
          </select></label>
        <label>對價
          <select id="dCons"><option>現金</option><option>換股</option>
            <option>現金加股份</option></select></label>
        <label>取得股權 %<input id="dPct" type="number" value="100" min="0" max="100"></label>
      </div>
      <div class="check-row">
        <label><input type="checkbox" id="dListed" checked> 標的為上市櫃公司</label>
        <label><input type="checkbox" id="dFtc" checked> 達結合申報門檻</label>
        <label><input type="checkbox" id="dCross"> 涉外資</label>
        <label><input type="checkbox" id="dPrc"> 涉陸資</label>
      </div>
      <label class="full">補充說明
        <input id="dNotes" placeholder="選填，例如：標的持有特許執照"></label>
      <div class="ai-row"><span></span>
        <button class="ai-btn" id="dBtn">產生草稿</button></div>
    </div>
    <div id="dOut"></div>`;
  m.querySelector("#dBtn").onclick = doDraft;
}

async function doDraft() {
  const g = (id) => document.getElementById(id);
  const out = document.getElementById("dOut");
  out.innerHTML = `<div class="ai-loading">推導適用關卡並撰寫草稿中…</div>`;
  const payload = {
    kind: g("dKind").value, acquirer: g("dAcq").value, target: g("dTgt").value,
    structure: g("dStruct").value, consideration: g("dCons").value,
    stake_pct: parseFloat(g("dPct").value || "100"),
    target_listed: g("dListed").checked, ftc_threshold_met: g("dFtc").checked,
    cross_border: g("dCross").checked, prc_capital: g("dPrc").checked,
    notes: g("dNotes").value,
  };
  try {
    const r = await api("/api/draft", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderDraftOut(out, r);
  } catch (e) {
    out.innerHTML = `<div class="ai-warn">呼叫失敗：${escapeHtml(String(e.message || e))}</div>`;
  }
}

function renderDraftOut(out, r) {
  const steps = r.steps || [];
  out.innerHTML = `
    <div class="ai-review">📝 <b>草稿 — 待人工覆核</b>　${escapeHtml(r.disclaimer)}</div>
    <div class="section-head" style="margin-top:22px"><h2>${escapeHtml(r.title)}</h2></div>
    <div class="ai-answer">${escapeHtml(r.body).replace(/\n/g, "<br>")}</div>

    <div class="section-head" style="margin-top:28px"><h2>適用關卡</h2>
      <span class="count">${steps.length} 項（由程式推導）</span></div>
    <div class="flow-list">
      ${steps.map((s) => `
        <div class="flow-step">
          <div class="flow-top">
            <span class="flow-phase">${escapeHtml(s.phase)}</span>
            <b>${escapeHtml(s.title)}</b>
            ${s.parallel ? '<span class="flow-par">可平行</span>' : ""}
          </div>
          <div class="flow-meta">主管機關：${escapeHtml(s.authority)}　·　時程：${escapeHtml(s.timing)}</div>
          <div class="flow-detail">${escapeHtml(s.detail).replace(/\n/g, "<br>")}</div>
          <div class="flow-refs">
            ${(s.articles || []).map((a) => `
              <a href="${a.url}" target="_blank" rel="noopener">${escapeHtml(a.law)} §${a.no}</a>`).join("")}
          </div>
        </div>`).join("")}
    </div>
    <div class="ai-row" style="margin-top:20px">
      <span></span>
      <button class="ai-btn ghost" onclick="copyDraft()">複製草稿全文</button>
    </div>
    <textarea id="draftRaw" style="position:absolute;left:-9999px">${escapeHtml(r.title)}\n\n${escapeHtml(r.body)}\n\n${escapeHtml(r.disclaimer)}</textarea>`;
}

function copyDraft() {
  const t = document.getElementById("draftRaw");
  t.style.position = "static";
  t.select();
  document.execCommand("copy");
  t.style.position = "absolute";
}

/* ---------- boot ---------- */
let apiAvailable = true;

(async function initAi() {
  if (window.__STATIC_BUILD__) {
    apiAvailable = false;
    renderAiNav();
    return;
  }
  try {
    aiStatus = await api("/api/ai/status");
  } catch {
    apiAvailable = false;   // served as static files, no backend
  }
  renderAiNav();
})();
