# 歷史持股回補（Backfill）

## 結論（00981A／00988A／00403A／00939／統一投信）

**不可行（一次回補 ~20 交易日）。**

- 統一 ezmoney `AssetExcelNPOI?fundCode=` 只回傳**最新**投資組合 Excel（主動 `49YTW`／`61YTW`／`63YTW`；被動 `00939` 統一台灣高息動能 → `46YTW`）。
- 調查與實測：無依日期參數的公開歷史 endpoint。
- 第三方 `zdsetf.com` 僅有 `/snapshot`、`/changes`（最新一日），`/history` 等回 404；被動 `00939` snapshot **404**。
- 因此 **00981A、00988A、00403A、00939** 的近 20 日趨勢必須靠本站 **每日 Actions 自行歸檔** 累積；上線初期天數會少於 20。

## 復華（00991A／00929）

- `https://www.fhtrust.com.tw/api/assetsExcel/{fund_code}/{YYYYMMDD}` 可依日期下載（主動 `00991A` → `ETF23`；被動 `00929` 復華台灣科技優息 → `ETF21`）。
- 可手動／腳本回補後以 `parse_fh_excel` 寫入 `data/snapshots/{TICKER}/`。
- 被動 `00929`：zdsetf **404**；Excel 末段期貨區塊由 parser 略過（僅歸檔股票）。
- 請遵守發行人公開揭露用途；勿高頻爬取。

## 產品行為

趨勢圖與「間歇加碼」標示在天數不足時顯示 Traditional Chinese 空狀態／提示，不偽造歷史點。

## 群益（00992A／00982A／00919／Capital Fund）

- 官網投組頁：`00992A` → `https://www.capitalfund.com.tw/etf/product/detail/500/portfolio`；`00982A` → `https://www.capitalfund.com.tw/etf/product/detail/399/portfolio`；被動 `00919`（群益台灣精選高息）→ `https://www.capitalfund.com.tw/etf/product/detail/195/portfolio`。
- **無公開 Excel／依日期 API** 可供本站直接下載。
- `00992A`／`00982A`：以 `zdsetf.com/api/etfs/{TICKER}/snapshot` 為主（有股數；`source_url` 指向群益官網）；僅最新一日，**無法一次回補**。
- `00919`：zdsetf **404**（不收錄此等被動 ETF）。以官網 CFWeb `POST /CFWeb/api/etf/buyback`（body `{"fundId":195}`）歸檔持股；含真實股數 `share` 與權重；略過債券附買回／期貨／保證金。資料日取 `pcf.date2`。僅最新一日，**無法一次回補**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 富邦（00405A／Fubon）

- 官網投組頁：`https://websys.fsit.com.tw/FubonETF/Fund/Profile.aspx?stkId=00405A`。
- **無穩定公開 Excel／CSV URL** 可供本站直接下載。
- 本站以 `zdsetf.com/api/etfs/00405A/snapshot` 作為主來源（JSON 內 `source_url` 指向 websys.fsit.com.tw）；僅最新一日，**無法一次回補**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 中信（00406A／00995A／CTBC）

- 官網 PCF／投組頁：`00406A` → `https://www.ctbcinvestments.com/etfprod/00406A/pcf`；`00995A` → `https://www.ctbcinvestments.com/etfprod/00995A/pcf`（產品頁亦可見 `https://www.ctbcinvestments.com/Etf/00653201`）。
- **無穩定公開 Excel／CSV API** 可供本站直接下載。
- 本站以 `zdsetf.com/api/etfs/{TICKER}/snapshot` 作為主來源（JSON 內 `source_url` 指向 ctbcinvestments.com）；僅最新一日，**無法一次回補**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 野村（00980A／00985A／00999A／Nomura）

- 官網產品／投組頁：`00980A` → `https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00980A`；`00985A` → `https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00985A`；`00999A` → `https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo=00999A`（亦可 `tab=basic`；zdsetf `source_url` 指向 `tab=Shareholding`）。
- **無穩定公開 Excel／CSV API** 可供本站直接下載（官網為 SPA，無穩定自動化下載 URL）。
- 本站以 `zdsetf.com/api/etfs/{TICKER}/snapshot` 作為主來源（JSON 內 `source_url` 指向 nomurafunds.com.tw）；僅最新一日，**無法一次回補**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 安聯（00984A／00993A／Allianz）

- 官網產品／投組頁：`00984A` → `https://etf.allianzgi.com.tw/etf-info/E0001`；`00993A` → `https://etf.allianzgi.com.tw/etf-info/E0002`（zdsetf `source_url` 指向 `https://etf.allianzgi.com.tw/list-trade`）。
- **無穩定公開 Excel／CSV API** 可供本站直接下載。
- 本站以 `zdsetf.com/api/etfs/{TICKER}/snapshot` 作為主來源（JSON 內 `source_url` 指向 etf.allianzgi.com.tw）；僅最新一日，**無法一次回補**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 國泰（00400A／00881／00878／Cathay）

- 官網產品／投組頁：主動 `00400A` → `https://www.cathaysite.com.tw/ETF/detail/EEA`；被動 `00881`（國泰台灣科技龍頭，原名 5G+）→ `https://www.cathaysite.com.tw/ETF/detail/ECR?tab=etf3`；被動 `00878`（國泰永續高股息）→ `https://www.cathaysite.com.tw/ETF/detail/ECS?tab=etf3`。
- **無穩定公開 Excel／CSV API** 可供本站直接下載。
- `00400A`：以 `zdsetf.com/api/etfs/00400A/snapshot` 為主（有股數）；僅最新一日，**無法一次回補**。
- `00881`／`00878`：zdsetf **404**（不收錄此等被動 ETF）。以官網 cwapi `GetIndexStockWeights?fundCode=CR`／`CN` 歸檔持股權重；**無股數**，本站以 `shares = round(weight_pct * 1e6)` 合成供相對異動／趨勢；cwapi 需 browser-like User-Agent（專案 UA 會 403）。僅最新一日，**無法一次回補**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 摩根（00401A／J.P. Morgan AM Taiwan／jpm）

- 官網產品頁：`https://am.jpmorgan.com/tw/zh/asset-management/twetf/products/jpmorgan-taiwan-taiwan-equity-high-income-active-etf-tw00000401a1`（行銷頁：`…/funds/jpmorgan-tw-equity-high-income-etf/`）。
- **無穩定公開 Excel／CSV API** 可供本站直接下載（zdsetf `source_url` 雖可能指向 am.jpmorgan.com 上的 PCF xlsx dam 路徑，但不視為穩定可自動化 API）。
- 本站以 `zdsetf.com/api/etfs/00401A/snapshot` 作為主來源（JSON 內 `source_url` 指向 am.jpmorgan.com）；僅最新一日，**無法一次回補**。
- **權重 caveat**：zdsetf 快照中 `weight_pct` 可能全為 `null`（與國泰 `00400A` 相同）；parser 正規化為 `0.0`，**不臆造權重**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 台新（00987A／Taishin／taishin）

- 官網產品頁：`https://www.tsit.com.tw/ETF/Home/ETFSeriesDetail/00987A`；PCF／投組：`https://www.tsit.com.tw/ETF/Home/Pcf/00987A`（zdsetf `source_url` 指向此 PCF 頁）。
- **無穩定公開 Excel／CSV API** 可供本站直接下載（官網為 HTML 投組／PCF 頁）。
- 本站以 `zdsetf.com/api/etfs/00987A/snapshot` 作為主來源（JSON 內 `source_url` 指向 tsit.com.tw）；僅最新一日，**無法一次回補**。
- **權重 caveat**：zdsetf 快照中 `weight_pct` 可能全為 `null`（與國泰 `00400A`／摩根 `00401A` 相同）；parser 正規化為 `0.0`，**不臆造權重**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 第一金（00408A／00994A／FSITC／fsitc）

- 官網產品／投組頁：`00408A` → `https://www.fsitc.com.tw/FundDetail.aspx?ID=183`；`00994A` → `https://www.fsitc.com.tw/FundDetail.aspx?ID=182`（zdsetf `source_url` 指向各頁）。
- **無穩定公開 Excel／CSV API** 可供本站直接下載（`FormDownload.aspx`／`ETFAccWeb`／`ETFList.aspx` 未提供可自動化的持股 Excel／CSV URL）。
- 本站以 `zdsetf.com/api/etfs/{TICKER}/snapshot` 作為主來源（JSON 內 `source_url` 指向 fsitc.com.tw）；僅最新一日，**無法一次回補**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 兆豐（00996A／Mega Funds／mega）

- 官網產品／投組頁：`https://www.megafunds.com.tw/MEGA/etf/etf_product.aspx?id=23`（zdsetf `source_url` 指向此頁；產品 id=23）。
- **無穩定公開 Excel／CSV API** 可供本站直接下載（官網為 HTML 投組頁；本機直連可能被 WAF 擋）。
- 本站以 `zdsetf.com/api/etfs/00996A/snapshot` 作為主來源（JSON 內 `source_url` 指向 megafunds.com.tw）；僅最新一日，**無法一次回補**。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 元大（0050／0056／00713／00940／Yuanta／yuanta）

- 官網持股比重頁：`https://www.yuantaetfs.com/product/detail/{TICKER}/ratio`（例：`0050`、`0056`、`00713`、`00940`；PCF：`https://www.yuantaetfs.com/tradeInfo/pcf/{TICKER}`）。
- **無公開 Excel／CSV API**；頁面為 Nuxt SSR，完整持股在 `window.__NUXT__` → `weightData.FundWeights.StockWeights`。
- [zdsetf.com](https://zdsetf.com) **僅追蹤主動式 *A ETF**，被動 `0050`／`0056`／`00713`／`00940` 回 404，不可作 fallback。
- 本站以官網 ratio 頁為主來源：下載 HTML 後以 Node.js 解析 `__NUXT__` 寫成 JSON 再歸檔；**無法一次回補**。
- **Caveat**：被動指數型（0050 臺灣50、0056 高股息、00713 高息低波、00940 價值高息）日常調倉少，日對日異動常為空；指數定期審核／再平衡時才會有明顯換股。
- 歷史天數靠每日 Actions 累積；異動資料日選單仍最多 10 日。

## 大華銀（00918／UOBAM／uobam）

- 官網產品頁：`https://www.uobam.com.tw/fund/etf/88329556`；PCF：`https://www.uobam.com.tw/fund/etf/pcf?fundID=88329556`。
- 無穩定公開 Excel／CSV 下載 URL；zdsetf **404**（不收錄被動 `00918`）。
- 本站以官網 ServiceStack `GET /json/reply/WebSitePcfRequest?fundID=88329556` 為主來源（真實股數 qty＋weight；略過 kind≠stock 的 Cash／Margin）。部分 CA 缺中華電信中繼時 SSL verify 失敗會改 `verify=False`。僅最新一日，**無法一次回補**。

## 凱基（009816／KGI／kgi）

- 官網基金頁：`https://www.kgifund.com.tw/Fund/Detail?fundID=J023`（凱基台灣 TOP 50 ETF；PCF：`https://www.kgifund.com.tw/Fund/RedemptionList`）。
- 無穩定公開 Excel／CSV 下載 URL；zdsetf **404**（不收錄被動 `009816`）。
- 本站以官網基金頁伺服器端渲染 HTML 的「持股比重」區塊為主來源（日期標於標題下方；股票表含股票代號／名稱／股數／權重；期貨 TX 與現金不列入）。僅最新一日，**無法一次回補**。
- **Caveat**：被動指數型（特選臺灣 TOP 50 指數，每年 2／5／8／11 月調整）日常調倉少，日對日異動常為空。
