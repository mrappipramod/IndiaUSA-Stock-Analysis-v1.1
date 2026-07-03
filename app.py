"""Pre-Buy Stock Validator — Streamlit app.

Run locally:   streamlit run app.py
Data source:   Yahoo Finance via the free `yfinance` library (no API key).
Storage:       each analysis is committed as JSON to your GitHub repo.
"""

import pandas as pd
import streamlit as st

from validations import fetch_data, compute_report, missing_manual_fields, MANUAL_FIELDS, RateLimited, PASS, WARN, FAIL, NA
import github_store

st.set_page_config(page_title="Pre-Buy Stock Validator", page_icon="✅", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch(symbol: str, av_key: str | None):
    """Cache raw data 1h so repeat lookups and manual re-scoring never re-hit Yahoo."""
    info, hist, source = fetch_data(symbol, av_key)
    return info, hist, source


ICON = {PASS: "✅", WARN: "⚠️", FAIL: "❌", NA: "➖"}

st.title("✅ Pre-Buy Stock Validator")
st.caption(
    "The checklist a financial analyst runs before buying a stock — valuation, profitability, "
    "growth, balance sheet, cash-flow quality, tradability, timing and ownership. "
    "All numbers come live from Yahoo Finance; anything Yahoo doesn't report is shown as N/A, never invented."
)

# ---------------- sidebar ----------------
with st.sidebar:
    st.header("Analyze a stock")
    ticker = st.text_input("Ticker symbol", placeholder="AAPL, RELIANCE.NS, TCS.NS …").strip()
    st.caption("Indian stocks: add **.NS** (NSE) or **.BO** (BSE).")
    go = st.button("Run validation", type="primary", use_container_width=True)

    st.divider()
    st.subheader("Backup data source")
    av_key = st.secrets.get("ALPHAVANTAGE_KEY", "")
    if av_key:
        st.success("Alpha Vantage fallback active")
    else:
        st.info("Optional: add a free ALPHAVANTAGE_KEY in secrets "
                "(alphavantage.co/support/#api-key) and the app auto-switches to the "
                "official Alpha Vantage API whenever Yahoo rate-limits. "
                "US & global tickers only — NSE (.NS) stays Yahoo-only.")

    st.divider()
    st.subheader("GitHub storage")
    gh_ok = "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets
    if gh_ok:
        st.success(f"Saving to `{st.secrets['GITHUB_REPO']}`")
    else:
        st.info("Add GITHUB_TOKEN and GITHUB_REPO in app secrets to save every "
                "analysis permanently to your repo (see README).")

    st.divider()
    st.caption("Educational screen, not investment advice. Verify numbers in the "
               "company's filings before acting.")

# ---------------- run ----------------
if go and ticker:
    try:
        with st.spinner(f"Pulling Yahoo Finance data for {ticker.upper()} … (retries automatically if rate-limited)"):
            info, hist, source = cached_fetch(ticker.upper(), av_key or None)
        st.session_state["fetched"] = (ticker.upper(), info, hist, source)
        st.session_state["overrides"] = {}
        st.session_state["report"] = compute_report(ticker.upper(), info, hist, source)
    except ValueError as e:
        st.error(str(e))
    except RateLimited:
        st.error("Yahoo is rate-limiting this server even after 4 retries, and no backup "
                 "source is configured. Add a free ALPHAVANTAGE_KEY in the app secrets "
                 "(link in the sidebar) so this never blocks you — or wait 2–5 minutes; "
                 "successful results are cached for an hour.")
    except Exception as e:
        st.error(f"Data fetch failed: {e}")

report = st.session_state.get("report")

if report:
    # -------- header metrics --------
    c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
    c1.metric(report.company, f"{report.currency} {report.price:,.2f}" if report.price else "—",
              help=f"{report.sector} · {report.industry}")
    c2.metric("Checklist score", f"{report.score}/100" if report.score is not None else "—")
    counts = pd.Series([c.status for c in report.checks]).value_counts()
    c3.metric("Pass / Warn / Fail",
              f"{counts.get(PASS,0)} / {counts.get(WARN,0)} / {counts.get(FAIL,0)}")
    c4.metric("Verdict", report.verdict.split("—")[0].strip(),
              help=report.verdict)

    st.caption(f"{report.data_coverage} · generated {report.generated_utc} · source: {report.data_source}")

    if report.score is not None:
        st.progress(min(report.score / 100, 1.0))

    # -------- checks by category --------
    df = pd.DataFrame([{
        "Category": c.category, "Check": c.name, "Observed": c.value,
        "Analyst rule": c.rule, "Status": c.status, "Note": c.note,
    } for c in report.checks])

    for cat in df["Category"].unique():
        sub = df[df["Category"] == cat]
        fails = (sub["Status"] == FAIL).sum()
        warns = (sub["Status"] == WARN).sum()
        label = f"{cat}  ·  {'❌'*fails}{'⚠️'*warns}" if (fails or warns) else f"{cat}  ·  ✅"
        with st.expander(label, expanded=(fails > 0)):
            for _, row in sub.iterrows():
                a, b = st.columns([3, 1])
                a.markdown(f"**{row['Check']}** — {row['Observed']}  \n"
                           f"<small>{row['Analyst rule']}</small>", unsafe_allow_html=True)
                b.markdown(f"### {ICON[row['Status']]} {row['Status']}")
                if row["Note"]:
                    st.info(row["Note"], icon="💡")

    # -------- fill gaps manually --------
    missing = missing_manual_fields(
        {**st.session_state["fetched"][1], **st.session_state.get("overrides", {})}
    ) if "fetched" in st.session_state else {}
    if missing:
        with st.expander(f"✍️ Fill missing data manually ({len(missing)} fields unavailable from the source)"):
            st.markdown(
                "Look these up yourself and enter them — the score recalculates with your "
                "numbers, and every affected check is **labeled as manually entered**. "
                "Good free sources: "
                "[stockanalysis.com](https://stockanalysis.com), "
                "[screener.in](https://www.screener.in) (Indian stocks), "
                "[finance.yahoo.com](https://finance.yahoo.com) (works in a browser even "
                "when this server is rate-limited), or the company's latest filings."
            )
            cols = st.columns(3)
            new_vals = {}
            for i, (key, (label, hint, is_pct)) in enumerate(missing.items()):
                with cols[i % 3]:
                    v = st.number_input(label, value=None, help=hint or None,
                                        format="%.4f", key=f"man_{key}")
                    if v is not None:
                        new_vals[key] = v / 100 if is_pct else v
            if st.button("🔁 Recalculate score with my numbers", type="primary"):
                st.session_state["overrides"] = {**st.session_state.get("overrides", {}), **new_vals}
                tkr, info, hist, source = st.session_state["fetched"]
                st.session_state["report"] = compute_report(
                    tkr, info, hist, source, overrides=st.session_state["overrides"])
                st.rerun()

    if report.user_provided:
        st.warning(f"{len(report.user_provided)} field(s) in this score were entered manually "
                   "and are not independently verified — double-check them against official "
                   "filings before acting.", icon="✍️")

    # -------- save / export --------
    st.divider()
    left, right = st.columns(2)
    with left:
        import json as _json
        st.download_button("⬇️ Download report (JSON)",
                           data=_json.dumps(report.to_dict(), indent=1),
                           file_name=f"{report.ticker}_validation.json",
                           mime="application/json", use_container_width=True)
    with right:
        if gh_ok:
            if st.button("💾 Save to GitHub", use_container_width=True):
                try:
                    url = github_store.save_report(
                        report.to_dict(),
                        token=st.secrets["GITHUB_TOKEN"],
                        repo=st.secrets["GITHUB_REPO"],
                        branch=st.secrets.get("GITHUB_BRANCH", "main"),
                    )
                    st.success(f"Committed to your repo → [{url.split('/')[-1]}]({url})")
                except Exception as e:
                    st.error(str(e))
        else:
            st.button("💾 Save to GitHub (configure secrets first)", disabled=True,
                      use_container_width=True)

# ---------------- history ----------------
if "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
    st.divider()
    with st.expander("📁 Saved analyses (from GitHub)"):
        try:
            files = github_store.list_reports(
                st.secrets["GITHUB_TOKEN"], st.secrets["GITHUB_REPO"],
                st.secrets.get("GITHUB_BRANCH", "main"))
            if not files:
                st.write("Nothing saved yet — run a validation and hit *Save to GitHub*.")
            else:
                rows = []
                for f in files[-50:]:
                    try:
                        r = github_store.load_report(f["download_url"], st.secrets["GITHUB_TOKEN"])
                        rows.append({"Ticker": r["ticker"], "Company": r["company"],
                                     "Score": r["score"], "Verdict": r["verdict"],
                                     "When (UTC)": r["generated_utc"]})
                    except Exception:
                        continue
                if rows:
                    st.dataframe(pd.DataFrame(rows).sort_values("When (UTC)", ascending=False),
                                 use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Couldn't list saved analyses: {e}")

if not report:
    st.info("Enter a ticker in the sidebar to run the 25-point pre-buy checklist. "
            "Try **AAPL**, **MSFT**, **RELIANCE.NS** or **TCS.NS**.")
