# DEPLOY — 公開這個網站

有兩種公開方式,差別在**要不要 AI 功能**。可以兩個都做。

---

## 選項 A:GitHub Pages(靜態版,無 AI)— 最簡單

**適合**:只想公開法規查詢工具,不需要 AI 問答。

**成本**:完全免費,無帳單風險,無伺服器要維護。

**限制**:AI 問答與草稿功能會顯示「此為靜態版本」的說明頁,無法使用
(因為它們需要伺服器呼叫模型 API)。

### 步驟

1. 把專案推到 GitHub(repo 需為 public,免費帳號才能用 Pages)。
2. GitHub 上進 **Settings → Pages → Source** 選 **GitHub Actions**。
3. 推一次 `main` 分支即可,`.github/workflows/pages.yml` 會自動建置部署。

網址會是:`https://<你的帳號>.github.io/<repo-名稱>/`

---

## 選項 B:含 AI 的完整版(需要伺服器)

**適合**:想讓別人也能用 AI 問答與草稿功能。

**⚠️ 先讀這段 — 關於成本**

你的 API 金鑰放在伺服器端,**不會**外洩給訪客,這點是安全的。但公開網址代表
**任何人都能呼叫你的 AI 端點,花的是你的 Gemini 額度**。爬蟲和惡意流量是真實
存在的。專案已內建三層保護,但你仍應自己確認:

| 保護 | 預設值 | 環境變數 |
| --- | --- | --- |
| 每 IP 每分鐘 | 5 次 | `LAWHUB_RATE_PER_MIN` |
| 每 IP 每日 | 40 次 | `LAWHUB_RATE_PER_DAY` |
| **全站每日總量** | 500 次 | `LAWHUB_GLOBAL_PER_DAY` |

最後一項是你的成本上限:全站一天最多 500 次呼叫,超過就回 429 並提示明日再試。

**另外務必做的事**:到 [Google AI Studio](https://aistudio.google.com/apikey) /
Google Cloud Console 為這把金鑰設定**用量上限或預算警示**。程式端的限制擋得住
一般濫用,但帳戶端的硬上限才是最後一道防線。Gemini 3.5 Flash-Lite 是目前
最便宜的一級,正常使用成本很低,但「公開網址 + 無上限」永遠是壞組合。

### B-1. Render(推薦,最省事)

免費方案會在閒置後休眠,第一個請求約需 30 秒喚醒 —— 對展示用途夠了。

1. 推到 GitHub。
2. 到 [render.com](https://render.com) → New → Web Service → 連結你的 repo。
3. Render 會讀取 `render.yaml` 自動設定(Docker 建置)。
4. **在 Render 儀表板的 Environment 頁面填入 `GEMINI_API_KEY`**
   (`render.yaml` 裡標了 `sync: false`,代表金鑰不進版控 —— 絕對不要把金鑰
   commit 進 git)。
5. Deploy。網址會是 `https://<name>.onrender.com`。

### B-2. Docker(Fly.io / Cloud Run / 自架 VPS)

```bash
docker build -t mna-law-hub .
docker run -p 8000:8000 \
  -e GEMINI_API_KEY=your-key \
  -e LAWHUB_MODEL=gemini-3.5-flash-lite \
  -e LAWHUB_PUBLIC=1 \
  mna-law-hub
```

Cloud Run 特別合適(按用量計費、可設最大實例數、與 Gemini 同一個 Google 帳戶):

```bash
gcloud run deploy mna-law-hub --source . \
  --region asia-east1 \
  --allow-unauthenticated \
  --max-instances 2 \
  --set-env-vars LAWHUB_PUBLIC=1,LAWHUB_MODEL=gemini-3.5-flash-lite \
  --set-secrets GEMINI_API_KEY=gemini-key:latest
```

`--max-instances 2` 是另一道成本保險。

---

## 公開前檢查清單

- [ ] `.env` **沒有**被 commit(`.gitignore` 已包含,但請自己確認一次
      `git log -p | grep -i api_key` 沒東西)
- [ ] 金鑰在雲端平台的環境變數裡設定,不在程式碼裡
- [ ] Google 帳戶端已設定用量上限或預算警示
- [ ] `LAWHUB_GLOBAL_PER_DAY` 設成你能接受的每日上限
- [ ] 頁尾免責聲明已顯示(預設已加入)
- [ ] 若金鑰曾不慎外流,立刻到 AI Studio **撤銷並重新產生**

## 關於免責聲明

網站頁尾已內建免責聲明,說明本站非法律意見、條文以官方原文為準、函釋為行政見解。
公開給不特定人使用時,這段文字請不要移除 —— 使用者可能不了解工具的限制,
而法律資訊被誤用的後果是實質的。

## 一個務實的建議

如果你的主要目的是**放進履歷或作品集**,選項 A(GitHub Pages)其實就夠了:
連結永遠可點、不會休眠、零成本、零風險,而 GitHub repo 本身就展示了完整的
AI 實作與工程能力。想 demo AI 功能時,再用 Render 開一個臨時網址即可。
