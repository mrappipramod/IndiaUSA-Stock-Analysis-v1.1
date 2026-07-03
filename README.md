# ✅ Pre-Buy Stock Validator

A Streamlit app that runs the checklist a financial analyst applies **before buying a stock** — 25 checks across 8 categories, using **only free, live Yahoo Finance data** (via `yfinance`, no API key). Nothing is fabricated: any field Yahoo doesn't report is shown as **N/A** and excluded from the score.

## The checklist

| Category | Checks |
|---|---|
| **Valuation** | P/E, forward vs trailing P/E, PEG, P/B, EV/EBITDA |
| **Profitability** | ROE (with buyback-inflation warning), ROA, operating margin, net margin |
| **Growth** | Revenue growth yoy, earnings growth yoy |
| **Balance sheet** | Debt/equity, current ratio, net cash position |
| **Cash flow quality** | Free cash flow, OCF ÷ net income (earnings quality), dividend payout ratio |
| **Tradability** | Market cap, average daily volume |
| **Timing** | Price vs 200DMA, 50/200 DMA structure, 52-week range position, RSI(14), beta |
| **Ownership** | Institutional holding, short interest, analyst consensus |

Each check → PASS / WARN / FAIL / N/A → weighted score /100 → verdict.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Indian tickers need the exchange suffix: `RELIANCE.NS`, `TCS.NS` (NSE) or `.BO` (BSE).

## Rate limits & the automatic fallback
Yahoo has no official API, and it throttles Streamlit Cloud's shared IPs. The app defends itself with a Chrome-fingerprint session (`curl_cffi`), retries with backoff, and a 1-hour result cache. For a guarantee, add a **free official API** as fallback:

1. Get a free key (30 seconds, no card): https://www.alphavantage.co/support/#api-key
2. Add to Streamlit secrets: `ALPHAVANTAGE_KEY = "your_key"`

When Yahoo rate-limits, the app automatically re-fetches from Alpha Vantage (NASDAQ-licensed, 25 free requests/day = ~12 analyses). Fields it doesn't provide (debt/equity, cash flow, volume…) show as N/A — never invented. Note: Alpha Vantage covers US/global tickers; NSE `.NS` symbols remain Yahoo-only.

## Graceful degradation & manual data entry
Yahoo throttles its **fundamentals** endpoint much harder than its **price/chart** endpoint. The app now fetches them independently:

- If only fundamentals are blocked → you still get a real report: RSI, 200-DMA trend, 50/200 structure and 52-week position are computed **from actual price history**, and fundamental checks show *N/A — rate-limited* (never a fake zero score).
- Low coverage is labeled: below 50% of the checklist, the verdict becomes **PARTIAL DATA — provisional** instead of pretending to be confident.
- **✍️ Fill missing data manually**: look up the missing numbers yourself (stockanalysis.com, screener.in, Yahoo in your browser) and type them in — the score recalculates instantly, every affected check is labeled *manually entered*, and the values are stored in the saved JSON under `user_provided` so your GitHub history shows exactly which numbers were yours vs live.

## Deploy free on Streamlit Community Cloud
1. Push this folder to a GitHub repo (e.g. `yourname/stock-validator`).
2. Go to https://share.streamlit.io → **New app** → pick the repo → main file `app.py` → Deploy.

## Store every analysis in GitHub (permanent history)
Streamlit Cloud wipes local files on restart, so reports are committed straight to your repo instead:

1. Create a **fine-grained personal access token**: GitHub → Settings → Developer settings → Fine-grained tokens → grant **Contents: Read & Write** on this repo only.
2. In Streamlit Cloud → your app → **Settings → Secrets**, add:
   ```toml
   GITHUB_TOKEN = "github_pat_xxxxxxxx"
   GITHUB_REPO  = "yourname/stock-validator"
   GITHUB_BRANCH = "main"
   ```
3. Click **Save to GitHub** after any analysis → the report lands in `data/analyses/TICKER_timestamp.json`, fully version-controlled. The app's "Saved analyses" panel reads them back.

For local runs, put the same keys in `.streamlit/secrets.toml` (already git-ignored).

## Daily automatic scan + Telegram alerts (score ≥ 80)
`scanner.py` + `.github/workflows/daily_scan.yml` scan the full universe (your repo's 484 Indian + 28 US stocks) every weekday at 4 PM IST on **GitHub Actions — free, no server needed**, and message you on Telegram only when a stock clears the checklist at 80+.

**Why it's feasible without rate-limit pain — a two-stage funnel:**
1. **Bulk price screen** (cheap endpoint, chunked): whole universe in a handful of requests → keep only uptrends (price > 200DMA and 50 > 200DMA). A stock can't score 80+ without this anyway.
2. **Full 27-point checklist** only on survivors (typically 15–30% of the universe), politely paced at one fundamentals call per 3s.

**Setup (once):**
1. Telegram: message **@BotFather** → `/newbot` → copy the token. Send your new bot any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
2. Repo → Settings → Secrets and variables → Actions → add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (and optionally `ALPHAVANTAGE_KEY`).
3. Push — the workflow runs Mon–Fri 10:30 UTC, or trigger manually from the Actions tab (workflow_dispatch).

Every run also commits `data/scan_results.json` (all reports, not just alerts) back to the repo, so Git history is your free scan archive. Alerts flag stocks whose 80+ score came from PARTIAL data separately, so you know to verify those manually. To scan a custom list, add `data/universe_in.txt` / `data/universe_us.txt` (one symbol per line). Threshold: edit `SCORE_THRESHOLD` in the workflow.

## Disclaimer
Educational screening tool, not investment advice. Thresholds are general analyst rules of thumb — always judge ratios against sector peers and verify numbers in official filings.
