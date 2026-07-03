"""
Daily batch scanner — runs on GitHub Actions (see .github/workflows/daily_scan.yml).

Two-stage funnel (keeps Yahoo happy and the run fast):
  Stage 1  Bulk-download 1y price history for the WHOLE universe in a few
           chunked requests (the chart endpoint is cheap). Keep only stocks in
           a technical uptrend: price > 200DMA and 50DMA > 200DMA.
  Stage 2  Only for those survivors, fetch fundamentals (the expensive,
           throttled endpoint) politely — one ticker every few seconds — and
           run the full 27-point checklist from validations.py.

Alerts: every stock scoring >= SCORE_THRESHOLD (default 80) is sent to your
Telegram in one message. Full results are written to data/scan_results.json,
which the workflow commits back to the repo — so your GitHub history doubles
as a free scan archive.

Universe: by default, the symbol lists from your own repo
(mrappipramod/IndianStockMarket-V1) — 484 Indian (.NS) + 28 US stocks.
Override with data/universe_in.txt / data/universe_us.txt (one symbol per line).

Environment variables (set as GitHub Actions secrets):
  TELEGRAM_BOT_TOKEN   from @BotFather
  TELEGRAM_CHAT_ID     your chat id (message the bot, then check
                       https://api.telegram.org/bot<TOKEN>/getUpdates)
  SCORE_THRESHOLD      default 80
  ALPHAVANTAGE_KEY     optional fundamentals fallback (US tickers)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from validations import compute_report, _retry, _SESSION, RateLimited

UNIVERSE_URLS = {
    "in": "https://raw.githubusercontent.com/mrappipramod/IndianStockMarket-V1/main/data/in_all_stocks.json",
    "us": "https://raw.githubusercontent.com/mrappipramod/IndianStockMarket-V1/main/data/us_all_stocks.json",
}
DATA_DIR = Path("data")
CHUNK = 80            # tickers per bulk price download
INFO_DELAY = 3.0      # seconds between fundamentals calls (polite pacing)


# ---------------------------------------------------------------- universe --
def load_universe() -> list[str]:
    symbols: list[str] = []
    for mkt, suffix in (("in", ".NS"), ("us", "")):
        local = DATA_DIR / f"universe_{mkt}.txt"
        if local.exists():
            syms = [l.strip().upper() for l in local.read_text().splitlines() if l.strip()]
        else:
            r = requests.get(UNIVERSE_URLS[mkt], timeout=60)
            r.raise_for_status()
            syms = [row["symbol"].upper() for row in r.json()]
        symbols += [s if s.endswith((".NS", ".BO")) or mkt == "us" else s + suffix
                    for s in syms]
    return sorted(set(symbols))


# ------------------------------------------------------- stage 1: bulk tech --
def bulk_history(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Download 1y closes for everyone in chunks. Returns {symbol: df}."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), CHUNK):
        chunk = symbols[i:i + CHUNK]
        try:
            df = _retry(lambda c=chunk: yf.download(
                c, period="1y", auto_adjust=True, progress=False,
                group_by="ticker", threads=False,
                session=_SESSION) if _SESSION else yf.download(
                c, period="1y", auto_adjust=True, progress=False,
                group_by="ticker", threads=False))
        except Exception as e:
            print(f"  chunk {i//CHUNK+1}: download failed ({e}); skipping")
            continue
        for sym in chunk:
            try:
                sub = df[sym][["Close"]].dropna() if len(chunk) > 1 else df[["Close"]].dropna()
                if len(sub) >= 60:
                    out[sym] = sub
            except (KeyError, TypeError):
                pass
        time.sleep(2)
    return out


def technical_prefilter(hist: dict[str, pd.DataFrame]) -> list[str]:
    """Keep stocks in an uptrend — the only ones that can plausibly score 80+."""
    keep = []
    for sym, df in hist.items():
        c = df["Close"]
        price = float(c.iloc[-1])
        ma200 = float(c.tail(200).mean()) if len(c) >= 200 else float(c.mean())
        ma50 = float(c.tail(50).mean())
        if price > ma200 and ma50 > ma200:
            keep.append(sym)
    return keep


# ------------------------------------------------- stage 2: full checklist --
def full_analysis(symbols: list[str], hist: dict[str, pd.DataFrame],
                  av_key: str | None) -> list[dict]:
    reports = []
    for n, sym in enumerate(symbols, 1):
        try:
            tk = yf.Ticker(sym, session=_SESSION) if _SESSION else yf.Ticker(sym)
            try:
                info = _retry(lambda: tk.info or {}, attempts=3)
                source = "Yahoo Finance"
            except RateLimited:
                info, source = {}, "Yahoo price data only — fundamentals rate-limited"
                if av_key and not sym.endswith((".NS", ".BO")):
                    try:
                        import alpha_vantage
                        info, _ = alpha_vantage.fetch(sym, av_key)
                        source = "Alpha Vantage (Yahoo rate-limited)"
                    except Exception:
                        pass
            r = compute_report(sym, info, hist[sym], source)
            reports.append(r.to_dict())
            print(f"  [{n}/{len(symbols)}] {sym}: {r.score} ({r.verdict.split('—')[0].strip()})")
        except Exception as e:
            print(f"  [{n}/{len(symbols)}] {sym}: failed ({e})")
        time.sleep(INFO_DELAY)
    return reports


# ------------------------------------------------------------------ alerts --
def send_telegram(text: str) -> None:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Telegram secrets not set — skipping alert. Message would have been:\n" + text)
        return
    # Telegram caps messages at 4096 chars — split if needed
    for i in range(0, len(text), 3900):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text[i:i + 3900],
                                "parse_mode": "HTML",
                                "disable_web_page_preview": True},
                          timeout=30)
        if r.status_code != 200:
            print(f"Telegram send failed: {r.status_code} {r.text[:200]}")


def format_alert(hits: list[dict], scanned: int, prefiltered: int, threshold: float) -> str:
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    head = (f"💎 <b>Pre-Buy Checklist Alert</b> — {stamp}\n"
            f"Universe {scanned} → uptrend {prefiltered} → "
            f"<b>{len(hits)} scored ≥ {threshold:g}</b>\n")
    lines = []
    for r in sorted(hits, key=lambda x: -(x["score"] or 0)):
        cur = r.get("currency") or ""
        fails = sum(1 for c in r["checks"] if c["status"] == "FAIL")
        partial = " ⚠️partial data" if "PARTIAL" in (r["verdict"] or "") else ""
        lines.append(
            f"\n<b>{r['ticker']}</b> — {r['company']}\n"
            f"  Score <b>{r['score']}</b>/100 · {fails} fails · {r['data_coverage']}{partial}\n"
            f"  {cur} {r['price']:,.2f} · {r['sector']}"
        )
    foot = ("\n\nℹ️ Checklist screen from live Yahoo data — a research shortlist, "
            "not investment advice. Verify before acting.")
    return head + "".join(lines) + foot


# -------------------------------------------------------------------- main --
def main() -> None:
    threshold = float(os.getenv("SCORE_THRESHOLD", "80"))
    av_key = os.getenv("ALPHAVANTAGE_KEY") or None

    print("Loading universe …")
    universe = load_universe()
    print(f"  {len(universe)} symbols")

    print("Stage 1: bulk price download + uptrend pre-filter …")
    hist = bulk_history(universe)
    survivors = technical_prefilter(hist)
    print(f"  {len(hist)} with data → {len(survivors)} in uptrend")

    print("Stage 2: full 27-point checklist on survivors …")
    reports = full_analysis(survivors, hist, av_key)

    hits = [r for r in reports if (r.get("score") or 0) >= threshold
            and "PARTIAL" not in (r.get("verdict") or "")]
    partial_hits = [r for r in reports if (r.get("score") or 0) >= threshold
                    and "PARTIAL" in (r.get("verdict") or "")]

    DATA_DIR.mkdir(exist_ok=True)
    out = {
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "threshold": threshold,
        "universe_size": len(universe),
        "prefiltered": len(survivors),
        "alerts": [r["ticker"] for r in hits],
        "partial_data_hits": [r["ticker"] for r in partial_hits],
        "reports": reports,
    }
    (DATA_DIR / "scan_results.json").write_text(json.dumps(out, indent=1))
    print(f"Saved {len(reports)} reports → data/scan_results.json")

    if hits or partial_hits:
        msg = format_alert(hits, len(universe), len(survivors), threshold)
        if partial_hits:
            msg += ("\n\n⚠️ Also scored ≥ threshold but with PARTIAL data "
                    "(fundamentals were rate-limited, verify manually): "
                    + ", ".join(r["ticker"] for r in partial_hits))
        send_telegram(msg)
        print(f"Alerted {len(hits)} stocks (+{len(partial_hits)} partial).")
    else:
        print("No stock cleared the threshold today — no alert sent.")


if __name__ == "__main__":
    main()
