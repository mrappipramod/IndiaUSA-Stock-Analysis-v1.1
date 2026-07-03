"""
Pre-buy stock validation engine.

Every number comes straight from Yahoo Finance via the `yfinance` library.
Nothing is fabricated: if Yahoo doesn't report a field, the check is marked
"N/A" and excluded from scoring instead of being guessed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

try:  # browser-impersonating HTTP session — dramatically reduces Yahoo 429s
    from curl_cffi import requests as curl_requests
    _SESSION = curl_requests.Session(impersonate="chrome")
except Exception:  # fall back to yfinance's default session
    _SESSION = None

PASS, WARN, FAIL, NA = "PASS", "WARN", "FAIL", "N/A"


class RateLimited(Exception):
    """Yahoo returned 429 for every retry attempt."""


def _retry(fn, attempts: int = 4):
    last_err = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            msg = str(e)
            if "429" not in msg and "Too Many Requests" not in msg and "rate" not in msg.lower():
                raise
        time.sleep(2 ** i + 1)  # 2s, 3s, 5s, 9s
    raise RateLimited(str(last_err))


def fetch_data(ticker: str, av_key: str | None = None):
    """Fetch (info, hist, source_label). Info and history are fetched INDEPENDENTLY:
    Yahoo throttles the fundamentals endpoint far harder than the price/chart endpoint,
    so a rate-limited `info` degrades to a price-only report instead of failing."""
    tk = yf.Ticker(ticker, session=_SESSION) if _SESSION else yf.Ticker(ticker)
    source = "Yahoo Finance"

    # price history (cheap endpoint, rarely blocked)
    try:
        hist = _retry(lambda: tk.history(period="1y", auto_adjust=True))
    except RateLimited:
        hist = pd.DataFrame()

    # fundamentals (heavily throttled endpoint)
    info, info_limited = {}, False
    try:
        info = _retry(lambda: tk.info or {})
    except RateLimited:
        info_limited = True

    if info_limited or not (info.get("longName") or info.get("shortName")):
        if av_key:  # official fallback
            try:
                import alpha_vantage
                av_info, av_hist = alpha_vantage.fetch(ticker, av_key)
                info = av_info
                if hist.empty:
                    hist = av_hist
                source = "Alpha Vantage (Yahoo fundamentals were rate-limited)"
                info_limited = False
            except Exception:
                pass
        if info_limited and not hist.empty:
            source = "Yahoo price data only — fundamentals endpoint rate-limited"
        elif info_limited:
            raise RateLimited("both Yahoo endpoints throttled")

    if not (info.get("longName") or info.get("shortName")) and hist.empty:
        raise ValueError(
            f"No data found for '{ticker}'. Check the symbol "
            "(Indian stocks need the .NS suffix, e.g. RELIANCE.NS)."
        )
    return info, hist, source


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@dataclass
class Check:
    category: str
    name: str
    value: str          # human-readable value actually observed
    rule: str           # the rule an analyst applies
    status: str         # PASS / WARN / FAIL / N/A
    weight: int = 1
    note: str = ""


@dataclass
class Report:
    ticker: str
    company: str
    sector: str
    industry: str
    currency: str
    price: float | None
    generated_utc: str
    checks: list[Check] = field(default_factory=list)
    score: float | None = None
    verdict: str = ""
    data_coverage: str = ""
    data_source: str = "Yahoo Finance"
    user_provided: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _num(info: dict, key: str):
    v = info.get(key)
    if v is None or isinstance(v, str):
        return None
    try:
        f = float(v)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


def _fmt(v, kind="x"):
    if v is None:
        return "not reported"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "pct_raw":
        return f"{v:.1f}%"
    if kind == "money":
        if abs(v) >= 1e9:
            return f"{v / 1e9:,.2f}B"
        if abs(v) >= 1e6:
            return f"{v / 1e6:,.1f}M"
        return f"{v:,.0f}"
    return f"{v:.2f}"


def _grade(v, good, bad, reverse=False):
    """Return PASS/WARN/FAIL for value v given good/bad thresholds."""
    if v is None:
        return NA
    if reverse:  # lower is better
        if v <= good:
            return PASS
        if v <= bad:
            return WARN
        return FAIL
    if v >= good:
        return PASS
    if v >= bad:
        return WARN
    return FAIL


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if close is None or len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - 100 / (1 + rs)
    val = rsi.dropna()
    return float(val.iloc[-1]) if len(val) else None


# ---------------------------------------------------------------------------
# the analyst checklist
# ---------------------------------------------------------------------------

# Fields the user may enter manually when a source doesn't report them.
# key: (label, how to enter it, enter_as_percent)
MANUAL_FIELDS = {
    "trailingPE":            ("P/E ratio (trailing)", "e.g. 24.5", False),
    "forwardPE":             ("Forward P/E", "e.g. 21.0", False),
    "trailingPegRatio":      ("PEG ratio", "e.g. 1.8", False),
    "priceToBook":           ("Price to book", "e.g. 4.2", False),
    "enterpriseToEbitda":    ("EV / EBITDA", "e.g. 14.0", False),
    "returnOnEquity":        ("Return on equity %", "enter 18 for 18%", True),
    "returnOnAssets":        ("Return on assets %", "enter 7 for 7%", True),
    "operatingMargins":      ("Operating margin %", "enter 15 for 15%", True),
    "profitMargins":         ("Net margin %", "enter 12 for 12%", True),
    "revenueGrowth":         ("Revenue growth yoy %", "enter 10 for 10%", True),
    "earningsGrowth":        ("Earnings growth yoy %", "enter 10 for 10%", True),
    "debtToEquity":          ("Debt/equity %", "enter 45 for 0.45x (45%)", False),
    "currentRatio":          ("Current ratio", "e.g. 1.6", False),
    "totalCash":             ("Total cash (absolute)", "e.g. 25000000000", False),
    "totalDebt":             ("Total debt (absolute)", "e.g. 18000000000", False),
    "freeCashflow":          ("Free cash flow (absolute)", "negative allowed", False),
    "operatingCashflow":     ("Operating cash flow (absolute)", "", False),
    "netIncomeToCommon":     ("Net income (absolute)", "", False),
    "payoutRatio":           ("Dividend payout %", "enter 35 for 35%", True),
    "marketCap":             ("Market cap (absolute)", "e.g. 5000000000", False),
    "averageVolume":         ("Average daily volume (shares)", "e.g. 800000", False),
    "beta":                  ("Beta", "e.g. 1.1", False),
    "heldPercentInstitutions": ("Institutional holding %", "enter 40 for 40%", True),
    "shortPercentOfFloat":   ("Short interest % of float", "enter 3 for 3%", True),
    "recommendationMean":    ("Analyst consensus (1=strong buy … 5=sell)", "e.g. 2.1", False),
    "fiftyDayAverage":       ("50-day moving average price", "", False),
    "twoHundredDayAverage":  ("200-day moving average price", "", False),
    "fiftyTwoWeekLow":       ("52-week low", "", False),
    "fiftyTwoWeekHigh":      ("52-week high", "", False),
}

# which info keys feed each check (used to mark manually-entered values)
_CHECK_KEYS = {
    "P/E ratio": ["trailingPE"], "Forward vs trailing P/E": ["forwardPE", "trailingPE"],
    "PEG ratio": ["trailingPegRatio"], "Price to book": ["priceToBook"],
    "EV / EBITDA": ["enterpriseToEbitda"], "Return on equity": ["returnOnEquity"],
    "Return on assets": ["returnOnAssets"], "Operating margin": ["operatingMargins"],
    "Net margin": ["profitMargins"], "Revenue growth (yoy)": ["revenueGrowth"],
    "Earnings growth (yoy)": ["earningsGrowth"], "Debt to equity": ["debtToEquity"],
    "Current ratio": ["currentRatio"], "Net cash position": ["totalCash", "totalDebt"],
    "Free cash flow": ["freeCashflow"],
    "Earnings quality (OCF / net income)": ["operatingCashflow", "netIncomeToCommon"],
    "Dividend payout ratio": ["payoutRatio"], "Market cap": ["marketCap"],
    "Average daily volume": ["averageVolume"], "Beta (volatility vs market)": ["beta"],
    "Institutional holding": ["heldPercentInstitutions"],
    "Short interest": ["shortPercentOfFloat"], "Analyst consensus": ["recommendationMean"],
    "Price vs 200-day average": ["twoHundredDayAverage"],
    "Trend structure (50 vs 200 DMA)": ["fiftyDayAverage", "twoHundredDayAverage"],
    "52-week range position": ["fiftyTwoWeekLow", "fiftyTwoWeekHigh"],
}


def missing_manual_fields(info: dict) -> dict:
    """Subset of MANUAL_FIELDS the current data source did not report."""
    return {k: v for k, v in MANUAL_FIELDS.items() if _num(info, k) is None}


def run_validations(ticker: str, av_key: str | None = None,
                    overrides: dict | None = None) -> Report:
    info, hist, source = fetch_data(ticker.strip(), av_key)
    return compute_report(ticker, info, hist, source, overrides)


def compute_report(ticker: str, info: dict, hist, source: str,
                   overrides: dict | None = None) -> Report:
    """Build the report. `overrides` = {info_key: float} of values the user
    looked up and entered manually; they fill gaps only (never replace live
    data) and every affected check is labeled as user-provided."""
    ticker = ticker.strip()
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    used_overrides = {k: v for k, v in overrides.items() if _num(info, k) is None}
    if used_overrides:
        info = {**info, **used_overrides}
        source = source + " + manually entered fields"

    close = hist["Close"] if hist is not None and not hist.empty else None
    price = _num(info, "currentPrice") or (float(close.iloc[-1]) if close is not None and len(close) else None)

    checks: list[Check] = []

    def add(category, name, value, rule, status, weight=1, note=""):
        checks.append(Check(category, name, value, rule, status, weight, note))

    # ---- 1. Valuation --------------------------------------------------
    pe = _num(info, "trailingPE")
    add("Valuation", "P/E ratio", _fmt(pe), "Under 25 is comfortable; 25–40 needs growth to justify; above 40 is expensive",
        _grade(pe, 25, 40, reverse=True), weight=2,
        note="Compare with sector peers — a 'high' P/E for a utility can be normal for software.")

    fpe, tpe = _num(info, "forwardPE"), pe
    if fpe is not None and tpe is not None:
        improving = fpe < tpe
        add("Valuation", "Forward vs trailing P/E", f"forward {_fmt(fpe)} vs trailing {_fmt(tpe)}",
            "Forward P/E below trailing means earnings are expected to grow",
            PASS if improving else WARN)
    else:
        add("Valuation", "Forward vs trailing P/E", "not reported", "Forward P/E below trailing", NA)

    peg = _num(info, "trailingPegRatio") or _num(info, "pegRatio")
    add("Valuation", "PEG ratio", _fmt(peg), "Under 1.5 = growth reasonably priced; above 2.5 = paying up",
        _grade(peg, 1.5, 2.5, reverse=True))

    pb = _num(info, "priceToBook")
    add("Valuation", "Price to book", _fmt(pb), "Under 3 conservative, above 8 rich (less meaningful for asset-light firms)",
        _grade(pb, 3, 8, reverse=True))

    ev_ebitda = _num(info, "enterpriseToEbitda")
    add("Valuation", "EV / EBITDA", _fmt(ev_ebitda), "Under 12 comfortable; above 20 expensive",
        _grade(ev_ebitda, 12, 20, reverse=True))

    # ---- 2. Profitability ----------------------------------------------
    roe = _num(info, "returnOnEquity")
    roe_status = _grade(roe, 0.15, 0.08)
    roe_note = ""
    d2e_raw = _num(info, "debtToEquity")
    pb_for_roe = _num(info, "priceToBook")
    if roe is not None and roe > 0.40 and (
        (d2e_raw is not None and d2e_raw > 60) or (pb_for_roe is not None and pb_for_roe > 15)
    ):
        roe_status = WARN
        roe_note = ("ROE above 40% alongside heavy debt or a tiny equity base is usually "
                    "buyback/leverage-inflated — verify with ROIC before trusting it.")
    add("Profitability", "Return on equity", _fmt(roe, "pct"), "Above 15% strong; below 8% weak",
        roe_status, weight=2, note=roe_note)

    roa = _num(info, "returnOnAssets")
    add("Profitability", "Return on assets", _fmt(roa, "pct"), "Above 7% strong; below 3% weak",
        _grade(roa, 0.07, 0.03))

    om = _num(info, "operatingMargins")
    add("Profitability", "Operating margin", _fmt(om, "pct"), "Above 15% strong; below 5% thin",
        _grade(om, 0.15, 0.05))

    nm = _num(info, "profitMargins")
    add("Profitability", "Net margin", _fmt(nm, "pct"), "Positive is the floor; above 10% healthy",
        _grade(nm, 0.10, 0.0001), weight=2)

    # ---- 3. Growth ------------------------------------------------------
    rg = _num(info, "revenueGrowth")
    add("Growth", "Revenue growth (yoy)", _fmt(rg, "pct"), "Above 10% good; shrinking revenue is a red flag",
        _grade(rg, 0.10, 0.0), weight=2)

    eg = _num(info, "earningsGrowth")
    add("Growth", "Earnings growth (yoy)", _fmt(eg, "pct"), "Above 10% good; negative growth needs a story",
        _grade(eg, 0.10, 0.0), weight=2)

    # ---- 4. Balance sheet & liquidity -----------------------------------
    if d2e_raw is not None:
        add("Balance sheet", "Debt to equity", f"{d2e_raw:.0f}%", "Under 80% comfortable; above 200% leveraged",
            _grade(d2e_raw, 80, 200, reverse=True), weight=2,
            note="Banks/NBFCs and utilities naturally run higher leverage — judge vs sector.")
    else:
        add("Balance sheet", "Debt to equity", "not reported", "Under 80% comfortable", NA, weight=2)

    cr = _num(info, "currentRatio")
    add("Balance sheet", "Current ratio", _fmt(cr), "Above 1.2 = can cover short-term liabilities",
        _grade(cr, 1.2, 0.9))

    cash, debt = _num(info, "totalCash"), _num(info, "totalDebt")
    if cash is not None and debt is not None:
        net = cash - debt
        add("Balance sheet", "Net cash position", _fmt(net, "money"),
            "Cash exceeding total debt removes refinancing risk",
            PASS if net > 0 else WARN)
    else:
        add("Balance sheet", "Net cash position", "not reported", "Cash exceeding total debt", NA)

    # ---- 5. Cash flow quality -------------------------------------------
    fcf = _num(info, "freeCashflow")
    add("Cash flow", "Free cash flow", _fmt(fcf, "money"), "Positive FCF — the business funds itself",
        PASS if (fcf is not None and fcf > 0) else (FAIL if fcf is not None else NA), weight=2)

    ocf, ni = _num(info, "operatingCashflow"), _num(info, "netIncomeToCommon")
    if ocf is not None and ni is not None and ni > 0:
        ratio = ocf / ni
        add("Cash flow", "Earnings quality (OCF / net income)", f"{ratio:.2f}",
            "Above 0.8 means profits are backed by real cash, not accruals",
            _grade(ratio, 0.8, 0.5), weight=2)
    else:
        add("Cash flow", "Earnings quality (OCF / net income)", "not reported",
            "Above 0.8 means profits are backed by real cash", NA, weight=2)

    payout = _num(info, "payoutRatio")
    if payout is not None and payout > 0:
        add("Cash flow", "Dividend payout ratio", _fmt(payout, "pct"),
            "Under 60% leaves room to reinvest and protect the dividend",
            _grade(payout, 0.60, 0.90, reverse=True))
    else:
        add("Cash flow", "Dividend payout ratio", "no dividend / not reported",
            "Under 60% sustainable", NA)

    # ---- 6. Size & tradability -------------------------------------------
    mc = _num(info, "marketCap")
    add("Tradability", "Market cap", _fmt(mc, "money"),
        "Above ~2B (large/mid cap) — small caps carry extra liquidity and governance risk",
        _grade(mc, 2e9, 3e8), note="Threshold in the stock's own currency.")

    avol = _num(info, "averageVolume")
    add("Tradability", "Average daily volume", _fmt(avol, "money"),
        "Above 100k shares/day — you can exit without moving the price",
        _grade(avol, 1e5, 2e4))

    # ---- 7. Price action & timing ----------------------------------------
    ma50, ma200 = _num(info, "fiftyDayAverage"), _num(info, "twoHundredDayAverage")
    if close is not None:  # derive from real price history when the source omits them
        if ma50 is None and len(close) >= 50:
            ma50 = float(close.tail(50).mean())
        if ma200 is None and len(close) >= 200:
            ma200 = float(close.tail(200).mean())
    if price and ma200:
        add("Timing", "Price vs 200-day average", f"price {_fmt(price)} vs 200DMA {_fmt(ma200)}",
            "Trading above the 200DMA = long-term uptrend intact",
            PASS if price > ma200 else FAIL, weight=2)
    else:
        add("Timing", "Price vs 200-day average", "not enough history", "Above 200DMA", NA, weight=2)

    if ma50 and ma200:
        add("Timing", "Trend structure (50 vs 200 DMA)", f"50DMA {_fmt(ma50)} vs 200DMA {_fmt(ma200)}",
            "50DMA above 200DMA (golden-cross structure) supports momentum",
            PASS if ma50 > ma200 else WARN)
    else:
        add("Timing", "Trend structure (50 vs 200 DMA)", "not enough history",
            "50DMA above 200DMA", NA)

    lo, hi = _num(info, "fiftyTwoWeekLow"), _num(info, "fiftyTwoWeekHigh")
    if close is not None and len(close) >= 200:
        lo = lo if lo is not None else float(close.min())
        hi = hi if hi is not None else float(close.max())
    if price and lo and hi and hi > lo:
        pos = (price - lo) / (hi - lo) * 100
        status = PASS if 30 <= pos <= 90 else WARN
        add("Timing", "52-week range position", f"{pos:.0f}% of range",
            "30–90% is the sweet spot; near the low may be a falling knife, at the very top is chase risk",
            status)
    else:
        add("Timing", "52-week range position", "not reported", "30–90% of range", NA)

    rsi = _rsi(close) if close is not None else None
    if rsi is not None:
        status = PASS if 40 <= rsi <= 70 else WARN
        add("Timing", "RSI (14-day)", f"{rsi:.0f}",
            "40–70 healthy; above 70 overbought, below 30 oversold",
            status)
    else:
        add("Timing", "RSI (14-day)", "not enough history", "40–70 healthy", NA)

    beta = _num(info, "beta")
    if beta is not None:
        add("Timing", "Beta (volatility vs market)", f"{beta:.2f}",
            "Under 1.3 = market-like swings; higher beta needs a stronger conviction",
            _grade(beta, 1.3, 2.0, reverse=True))
    else:
        add("Timing", "Beta (volatility vs market)", "not reported", "Under 1.3", NA)

    # ---- 8. Ownership & street view --------------------------------------
    inst = _num(info, "heldPercentInstitutions")
    if inst is not None:
        add("Ownership", "Institutional holding", _fmt(inst, "pct"),
            "Above 20% means professional money has done diligence here",
            _grade(inst, 0.20, 0.05))
    else:
        add("Ownership", "Institutional holding", "not reported", "Above 20%", NA)

    short = _num(info, "shortPercentOfFloat")
    if short is not None:
        add("Ownership", "Short interest", _fmt(short, "pct"),
            "Under 5% of float; heavy shorting means smart money is betting against it",
            _grade(short, 0.05, 0.15, reverse=True))
    else:
        add("Ownership", "Short interest", "not reported (common for non-US listings)",
            "Under 5% of float", NA)

    rec = _num(info, "recommendationMean")
    if rec is not None:
        add("Ownership", "Analyst consensus", f"{rec:.1f} (1=strong buy, 5=sell)",
            "Under 2.5 = street leans buy — a sanity check, never the reason to buy",
            _grade(rec, 2.5, 3.5, reverse=True))
    else:
        add("Ownership", "Analyst consensus", "no coverage", "Under 2.5", NA)

    # ---- scoring -----------------------------------------------------------
    pts = {PASS: 1.0, WARN: 0.5, FAIL: 0.0}
    scored = [c for c in checks if c.status != NA]
    total_w = sum(c.weight for c in scored)
    score = round(100 * sum(pts[c.status] * c.weight for c in scored) / total_w, 1) if total_w else None

    for c in checks:  # label anything computed from a manual value
        if any(k in used_overrides for k in _CHECK_KEYS.get(c.name, [])):
            c.note = ("Uses a manually entered value — verify it against official filings. "
                      + c.note).strip()

    fails = sum(1 for c in scored if c.status == FAIL)
    all_w = sum(c.weight for c in checks)
    coverage = total_w / all_w if all_w else 0
    if score is None:
        verdict = "INSUFFICIENT DATA"
    elif coverage < 0.5:
        verdict = (f"PARTIAL DATA ({int(coverage*100)}% of checklist) — score is provisional; "
                   "fill missing fields or retry when data is available")
    elif score >= 75 and fails <= 2:
        verdict = "STRONG CANDIDATE — proceed to deep research"
    elif score >= 60:
        verdict = "WORTH RESEARCHING — resolve the warnings first"
    elif score >= 45:
        verdict = "WEAK — several checklist items failed"
    else:
        verdict = "AVOID FOR NOW — fails the analyst checklist"

    return Report(
        ticker=ticker.upper().strip(),
        company=info.get("longName") or info.get("shortName") or ticker,
        sector=info.get("sector") or "—",
        industry=info.get("industry") or "—",
        currency=info.get("currency") or "",
        price=price,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        checks=checks,
        score=score,
        verdict=verdict,
        data_coverage=f"{len(scored)}/{len(checks)} checks had data",
        data_source=source,
        user_provided=used_overrides,
    )
