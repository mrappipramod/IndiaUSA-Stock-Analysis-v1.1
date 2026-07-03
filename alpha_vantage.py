"""
Alpha Vantage fallback — an OFFICIAL free API (get a key at
https://www.alphavantage.co/support/#api-key), used automatically when Yahoo
rate-limits the server.

Free tier: 25 requests/day, 5/minute. Each analysis here costs 2 requests
(OVERVIEW for fundamentals + TIME_SERIES_DAILY for prices), so ~12 fresh
stocks per day — combined with the app's 1-hour cache that goes a long way.

The response is mapped into the same field names yfinance uses, so
validations.py works unchanged. Fields Alpha Vantage doesn't provide
(debt/equity, current ratio, cash flow, volume, ownership) stay missing and
show as N/A — never invented.

Note: Alpha Vantage covers US and many global listings, but NSE (.NS) Indian
symbols are generally NOT supported. Yahoo remains the primary source; this
is a safety net so the app keeps working during rate-limit windows.
"""

from __future__ import annotations

import requests
import pandas as pd

BASE = "https://www.alphavantage.co/query"


class AlphaVantageError(Exception):
    pass


def _get(params: dict, key: str) -> dict:
    params = {**params, "apikey": key}
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    # AV signals problems inside a 200 response
    for bad in ("Note", "Information", "Error Message"):
        if bad in data:
            raise AlphaVantageError(data[bad])
    return data


def _f(d: dict, k: str):
    v = d.get(k)
    if v in (None, "None", "-", ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch(ticker: str, api_key: str):
    """Return (info_dict, history_df) shaped like yfinance's output."""
    ov = _get({"function": "OVERVIEW", "symbol": ticker}, api_key)
    if not ov or not ov.get("Name"):
        raise AlphaVantageError(
            f"Alpha Vantage has no fundamentals for '{ticker}'. "
            "It covers US and major global listings; NSE (.NS) symbols are usually unsupported."
        )

    ts = _get({"function": "TIME_SERIES_DAILY", "symbol": ticker,
               "outputsize": "compact"}, api_key)
    series = ts.get("Time Series (Daily)", {})
    if series:
        hist = pd.DataFrame(
            {"Close": {pd.Timestamp(d): float(v["4. close"]) for d, v in series.items()}}
        ).sort_index()
        price = float(hist["Close"].iloc[-1])
    else:
        hist, price = pd.DataFrame(), None

    info = {
        "longName": ov.get("Name"),
        "sector": (ov.get("Sector") or "").title() or None,
        "industry": (ov.get("Industry") or "").title() or None,
        "currency": ov.get("Currency"),
        "currentPrice": price,
        "trailingPE": _f(ov, "PERatio"),
        "forwardPE": _f(ov, "ForwardPE"),
        "trailingPegRatio": _f(ov, "PEGRatio"),
        "priceToBook": _f(ov, "PriceToBookRatio"),
        "enterpriseToEbitda": _f(ov, "EVToEBITDA"),
        "returnOnEquity": _f(ov, "ReturnOnEquityTTM"),
        "returnOnAssets": _f(ov, "ReturnOnAssetsTTM"),
        "operatingMargins": _f(ov, "OperatingMarginTTM"),
        "profitMargins": _f(ov, "ProfitMargin"),
        "revenueGrowth": _f(ov, "QuarterlyRevenueGrowthYOY"),
        "earningsGrowth": _f(ov, "QuarterlyEarningsGrowthYOY"),
        "payoutRatio": _f(ov, "PayoutRatio"),
        "marketCap": _f(ov, "MarketCapitalization"),
        "beta": _f(ov, "Beta"),
        "fiftyDayAverage": _f(ov, "50DayMovingAverage"),
        "twoHundredDayAverage": _f(ov, "200DayMovingAverage"),
        "fiftyTwoWeekLow": _f(ov, "52WeekLow"),
        "fiftyTwoWeekHigh": _f(ov, "52WeekHigh"),
        "heldPercentInstitutions": (
            _f(ov, "PercentInstitutions") / 100
            if _f(ov, "PercentInstitutions") is not None else None
        ),
        # not provided by OVERVIEW — left absent on purpose (will show N/A):
        # debtToEquity, currentRatio, totalCash, totalDebt, freeCashflow,
        # operatingCashflow, netIncomeToCommon, averageVolume,
        # shortPercentOfFloat, recommendationMean
    }
    return info, hist
