# 📊 Alert Scoreboard — does the 80+ system actually work?

_Updated 2026-08-28T21:47:09+00:00 · returns are % vs first close after alert · alpha = stock return − benchmark (Nifty 50 for .NS, S&P 500 otherwise) · blank = horizon not reached yet_

| Ticker | Alerted | 30d | α30 | 90d | α90 | 180d | α180 | To date | α |
|---|---|---|---|---|---|---|---|---|---|
| ATUL.NS | 2026-07-03 | +3.9% | +1.8% |  |  |  |  | +0.9% | +1.7% |
| LUPIN.NS | 2026-07-03 | -2.6% | -4.7% |  |  |  |  | -12.2% | -11.5% |
| GRANULES.NS | 2026-07-03 | +1.3% | -0.7% |  |  |  |  | +0.0% | +0.8% |
| AFL | 2026-07-03 | +5.2% | +4.3% |  |  |  |  | -2.8% | -5.1% |
| AUBANK.NS | 2026-07-03 | +0.2% | -1.8% |  |  |  |  | +3.2% | +3.9% |
| KPIL.NS | 2026-07-03 | -7.3% | -9.3% |  |  |  |  | +0.5% | +1.2% |
| COALINDIA.NS | 2026-07-03 | -3.9% | -6.0% |  |  |  |  | -7.6% | -6.9% |
| CIEINDIA.NS | 2026-07-03 | -10.9% | -13.0% |  |  |  |  | -16.2% | -15.5% |
| RBLBANK.NS | 2026-07-03 | +5.2% | +3.1% |  |  |  |  | +7.0% | +7.8% |
| ALGN | 2026-07-03 | -8.2% | -9.1% |  |  |  |  | -16.4% | -18.7% |
| JSWSTEEL.NS | 2026-07-09 | +6.2% | +3.6% |  |  |  |  | +9.1% | +8.6% |
| EMCURE.NS | 2026-07-09 | +10.3% | +7.7% |  |  |  |  | +3.8% | +3.3% |
| ENDURANCE.NS | 2026-07-10 | +11.0% | +9.4% |  |  |  |  | +10.1% | +10.6% |
| ANGELONE.NS | 2026-07-17 | -10.5% | -10.3% |  |  |  |  | -9.8% | -8.8% |
| FEDERALBNK.NS | 2026-07-23 | +1.3% | -0.2% |  |  |  |  | -2.4% | -3.3% |
| KARURVYSYA.NS | 2026-07-23 | +1.1% | -0.3% |  |  |  |  | +3.6% | +2.7% |
| OBEROIRLTY.NS | 2026-07-23 | +2.9% | +1.4% |  |  |  |  | +3.0% | +2.1% |
| BALL | 2026-07-23 | +3.5% | +0.2% |  |  |  |  | +2.5% | -1.6% |
| ABSLAMC.NS | 2026-07-23 | +1.3% | -0.2% |  |  |  |  | +6.1% | +5.2% |
| CUB.NS | 2026-07-30 |  |  |  |  |  |  | +7.4% | +8.3% |
| EOG | 2026-07-30 |  |  |  |  |  |  | -1.5% | -5.2% |
| CINF | 2026-07-30 |  |  |  |  |  |  | -1.6% | -5.3% |
| BANDHANBNK.NS | 2026-07-30 |  |  |  |  |  |  | -0.9% | +0.0% |
| USHAMART.NS | 2026-07-30 |  |  |  |  |  |  | -1.9% | -1.0% |
| GL | 2026-07-30 |  |  |  |  |  |  | -5.6% | -9.3% |
| RJF | 2026-07-30 |  |  |  |  |  |  | +2.5% | -1.2% |
| ZFCVINDIA.NS | 2026-07-31 |  |  |  |  |  |  | +6.3% | +7.5% |
| WELCORP.NS | 2026-07-31 |  |  |  |  |  |  | +45.8% | +47.0% |
| JPPOWER.NS | 2026-07-31 |  |  |  |  |  |  | -7.5% | -6.3% |
| NATIONALUM.NS | 2026-08-06 |  |  |  |  |  |  | +2.4% | +4.7% |
| GESHIP.NS | 2026-08-06 |  |  |  |  |  |  | -1.6% | +0.6% |
| AUROPHARMA.NS | 2026-08-07 |  |  |  |  |  |  | -1.3% | +0.7% |
| GAIL.NS | 2026-08-07 |  |  |  |  |  |  | -0.7% | +1.3% |
| GLENMARK.NS | 2026-08-13 |  |  |  |  |  |  | +6.0% | +7.3% |
| FINCABLES.NS | 2026-08-13 |  |  |  |  |  |  | +3.4% | +4.6% |
| HINDALCO.NS | 2026-08-20 |  |  |  |  |  |  | -0.6% | +0.0% |
| KAJARIACER.NS | 2026-08-20 |  |  |  |  |  |  | -1.7% | -1.1% |
| COP | 2026-08-28 |  |  |  |  |  |  | +0.0% | +0.0% |
| OXY | 2026-08-28 |  |  |  |  |  |  | +0.0% | +0.0% |
| CF | 2026-08-28 |  |  |  |  |  |  | +0.0% | +0.0% |

## Verdict so far

- **30-day** (19 alerts matured): median alpha **-0.2%**, beat benchmark 8/19 times
- **to date** (40 alerts matured): median alpha **+0.3%**, beat benchmark 22/40 times

> Judgement rule: wait for **20+ matured alerts**. If median 90-day alpha is around zero or negative, the system isn't beating the index — lower conviction or fix the checklist. A handful of alerts proves nothing either way.
