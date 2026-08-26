# 併購・公司治理 法規查詢台 — M&A / Corporate-Governance Law Hub

台灣併購與公司治理的法規查詢工具。整合六部核心法規、精選條文、官方問答／函釋，
以及跨主管機關的交易法遵流程。前端是零依賴的單頁應用，後端是以 Python 為單一資料
來源的 FastAPI 服務。

> **免責聲明**：本工具彙整之條文摘要與函釋連結僅供研究與實務導覽，非法律意見。
> 函釋為主管機關行政見解，個案仍應回到法條文義、法院判決與專業意見判斷。

## 收錄範圍

| 法規 | pcode | 說明 |
| --- | --- | --- |
| 公司法 | `J0080001` | 決議門檻、異議股東收買請求權 |
| 證券交易法 | `G0400001` | 公開收購、內線交易、重大訊息揭露 |
| 企業併購法 | `J0080041` | 合併/分割/收購/股份轉換專法 |
| 公開收購辦法 | `G0400063` | 公開收購申報與審議程序 |
| 公平交易法 | `J0150002` | 結合（merger control）申報 |
| 投審（外資/陸資） | `J0040002` / `Q0040015` / `Q0040001` | 外資、陸資、赴陸投資審查 |

共 6 部法規、60 條精選條文、36 個官方問答／函釋入口。

## 功能

- **法條指令列**：輸入 `證交 43-1`、`公平 11`、`外資 4` 直接跳到全國法規資料庫原文；
  投審跨三部法規，`外資`/`陸資`/`赴陸` 會分流到正確的 pcode。
- **關鍵字搜尋**：同時搜條文與問答函釋。
- **收藏（★）**：條文與問答皆可收藏，存於瀏覽器 localStorage。
- **深色模式、響應式、左目錄＋右內容**。
- **交易法遵流程**：`/api/deal-flow` 將併購程序編碼為結構化步驟（見下）。

## 快速開始

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 由 Python 資料來源產生前端資料檔
python scripts/export_web.py

# 啟動：API + 靜態前端都在同一個服務
uvicorn lawhub.app:app --reload
# 開 http://127.0.0.1:8000
```

只想開前端、不跑後端也可以：`scripts/export_web.py` 產生的 `web/data.js` 讓
`web/index.html` 直接用瀏覽器開啟就能運作（資料以 `window.__DATA__` 注入）。

開發與測試：

```bash
pip install -r requirements-dev.txt
pytest -q
```


## AI 功能

兩個功能已實作:**有引註的問答**與**產生草稿**。預設走 Gemini,未設金鑰時自動退回
離線模式(不會產生法律內容),因此測試與 CI 完全免金鑰、免網路、零成本。

### 設定

```bash
pip install -r requirements-ai.txt        # 含 google-genai
cp .env.example .env                      # 填入 GEMINI_API_KEY
export GEMINI_API_KEY=your-key-here       # 或用 .env
uvicorn lawhub.app:app --reload
```

金鑰申請:<https://aistudio.google.com/apikey>。想換模型改 `LAWHUB_MODEL`;想換
供應商(Claude/OpenAI/本地模型),在 `src/lawhub/ai/llm.py` 加一個實作 `LLM`
protocol 的類別即可,RAG 與草稿邏輯完全不用動。

預設模型是 **Gemini 3.5 Flash-Lite**(`gemini-3.5-flash-lite`)。注意 Gemini 3.x
不再接受 `temperature` / `top_p` / `top_k`,程式會依模型版本自動判斷是否送出這些
參數,所以換回 2.x 系列也不會壞。

### 有引註的問答 — 核心保證是「引註驗證」

流程是 **檢索 → 提示 → 驗證**:

1. 從語料庫檢索相關條文與官方問答,**編號**後交給模型。
2. 提示詞硬性要求:只能引用 `[n]` 編號的來源,答不出來就說答不出來。
3. **驗證(關鍵)**:用 Python 解析回答中的 `[n]`,逐一比對是否真的存在於我們
   提供的來源。捏造或超出範圍的引註會被**移除並記錄**;若沒有任何引註存活,
   整則回答標記為**拒答**。

第 3 步刻意用確定性的程式碼,不是再叫一次模型 —— 「每個引註都對得到真實官方
連結」這個保證,不能依賴 LLM 自己說了算。

實測:餵給它一個會亂編的模型,輸出 `[1][2][42][77]`,系統保留 `[1][2]`
(真實來源)、攔截 `[42][77]`(捏造)。這個行為有專門的測試守著。

### 產生草稿 — 骨架是程式,文字才是模型

三種草稿:法遵檢核清單、交易架構備忘錄、重大訊息公告。

設計原則:**攸關正確性的部分不交給模型**。哪些主管機關關卡適用(標的是否上市、
是否涉外資/陸資、是否達結合門檻)由 `applicable_steps()` 用規則推導,模型只負責
把說明文字寫順。這樣最壞情況是「文字寫得不漂亮」,而不是「漏掉一個主管機關」。

所有草稿都帶 `requires_review=True` 與免責聲明,不會自動對外發送。

### AI 端點

| 端點 | 說明 |
| --- | --- |
| `POST /api/ask` | 有引註問答(回傳 citations / abstained / dropped_citations) |
| `POST /api/draft` | 產生草稿(checklist / memo / disclosure) |
| `GET /api/ai/status` | 目前供應商與是否為真實模型 |

```bash
curl -X POST localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"結合申報門檻與等待期"}'
```


## API

| 端點 | 說明 |
| --- | --- |
| `GET /api/health` | 狀態與各項數量 |
| `GET /api/bootstrap` | 前端所需的 `{LAWS, PORTALS}` 全量資料 |
| `GET /api/laws` / `GET /api/laws/{key}` | 法規清單／單一法規 |
| `GET /api/search?q=` | 搜尋條文與問答函釋 |
| `GET /api/jump?cmd=證交 43-1` | 解析指令列並回傳深連結 |
| `GET /api/deal-flow` | 併購法遵流程（結構化步驟＋條文連結） |


## 公開部署

完整說明見 [`docs/DEPLOY.md`](docs/DEPLOY.md)。兩種方式:

**A. GitHub Pages(靜態版,無 AI)** — 免費、零風險。推到 GitHub 後在
Settings → Pages 選 GitHub Actions 即可,`.github/workflows/pages.yml` 會自動部署。
AI 頁面會顯示「靜態版本」說明,法規查詢功能完全正常。

**B. 含 AI 的完整版** — 需要伺服器。附了 `Dockerfile` 與 `render.yaml`
(Render 一鍵部署),也可用 Fly.io / Cloud Run。

> ⚠️ **公開前必讀**:金鑰放在伺服器端不會外洩,但**任何人都能呼叫你的 AI 端點,
> 花的是你的額度**。專案已內建每 IP 每分鐘/每日限制與**全站每日總量上限**
> (預設 500 次,可用 `LAWHUB_GLOBAL_PER_DAY` 調整),但仍請務必到 Google 帳戶端
> 設定用量上限或預算警示。詳見 DEPLOY.md 的檢查清單。


## 專案結構

```
mna-law-hub/
├── src/lawhub/
│   ├── models.py          # Law / Article / Resource dataclasses
│   ├── repository.py      # 載入語料、搜尋、指令解析（單一讀取路徑）
│   ├── serialize.py       # 模型 → 前端 JSON 契約
│   ├── app.py             # FastAPI：API + 靜態前端
│   ├── data/laws.json     # ★ 單一資料來源（canonical corpus）
│   └── ai/
│       ├── llm.py         # 供應商抽象（Gemini 預設，可替換）
│       ├── qa.py          # 有引註問答 + 引註驗證
│       ├── draft.py       # 草稿產生（關卡推導為確定性程式）
│       ├── deal_flow.py   # 併購程序知識圖
│       └── retrieval.py   # RAG 介面契約
├── web/                   # 零依賴前端（index.html / styles.css / app.js / ai.js）
│   └── data.js            # 由 scripts/export_web.py 產生
├── scripts/export_web.py  # Python 語料 → web/data.js
├── tests/                 # pytest（語料邏輯＋API）
└── docs/ROADMAP.md        # 進化到 AI 原生產品的路線圖
```

## 架構

Python 端是**單一資料來源**。條文與函釋維護於 `data/laws.json`，經 `repository`
載入為型別化模型，同時供給三個出口：REST API、靜態前端（透過 `export_web.py`）、
以及測試。這個設計讓語料只需維護一處，也讓未來的 AI 功能（語意檢索、代理、接地
問答）建立在同一份型別化資料上，而不是去爬 HTML。

```
        data/laws.json  (canonical)
                │
          repository.py  ── search / parse_command / deal-flow
                │
      ┌─────────┼──────────────┐
   FastAPI   export_web.py    tests
   /api/*     web/data.js
                │
          web/ 靜態前端
```

## 如何演進成 AI 產品

見 [`docs/ROADMAP.md`](docs/ROADMAP.md) — 圍繞三條主軸：深度領域 AI、
AI 原生產品與營運、自主且具適應能力的 AI。核心原則是 **cite-or-abstain**：
法律領域的 AI 必須每個結論都可回溯官方來源，無法接地時就拒答。
