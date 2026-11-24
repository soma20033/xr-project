#!/usr/bin/env python3
"""Xr project: a small research and paper-analysis kit. Original code, MIT.
Reads free public data only (Yahoo via yfinance, SEC EDGAR). Places no orders.
Educational use. Not financial advice.

  python xr_project.py research NVDA --sec-ua "Your Name you@example.com"
  python xr_project.py backtest NVDA --years 10
  python xr_project.py size --account 5000 --entry 153 --stop 145 --risk-pct 1
  python xr_project.py timing NVDA --date 2026-11-12      # uses vendored MIT scripts
"""
import argparse, json, subprocess, sys, os, urllib.request
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "vendor", "day-trader-skill")


class KitError(Exception):
    """A problem the user can act on (bad input, no data, network down)."""


def _hist(sym, period="max"):
    try:
        import yfinance as yf
        c = yf.Ticker(sym).history(period=period, auto_adjust=True)["Close"].dropna()
    except Exception as e:  # yfinance raises many types when the network or Yahoo fails
        raise KitError(f"could not fetch prices for {sym}: {e}")
    if c.empty:
        raise KitError(f"no price data for {sym}")
    return c


def _sec(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except Exception as e:
        raise KitError(f"SEC request failed ({url}): {e}")


def _cik(sym, ua):
    d = _sec("https://www.sec.gov/files/company_tickers.json", ua)
    for v in d.values():
        if v["ticker"].upper() == sym.upper():
            return "%010d" % v["cik_str"]
    raise KitError(f"{sym} not found in SEC ticker list")


def _revenue_quarters(by_tag):
    """Three-month revenue rows. Companies switch revenue tags over time, so use the tag with the newest quarter."""
    days = lambda r: (pd.Timestamp(r["end"]) - pd.Timestamp(r["start"])).days
    cands = [[r for r in rows if "start" in r and 80 <= days(r) <= 100] for rows in by_tag.values()]
    cands = [x for x in cands if x]
    if not cands:
        raise KitError("no quarterly revenue found in SEC data")
    return max(cands, key=lambda x: max(r["end"] for r in x))


def _ttm_eps(rows):
    """Trailing 12 months EPS = latest 10-K year + current year-to-date - same year-to-date a year earlier."""
    days = lambda r: (pd.Timestamp(r["end"]) - pd.Timestamp(r["start"])).days
    rows = [r for r in rows if "start" in r]
    annual = sorted((r for r in rows if r["form"] == "10-K" and 350 <= days(r) <= 380), key=lambda r: r["end"])
    if not annual:
        return None
    fy = annual[-1]
    ytd = sorted((r for r in rows if r["form"] == "10-Q" and pd.Timestamp(r["start"]) >= pd.Timestamp(fy["end"]) - pd.Timedelta(days=5)), key=lambda r: (r["end"], days(r)))
    if not ytd:
        return fy["val"]
    cur = ytd[-1]
    prev = [r for r in rows if r["form"] == "10-Q" and abs((pd.Timestamp(cur["start"]) - pd.Timestamp(r["start"])).days - 364) <= 10
            and abs((pd.Timestamp(cur["end"]) - pd.Timestamp(r["end"])).days - 364) <= 10]
    if not prev:
        return None
    return fy["val"] + cur["val"] - prev[0]["val"]


def _wilder_rsi(closes, n=14):
    """RSI per Wilder (1978): first average = simple mean of n changes, then avg = (prev*(n-1)+x)/n."""
    if len(closes) < n + 1:
        raise KitError("not enough price history for RSI")
    ch = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gain = sum(max(x, 0) for x in ch[:n]) / n
    loss = sum(max(-x, 0) for x in ch[:n]) / n
    for x in ch[n:]:
        gain = (gain * (n - 1) + max(x, 0)) / n
        loss = (loss * (n - 1) + max(-x, 0)) / n
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def research(a):
    c = _hist(a.symbol, "2y")
    sma = lambda n: float(c.rolling(n).mean().iloc[-1])
    rsi = _wilder_rsi(c.tolist(), 14)
    y = c[-252:]
    out = {"symbol": a.symbol.upper(), "price_date": str(c.index[-1].date()), "close": round(float(c.iloc[-1]), 2),
           "high_52w": round(float(y.max()), 2), "low_52w": round(float(y.min()), 2),
           "from_high_pct": round((c.iloc[-1] / y.max() - 1) * 100, 1),
           "vs_sma50_pct": round((c.iloc[-1] / sma(50) - 1) * 100, 1), "vs_sma200_pct": round((c.iloc[-1] / sma(200) - 1) * 100, 1),
           "rsi14": round(rsi, 1), "price_source": "Yahoo Finance via yfinance (can lag)"}
    if a.sec_ua:
        cik = _cik(a.symbol, a.sec_ua)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        g = _sec(url, a.sec_ua)["facts"]["us-gaap"]
        def series(tag, unit="USD"):
            return [r for r in g.get(tag, {}).get("units", {}).get(unit, []) if r["form"] in ("10-Q", "10-K")]
        q = _revenue_quarters({t: series(t) for t in ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet") if t in g})
        q.sort(key=lambda r: r["end"])
        last = q[-1]
        prior = [r for r in q if abs((pd.Timestamp(last["end"]) - pd.Timestamp(r["end"])).days - 364) <= 10]
        ni = [r for r in series("NetIncomeLoss") if r.get("start") == last["start"] and r["end"] == last["end"]]
        ttm = _ttm_eps(series("EarningsPerShareDiluted", "USD/shares"))
        out["sec"] = {"source": url, "quarter_end": last["end"], "filed": last["filed"], "accession": last["accn"],
                      "revenue_musd": round(last["val"] / 1e6), "net_income_musd": round(ni[0]["val"] / 1e6) if ni else None,
                      "revenue_yoy_pct": round((last["val"] / prior[0]["val"] - 1) * 100, 1) if prior else None,
                      "eps_ttm_4q": round(ttm, 2) if ttm else None,
                      "pe_from_sec_eps": round(float(c.iloc[-1]) / ttm, 1) if ttm else None}
    else:
        out["sec"] = "skipped: pass --sec-ua 'Name email' (SEC requires a contact user agent)"
    print(json.dumps(out, indent=1, ensure_ascii=False))


def backtest_core(c, years=10, cost_bps=10.0, window=200):
    """200-day trend rule vs buy-and-hold on adjusted closes.
    The signal is read at a close and held from the next day (no lookahead). Each switch costs cost_bps.
    The rule needs `window` days of history before the test window starts; if the series is too short that is an error."""
    if years <= 0 or cost_bps < 0:
        raise KitError("years must be positive and cost cannot be negative")
    start = c.index[-1] - pd.DateOffset(years=years)
    if (c.index < start).sum() < window:
        raise KitError(f"need at least {window} trading days before the {years}-year window starts")
    ret = c.pct_change().fillna(0)
    pos = (c > c.rolling(window).mean()).astype(int).shift(1).fillna(0)
    strat = pos * ret - pos.diff().abs().fillna(0) * cost_bps / 1e4
    t = c.index >= start

    def st(x):
        e = (1 + x[t]).cumprod()
        yrs = (e.index[-1] - e.index[0]).days / 365.25
        return {"growth_x": round(float(e.iloc[-1]), 1), "cagr_pct": round(float(e.iloc[-1] ** (1 / yrs) - 1) * 100, 2),
                "max_drawdown_pct": round(float((e / e.cummax() - 1).min()) * 100, 2)}
    return {"from": str(c.index[t][0].date()), "to": str(c.index[-1].date()),
            "buy_and_hold": st(ret), "rule_result": st(strat), "cost_bps_per_switch": cost_bps}


def backtest(a):
    out = {"symbol": a.symbol.upper(), "rule": "in the stock while close is above its 200-day average",
           **backtest_core(_hist(a.symbol), a.years, a.cost_bps),
           "notes": "Adjusted closes, next-day execution, same window for both, cash earns 0, no tax or slippage. One stock, in-sample: not evidence the rule works."}
    print(json.dumps(out, indent=1))


def size_core(account, entry, stop, risk_pct=1.0, max_position_pct=20.0):
    if min(account, entry, stop) <= 0:
        raise KitError("account, entry and stop must be positive")
    if not 0 < risk_pct <= 100 or not 0 < max_position_pct <= 100:
        raise KitError("risk and position percentages must be between 0 and 100")
    risk_share = entry - stop
    if risk_share <= 0:
        raise KitError("stop must be below entry for a long")
    by_risk = int((account * risk_pct / 100) // risk_share)
    by_cap = int((account * max_position_pct / 100) // entry)
    q = min(by_risk, by_cap)
    return {"shares": q, "position_usd": round(q * entry, 2), "loss_at_stop_usd": round(q * risk_share, 2),
            "loss_pct_of_account": round(q * risk_share / account * 100, 2), "limited_by": "risk" if by_risk <= by_cap else "position cap"}


def size(a):
    print(json.dumps(size_core(a.account, a.entry, a.stop, a.risk_pct, a.max_position_pct), indent=1))


def timing(a):
    env = dict(os.environ)
    now = f"{a.date} 11:30" if a.date else None
    work = os.path.join(os.getcwd(), "xr_project_work"); os.makedirs(work, exist_ok=True)
    def run(script, *args):
        p = subprocess.run([sys.executable, os.path.join(VENDOR, script), *args], cwd=work, capture_output=True, text=True, timeout=120)
        print(p.stdout + p.stderr)
        return p.returncode
    extra = ["--now", now] if now else []
    run("trader-entry/entry.py", "check", a.symbol, "--setup", "orb", "--write", *extra)
    if run("trader-exit/exit.py", "plan", "--stop", "or-mid", "--target", "1R", "--write", *extra) == 0:
        tm = ["--now", f"{a.date} 10:00"] if a.date else []
        run("trader-timemachine/timemachine.py", "run", "--write", *tm)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    r = s.add_parser("research"); r.add_argument("symbol"); r.add_argument("--sec-ua"); r.set_defaults(f=research)
    b = s.add_parser("backtest"); b.add_argument("symbol"); b.add_argument("--years", type=int, default=10); b.add_argument("--cost-bps", type=float, default=10); b.set_defaults(f=backtest)
    z = s.add_parser("size"); z.add_argument("--account", type=float, required=True); z.add_argument("--entry", type=float, required=True); z.add_argument("--stop", type=float, required=True)
    z.add_argument("--risk-pct", type=float, default=1); z.add_argument("--max-position-pct", type=float, default=20); z.set_defaults(f=size)
    t = s.add_parser("timing"); t.add_argument("symbol"); t.add_argument("--date", help="replay a past session YYYY-MM-DD"); t.set_defaults(f=timing)
    a = p.parse_args()
    try:
        a.f(a)
    except KitError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
