"""
Alert performance tracker — the honest scoreboard.

Reads every past scan committed to data/scan_results.json history (via git log)
plus the archive it builds itself, then re-checks how each alerted stock
actually performed since its alert date, compared against its benchmark
(Nifty 50 for .NS tickers, S&P 500 otherwise). All prices come live from
Yahoo's chart endpoint — the cheap one — so this uses only a handful of
requests no matter how many alerts you have.

Outputs:
  data/alert_performance.json   full per-alert records (machine-readable)
  data/SCOREBOARD.md            human-readable summary committed to the repo

Run manually:  python track_performance.py
Or on a schedule: the daily_scan workflow can call it after each scan
(see README) — it is idempotent and cheap.

Reading the scoreboard: the single number that matters is the median
excess return vs benchmark ("alpha"). If after 20+ alerts and 3+ months the
median alpha is ~0 or negative, the 80-threshold system is not adding value
over simply buying the index — that is a real answer, and the whole point.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import pandas as pd
import yfinance as yf

try:
    from curl_cffi import requests as _curl
    _SESSION = _curl.Session(impersonate="chrome")
except Exception:
    _SESSION = None

DATA = Path("data")
RESULTS = DATA / "scan_results.json"
ARCHIVE = DATA / "alert_performance.json"
BOARD = DATA / "SCOREBOARD.md"
HORIZONS = (30, 90, 180)  # days


# ------------------------------------------------------------- collect alerts
def alerts_from_git() -> dict[str, str]:
    """{ticker: first_alert_date} from every historical version of
    scan_results.json in git history. Falls back to the current file."""
    first_seen: dict[str, str] = {}

    def record(payload: dict):
        day = (payload.get("run_utc") or "")[:10]
        for t in payload.get("alerts", []):
            if t not in first_seen or day < first_seen[t]:
                first_seen[t] = day

    try:
        shas = subprocess.run(
            ["git", "log", "--format=%H", "--", str(RESULTS)],
            capture_output=True, text=True, check=True
        ).stdout.split()
        for sha in shas:
            try:
                blob = subprocess.run(
                    ["git", "show", f"{sha}:{RESULTS.as_posix()}"],
                    capture_output=True, text=True, check=True).stdout
                record(json.loads(blob))
            except Exception:
                continue
    except Exception:
        pass
    if RESULTS.exists():
        try:
            record(json.loads(RESULTS.read_text()))
        except Exception:
            pass
    # merge previously archived alerts so nothing is ever lost
    if ARCHIVE.exists():
        for rec in json.loads(ARCHIVE.read_text()).get("alerts", []):
            t, d = rec["ticker"], rec["alert_date"]
            if t not in first_seen or d < first_seen[t]:
                first_seen[t] = d
    return first_seen


# ------------------------------------------------------------------- pricing
def batch_closes(tickers: list[str], start: str) -> dict[str, pd.Series]:
    if not tickers:
        return {}
    kw = dict(start=start, auto_adjust=True, progress=False,
              group_by="ticker", threads=False)
    df = yf.download(tickers, session=_SESSION, **kw) if _SESSION else yf.download(tickers, **kw)
    out = {}
    for t in tickers:
        try:
            s = (df[t]["Close"] if len(tickers) > 1 else df["Close"]).dropna()
            if len(s):
                out[t] = s
        except (KeyError, TypeError):
            pass
    return out


def ret_since(closes: pd.Series, start_date: str, days: int | None) -> float | None:
    """% return from first close on/after start_date to `days` later (None = today)."""
    idx = closes.index.tz_localize(None)
    start = pd.Timestamp(start_date)
    pos = idx.searchsorted(start)
    if pos >= len(closes):
        return None
    p0 = float(closes.iloc[pos])
    if days is None:
        p1 = float(closes.iloc[-1])
    else:
        end_pos = idx.searchsorted(start + pd.Timedelta(days=days))
        if end_pos >= len(closes):
            return None  # horizon not reached yet — report nothing, not a guess
        p1 = float(closes.iloc[end_pos])
    return round((p1 / p0 - 1) * 100, 2)


# ---------------------------------------------------------------------- main
def main() -> None:
    first_seen = alerts_from_git()
    if not first_seen:
        print("No past alerts found yet — run the scanner first.")
        return
    print(f"Tracking {len(first_seen)} alerted stocks "
          f"(earliest {min(first_seen.values())}) …")

    earliest = min(first_seen.values())
    closes = batch_closes(sorted(first_seen), start=earliest)
    bench = batch_closes(["^NSEI", "^GSPC"], start=earliest)

    records = []
    for tkr, day in sorted(first_seen.items(), key=lambda kv: kv[1]):
        c = closes.get(tkr)
        bsym = "^NSEI" if tkr.endswith((".NS", ".BO")) else "^GSPC"
        b = bench.get(bsym)
        if c is None:
            records.append({"ticker": tkr, "alert_date": day, "benchmark": bsym,
                            "note": "price data unavailable"})
            continue
        rec = {"ticker": tkr, "alert_date": day, "benchmark": bsym}
        for h in HORIZONS:
            r, br = ret_since(c, day, h), ret_since(b, day, h) if b is not None else None
            rec[f"ret_{h}d"] = r
            rec[f"alpha_{h}d"] = round(r - br, 2) if r is not None and br is not None else None
        r, br = ret_since(c, day, None), ret_since(b, day, None) if b is not None else None
        rec["ret_to_date"] = r
        rec["alpha_to_date"] = round(r - br, 2) if r is not None and br is not None else None
        records.append(rec)

    payload = {"updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "alerts": records}
    DATA.mkdir(exist_ok=True)
    ARCHIVE.write_text(json.dumps(payload, indent=1))

    # ---------------- scoreboard ----------------
    lines = ["# 📊 Alert Scoreboard — does the 80+ system actually work?", "",
             f"_Updated {payload['updated_utc']} · returns are % vs first close after alert · "
             "alpha = stock return − benchmark (Nifty 50 for .NS, S&P 500 otherwise) · "
             "blank = horizon not reached yet_", ""]

    hdr = "| Ticker | Alerted | 30d | α30 | 90d | α90 | 180d | α180 | To date | α |"
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    lines += [hdr, sep]
    f = lambda v: "" if v is None else f"{v:+.1f}%"
    for r in records:
        if "note" in r:
            lines.append(f"| {r['ticker']} | {r['alert_date']} | — {r['note']} |||||||||")
            continue
        lines.append(f"| {r['ticker']} | {r['alert_date']} | {f(r['ret_30d'])} | {f(r['alpha_30d'])} "
                     f"| {f(r['ret_90d'])} | {f(r['alpha_90d'])} | {f(r['ret_180d'])} | {f(r['alpha_180d'])} "
                     f"| {f(r['ret_to_date'])} | {f(r['alpha_to_date'])} |")

    lines += ["", "## Verdict so far", ""]
    for h in list(HORIZONS) + ["to_date"]:
        key = f"alpha_{h}d" if isinstance(h, int) else "alpha_to_date"
        vals = [r[key] for r in records if r.get(key) is not None]
        if vals:
            wins = sum(1 for v in vals if v > 0)
            label = f"{h}-day" if isinstance(h, int) else "to date"
            lines.append(f"- **{label}** ({len(vals)} alerts matured): median alpha "
                         f"**{median(vals):+.1f}%**, beat benchmark {wins}/{len(vals)} times")
    matured = [r.get("alpha_90d") for r in records if r.get("alpha_90d") is not None]
    lines += ["", "> Judgement rule: wait for **20+ matured alerts**. If median 90-day alpha "
              "is around zero or negative, the system isn't beating the index — lower "
              "conviction or fix the checklist. A handful of alerts proves nothing either way.", ""]
    BOARD.write_text("\n".join(lines))
    print(f"Wrote {ARCHIVE} and {BOARD}")
    for l in lines[-8:]:
        print(l)


if __name__ == "__main__":
    main()
