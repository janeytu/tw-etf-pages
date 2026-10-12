# tw-etf-pages

台灣**主動式／被動式 ETF**每日**持股異動**靜態報告（非股價）。

觀察清單：`00981A`、`00988A`、`00991A`、`00403A`、`00992A`、`00405A`、`00406A`、`00980A`、`00985A`、`00982A`、`00984A`、`00993A`、`00400A`、`00401A`、`00987A`、`00408A`、`00994A`、`00995A`、`00996A`、`00999A`、`0050`、`0056`、`00713`、`00881`、`00878`、`00918`、`00919`、`00929`、`00939`、`00940`、`009816`。

每個交易日對每檔 ETF，與**前一份已歸檔快照**比較股數，產出：

1. **第一次買**（新建倉）
2. **加碼**（含連續加碼天數）
3. **減碼**（含連續減碼天數）
4. **全部出清**

靜態 HTML 透過 **GitHub Pages** 發布；持股 JSON 快照自行歸檔於 `data/snapshots/`。

### GitHub 歸檔（每日持股清單）

每個交易日 Actions 會把下列路徑 **commit 進本 repo**（並部署 Pages）：

| 路徑 | 內容 |
|------|------|
| `data/snapshots/{TICKER}/YYYY-MM-DD.json` | 當日完整持股清單（輕量 JSON，**歸檔主體**） |
| `data/changes/{TICKER}/YYYY-MM-DD.json` | 與前一已歸檔日比較的買賣異動報告 |
| `data/last_run.json` | 最近一次 pipeline 狀態 |
| `site/` | 靜態頁面（含 `site/data/{TICKER}-changes.json` 供日期選單） |

- 原始 Excel 位於 `data/raw/`，預設 **gitignore**（避免二元檔膨脹）。若需原始檔可從發行人重新下載；**以 JSON 快照為準**。
- Workflow（週一至週五台灣 18:00）執行 `python -m tw_etf_pages run` 後 `git add data/snapshots data/changes data/last_run.json site` 並 push。
- 瀏覽歷史：GitHub 上直接開啟上述路徑，或在 Pages 明細頁用「異動資料日」下拉選單切換。

### 日期選單（買賣清單）

各檔 `site/{TICKER}.html`（優先 `00981A`）提供 **異動資料日** `<select>`：

- 列出 `data/changes/{TICKER}/` 所有可對比日（新→舊）；僅 1–2 日也會顯示選單。
- 切換後以客戶端 JS 更新「新建倉／加碼／減碼／全部出清」異動表，並顯示該日的 `as_of_date` 與 `prev_as_of_date`。
- 支援網址 `?date=YYYY-MM-DD`；總覽頁各 ETF 區塊的日期選單會連到明細頁並帶此參數。


### 頁面配置（日報風格）

`site/index.html` 為單頁日報，含：

1. **Sticky 目錄**：跳至「新增／剔除」、各檔 `act_{TICKER}`、水位彙總。
2. **整體新增／剔除**：跨觀察清單彙整新建倉與全部出清。
3. **主動型 ETF 變動專區**：每檔表列「代號／名稱／今天部位（張）／權重(%)／變動狀態」；狀態含新建倉、加碼(連N天)、減碼(連N天)、全部出清；預設只看異動，可切換全部持股。
4. **水位變動**：依股票代號跨 ETF 淨股數變動，細節列含 `連N買`／`連N賣`。

**刻意省略**：AUM 規模、申贖張數、淨買超金額、處置預估等（無可靠來源，不造假；頁面標示「尚無資料」）。

本機預覽：`python -m tw_etf_pages render` 後以瀏覽器開啟 `site/index.html`（或 `python -m http.server -d site`）。

### 近20天持股趨勢（ETF 明細頁）

各檔 `site/{TICKER}.html` 新增 **「近20天持股趨勢」** 區塊：

- 依 `data/snapshots/{TICKER}/` 已歸檔日，組出每檔持股的股數時間序列（最多 20 個交易日；不足則用現有天數）。
- Chart.js（CDN）折線圖；可多選標的，並以「間歇加碼」（加碼→間隔→再加碼）優先列出。
- **稀疏歷史友善**：統一投信僅最新 Excel、目前可能只有 1–2 日時仍顯示空狀態／提示；隨 GitHub Actions 每日歸檔自動變完整。

#### 歷史回補說明（00981A 等統一投信）

| 發行人 | 歷史 Excel | 本站作法 |
|--------|------------|----------|
| **統一（uni）** `00981A`／`00988A`／`00403A`／`00939` | **僅最新一日**（`AssetExcelNPOI`），無公開依日期回補 API；zdsetf 亦無 history（被動 `00939` 404） | **無法一次回補 20 日**。主動檔與被動 `00939`（`46YTW`）同走 ezmoney Excel；靠每日 Actions 累積。 |
| **復華（fh）** `00991A`／`00929` | URL 帶 `YYYYMMDD`，可下載歷史；zdsetf **不收錄**被動 `00929` | 可選擇性回補。主動 `00991A`（`ETF23`）本 repo 已歸檔約 20 個交易日；被動 `00929`（`ETF21`）同官網 `api/assetsExcel`，靠每日 Actions 累積（可依日期回補）。 |
| **群益（capital）** `00992A`／`00982A`／`00919` | 無公開 Excel／依日期 API；zdsetf 收錄主動檔、**不收錄**被動 `00919` | **無法一次回補**。主動檔以 zdsetf 鏡像官網；被動 `00919` 以官網 CFWeb `/api/etf/buyback`（fundId=`195`；真實股數＋權重）歸檔。靠每日 Actions 累積；異動資料日選單仍最多 10 日。 |
| **富邦（fubon）** `00405A` | 官網投組頁有 ASP.NET 下載鈕，無穩定公開 Excel／CSV URL；zdsetf 僅最新一日 | **無法一次回補**。以 zdsetf 鏡像富邦官網投組歸檔，靠每日 Actions 累積；異動資料日選單仍最多 10 日。 |
| **中信（ctbc）** `00406A`／`00995A` | 官網 PCF／投組頁無穩定公開 Excel／CSV API；zdsetf 僅最新一日 | **無法一次回補**。以 zdsetf 鏡像中信官網 PCF 頁歸檔，靠每日 Actions 累積；異動資料日選單仍最多 10 日。 |
| **野村（nomura）** `00980A`／`00985A`／`00999A` | 官網投組頁（SPA）無穩定公開 Excel／CSV API；zdsetf 僅最新一日 | **無法一次回補**。以 zdsetf 鏡像野村官網投組頁歸檔，靠每日 Actions 累積；異動資料日選單仍最多 10 日。 |
| **安聯（allianz）** `00984A`／`00993A` | 官網投組頁無穩定公開 Excel／CSV API；zdsetf 僅最新一日 | **無法一次回補**。以 zdsetf 鏡像安聯官網投組頁歸檔，靠每日 Actions 累積；異動資料日選單仍最多 10 日。 |
| **國泰（cathay）** `00400A`／`00881`／`00878` | 官網投組頁無穩定公開 Excel／CSV；zdsetf **不收錄**被動 `00881`／`00878`（主動 `00400A` 可） | **無法一次回補**。`00400A` 以 zdsetf 鏡像官網；`00881`／`00878` 以官網 cwapi `GetIndexStockWeights`（fundCode=`CR`／`CN`）歸檔權重，股數為 weight×1e6 合成。靠每日 Actions 累積。 |
| **摩根（jpm）** `00401A` | 官網產品／PCF 無穩定公開 Excel／CSV API；zdsetf 僅最新一日；權重可能為 null | **無法一次回補**。以 zdsetf 鏡像摩根官網 PCF／投組歸檔，靠每日 Actions 累積；異動資料日選單仍最多 10 日。權重 null 正規化為 0.0（不臆造）。 |
| **台新（taishin）** `00987A` | 官網 PCF／投組頁無穩定公開 Excel／CSV API；zdsetf 僅最新一日；權重可能為 null | **無法一次回補**。以 zdsetf 鏡像台新官網 PCF／投組歸檔，靠每日 Actions 累積；異動資料日選單仍最多 10 日。權重 null 正規化為 0.0（不臆造）。 |
| **第一金（fsitc）** `00408A`／`00994A` | 官網投組頁無穩定公開 Excel／CSV API；zdsetf 僅最新一日 | **無法一次回補**。以 zdsetf 鏡像第一金官網投組頁歸檔，靠每日 Actions 累積；異動資料日選單仍最多 10 日。 |
| **兆豐（mega）** `00996A` | 官網投組頁無穩定公開 Excel／CSV API；zdsetf 僅最新一日 | **無法一次回補**。以 zdsetf 鏡像兆豐官網投組頁歸檔，靠每日 Actions 累積；異動資料日選單仍最多 10 日。 |
| **元大（yuanta）** `0050`／`0056`／`00713`／`00940` | 官網持股比重頁（Nuxt SSR）無公開 Excel／CSV；zdsetf **不收錄**被動 ETF | **無法一次回補**。以官網 `product/detail/{TICKER}/ratio` SSR `__NUXT__` 抽取 FundWeights；被動指數型日調倉少，日對日異動常為空。需 Node.js。 |
| **大華銀（uobam）** `00918` | 官網 PCF API；zdsetf **不收錄**被動 `00918` | **無法一次回補**。以官網 ServiceStack `WebSitePcfRequest?fundID=`（fund_code=`88329556`）歸檔；含真實股數 qty 與權重；略過 Cash／Margin。部分環境 SSL 中繼憑證不全時 verify=False。靠每日 Actions 累積。 |
| **凱基（kgi）** `009816` | 官網基金頁 HTML（無公開 Excel／CSV）；zdsetf **不收錄**被動 `009816` | **無法一次回補**。以官網 `Fund/Detail?fundID=J023` 伺服器端渲染的「持股比重」股票表歸檔；含真實股數與權重；略過期貨／現金。靠每日 Actions 累積。 |



---

## 快速開始（本機離線 dry-run）

不需網路；使用 `samples/` 內已下載的發行人 Excel：

```bash
cd tw-etf-pages
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -m tw_etf_pages dry-run
# 或：./scripts/dry_run.sh
```

產出：`site/index.html` 與各檔 `site/{TICKER}.html`。

線上抓取（需能連到投信官網）：

```bash
python -m tw_etf_pages run
```

僅依既有 `data/` 重繪頁面：

```bash
python -m tw_etf_pages render
```

---

## 如何 Fork 並啟用 GitHub Pages

1. Fork（或複製）本 repo，保持公開（發行人 endpoints 無需密鑰）。
2. **Settings → Pages → Build and deployment → Source：GitHub Actions**。
3. 首次可到 **Actions → Update ETF holdings → Run workflow** 手動觸發。
4. Workflow 會：安裝依賴 → `python -m tw_etf_pages run` → commit `data/` 與 `site/` → 以 `actions/upload-pages-artifact` + `actions/deploy-pages` 部署。
5. 權限已在 `.github/workflows/update.yml` 宣告：`contents: write`、`pages: write`、`id-token: write`。若 org 限制 Actions 權限，請在 repo Settings → Actions → General 允許 read/write。

排程：週一至週五 **台灣時間 18:00**（cron `0 10 * * 1-5` UTC），另支援 `workflow_dispatch`。

---

## 變更觀察清單

編輯根目錄 [`config.yaml`](config.yaml)：

```yaml
etfs:
  - ticker: "00981A"
    name: "主動統一台股增長"
    issuer: uni          # uni | fh | capital | fubon | ctbc | nomura | allianz | cathay | jpm | taishin | fsitc | mega | yuanta | uobam | kgi
    fund_code: "49YTW"   # 統一 fundCode 或復華 ETF23／ETF21
    source_page: "https://..."
```

- 統一投信：`issuer: uni`，`fund_code` 為 ezmoney 的 `fundCode`（本專案主動 `00981A`／`00988A`／`00403A` 為 `49YTW`／`61YTW`／`63YTW`；被動 `00939` 統一台灣高息動能為 `46YTW`）；zdsetf 不收錄被動 `00939`。
- 復華投信：`issuer: fh`，`fund_code` 為路徑中的產品碼（本專案主動 `00991A` 為 `ETF23`、被動 `00929` 為 `ETF21`）；官網 `api/assetsExcel/{fund_code}/{YYYYMMDD}`；zdsetf 不收錄被動 `00929`。
- 群益投信：`issuer: capital`，`fund_code` 為官網產品 id（本專案 `00992A` 為 `500`、`00982A` 為 `399`、被動 `00919` 為 `195`）；無公開 Excel API。抓取先試 zdsetf，失敗則改官網 CFWeb `POST /api/etf/buyback`（真實股數＋權重；`source_page` → capitalfund.com.tw `/etf/product/detail/{id}/portfolio`）。
- 富邦投信：`issuer: fubon`，`fund_code` 為股票代號（本專案 `00405A`）；無穩定公開 Excel／CSV，抓取走 zdsetf 鏡像官網投組（`source_url` → websys.fsit.com.tw）。
- 中國信託投信：`issuer: ctbc`，`fund_code` 為股票代號（本專案 `00406A`／`00995A`）；無穩定公開 Excel／CSV，抓取走 zdsetf 鏡像官網 PCF／投組（`source_url` → ctbcinvestments.com）。
- 野村投信：`issuer: nomura`，`fund_code` 為股票代號（本專案 `00980A`／`00985A`／`00999A`）；無穩定公開 Excel／CSV，抓取走 zdsetf 鏡像官網投組（`source_url` → nomurafunds.com.tw）。
- 安聯投信：`issuer: allianz`，`fund_code` 為官網產品碼（本專案 `00984A` 為 `E0001`、`00993A` 為 `E0002`）；無穩定公開 Excel／CSV，抓取走 zdsetf 鏡像官網投組（`source_url` → etf.allianzgi.com.tw）。
- 國泰投信：`issuer: cathay`；`fund_code` 對主動 `00400A` 為官網 URL 碼 `EEA`（zdsetf）；對被動 `00881`／`00878` 為 cwapi `fundCode`=`CR`／`CN`（頁面 slug `ECR`／`ECS`）。抓取先試 zdsetf，失敗則改官網 `GetIndexStockWeights`（權重；股數為 weight×1e6 合成）。
- 摩根投信：`issuer: jpm`，`fund_code` 為股票代號（本專案 `00401A`）；無穩定公開 Excel／CSV，抓取走 zdsetf 鏡像官網 PCF／投組（`source_url` → am.jpmorgan.com）。zdsetf `weight_pct` 可能為 null，解析後正規化為 `0.0`（不臆造權重）。
- 台新投信：`issuer: taishin`，`fund_code` 為股票代號（本專案 `00987A`）；無穩定公開 Excel／CSV，抓取走 zdsetf 鏡像官網 PCF／投組（`source_url` → tsit.com.tw）。zdsetf `weight_pct` 可能為 null，解析後正規化為 `0.0`（不臆造權重）。
- 第一金投信：`issuer: fsitc`，`fund_code` 為官網 FundDetail ID（本專案 `00408A` 為 `183`、`00994A` 為 `182`）；無穩定公開 Excel／CSV，抓取走 zdsetf 鏡像官網投組（`source_url` → fsitc.com.tw）。
- 兆豐投信：`issuer: mega`，`fund_code` 為官網產品 id（本專案 `00996A` 為 `23`）；無穩定公開 Excel／CSV，抓取走 zdsetf 鏡像官網投組（`source_url` → megafunds.com.tw）。
- 元大投信：`issuer: yuanta`，`fund_code` 為股票代號（本專案 `0050`／`0056`／`00713`／`00940`）；無公開 Excel／CSV，抓取走官網持股比重頁 SSR（`source_page` → yuantaetfs.com `/product/detail/{TICKER}/ratio`）；抽取需 Node.js。zdsetf 不收錄被動 `0050`／`0056`／`00713`／`00940`。
- 大華銀投信：`issuer: uobam`，`fund_code` 為官網 fundID（本專案 `00918` 為 `88329556`）；無公開 Excel／CSV，抓取走官網 PCF API `WebSitePcfRequest`（`source_page` → uobam.com.tw `/fund/etf/{fundID}`）；含真實股數。zdsetf 不收錄被動 `00918`。
- 凱基投信：`issuer: kgi`，`fund_code` 為官網 fundID（本專案 `009816` 為 `J023`）；無公開 Excel／CSV，抓取走官網基金頁 `Fund/Detail?fundID={fundID}` 的「持股比重」股票表（HTML；含真實股數＋權重）。zdsetf 不收錄被動 `009816`。

---

## 資料來源

| 優先 | 來源 | 說明 |
|------|------|------|
| 主 | 統一 ezmoney `AssetExcelNPOI?fundCode=`（`00981A`／`00988A`／`00403A`／`00939`） | 需先 GET 官網取得 WAF cookie；**僅最新**，本專案自行 archive；被動 `00939` fundCode=`46YTW`；zdsetf 不收錄 |
| 主 | 復華 `api/assetsExcel/{ETF23|ETF21}/{YYYYMMDD}`（`00991A`／`00929`） | 無需登入；可依日期取歷史；無資料時回 JSON；被動檔 Excel 末段期貨略過；zdsetf 不收錄被動 `00929` |
| 主 | 群益 `capital`（`00992A`／`00982A`／`00919`） | **無公開 Excel API**；主動檔以 [zdsetf.com](https://zdsetf.com) snapshot；被動 `00919`（zdsetf 404）以官網 CFWeb [buyback](https://www.capitalfund.com.tw/CFWeb/api/etf/buyback)（fundId=`195`；真實 share＋weight） |
| 主 | 富邦 `fubon`（`00405A`） | **無穩定公開 Excel／CSV**；以 [zdsetf.com](https://zdsetf.com) `/api/etfs/00405A/snapshot` 鏡像官網投組（`source_url` → websys.fsit.com.tw） |
| 主 | 中信 `ctbc`（`00406A`／`00995A`） | **無穩定公開 Excel／CSV**；以 [zdsetf.com](https://zdsetf.com) `/api/etfs/{TICKER}/snapshot` 鏡像官網 PCF（`source_url` → ctbcinvestments.com） |
| 主 | 野村 `nomura`（`00980A`／`00985A`／`00999A`） | **無穩定公開 Excel／CSV**；以 [zdsetf.com](https://zdsetf.com) `/api/etfs/{TICKER}/snapshot` 鏡像官網投組（`source_url` → nomurafunds.com.tw） |
| 主 | 安聯 `allianz`（`00984A`／`00993A`） | **無穩定公開 Excel／CSV**；以 [zdsetf.com](https://zdsetf.com) `/api/etfs/{TICKER}/snapshot` 鏡像官網投組（`source_url` → etf.allianzgi.com.tw） |
| 主 | 國泰 `cathay`（`00400A`／`00881`／`00878`） | **無穩定公開 Excel／CSV**；`00400A` 以 [zdsetf.com](https://zdsetf.com) snapshot；`00881`／`00878`（zdsetf 404）以官網 cwapi [GetIndexStockWeights](https://cwapi.cathaysite.com.tw/api/ETF/GetIndexStockWeights?fundCode=CN)（fundCode=`CR`／`CN`；需 browser UA；股數合成自權重） |
| 主 | 摩根 `jpm`（`00401A`） | **無穩定公開 Excel／CSV**；以 [zdsetf.com](https://zdsetf.com) `/api/etfs/00401A/snapshot` 鏡像官網 PCF／投組（`source_url` → am.jpmorgan.com）；權重 null → 0.0 |
| 主 | 台新 `taishin`（`00987A`） | **無穩定公開 Excel／CSV**；以 [zdsetf.com](https://zdsetf.com) `/api/etfs/00987A/snapshot` 鏡像官網 PCF／投組（`source_url` → tsit.com.tw）；權重 null → 0.0 |
| 主 | 第一金 `fsitc`（`00408A`／`00994A`） | **無穩定公開 Excel／CSV**；以 [zdsetf.com](https://zdsetf.com) `/api/etfs/{TICKER}/snapshot` 鏡像官網投組（`source_url` → fsitc.com.tw） |
| 主 | 兆豐 `mega`（`00996A`） | **無穩定公開 Excel／CSV**；以 [zdsetf.com](https://zdsetf.com) `/api/etfs/00996A/snapshot` 鏡像官網投組（`source_url` → megafunds.com.tw） |
| 主 | 元大 `yuanta`（`0050`／`0056`／`00713`／`00940`） | **無公開 Excel／CSV**；官網持股比重 [yuantaetfs.com/.../{TICKER}/ratio](https://www.yuantaetfs.com/product/detail/0050/ratio) Nuxt SSR `__NUXT__.weightData.FundWeights`（需 Node.js）；zdsetf 不收錄被動 ETF |
| 主 | 大華銀 `uobam`（`00918`） | **無公開 Excel／CSV**；官網 PCF [WebSitePcfRequest](https://www.uobam.com.tw/json/reply/WebSitePcfRequest?fundID=88329556)（fundID=`88329556`；真實 qty＋weight；略過 Cash／Margin）；zdsetf 不收錄被動 `00918`；SSL 中繼憑證不全時 verify=False |
| 主 | 凱基 `kgi`（`009816`） | **無公開 Excel／CSV**；官網基金頁 [Fund/Detail?fundID=J023](https://www.kgifund.com.tw/Fund/Detail?fundID=J023)「持股比重」股票表（HTML；真實股數＋權重；略過期貨／現金）；zdsetf 不收錄被動 `009816` |
| 備 | [zdsetf.com](https://zdsetf.com) `/api/etfs/{TICKER}/snapshot` | 第三方 JSON；統一／復華官方失敗時 fallback |

比對規則：

- 鍵：`stock_code`；數量用 **shares（股數）**，不用權重。
- **占位列政策（預設）**：`shares ≤ 1000` **且** `weight_pct < 0.01` 視為占位 → 快照仍保留並標記 `is_placeholder`，但**不進入**四類異動表。可在 `config.yaml` 的 `placeholder` 調整。
- **連續天數**：回溯已歸檔快照，計算同一代號連續加碼／減碼的日數。
- 時區：`Asia/Taipei`。

研究紀錄見姊妹目錄調查報告（本機開發用）。

---

## 專案結構

```
config.yaml                 # 觀察清單與占位政策
src/tw_etf_pages/           # fetch / parse / compare / render
samples/                    # 離線單元測試與 dry-run 用 Excel
data/snapshots/{TICKER}/    # 日快照 JSON
data/changes/{TICKER}/      # 異動報告 JSON
site/                       # GitHub Pages 靜態輸出
.github/workflows/update.yml
```

---

## 授權

MIT — 見 [LICENSE](LICENSE)。持股資料版權屬各發行人；本專案僅做公開揭露內容之歸檔與呈現。
