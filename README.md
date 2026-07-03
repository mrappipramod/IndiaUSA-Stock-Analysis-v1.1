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

## Disclaimer
Educational screening tool, not investment advice. Thresholds are general analyst rules of thumb — always judge ratios against sector peers and verify numbers in official filings.
