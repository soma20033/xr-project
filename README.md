# Xr project
Small research and paper-analysis kit for stocks. Free public data only (Yahoo via yfinance, SEC EDGAR). It places no orders and connects to no broker. Educational, not financial advice.

    pip install -r requirements.txt
    python xr_project.py research NVDA --sec-ua "Your Name you@example.com"   # price levels, RSI, SEC revenue/net income, P/E from SEC EPS
    python xr_project.py backtest NVDA --years 10                           # 200-day rule vs buy and hold, same window, next-day, 10bp costs
    python xr_project.py size --account 5000 --entry 153 --stop 145         # risk-based share count
    python xr_project.py timing NVDA --date 2026-11-12                      # opening-range check, exit plan, replay (vendored MIT scripts)

Tested 2026-11-24 on NVDA; example outputs in examples/. 26 offline tests: `python -m unittest discover -s tests`. Results match earlier checks: SEC Q2 FY27 revenue 96,221M and net income 59,688M, trailing EPS 7.91, rule CAGR 55.03% vs buy and hold 52.12% (80x vs 66x), and the 12 Nov replay. One stock, in-sample: none of this shows a rule makes money.
Limits: Yahoo data can lag; `timing` needs the vendored scripts and live Yahoo 5-minute data; tests cover the pure logic with synthetic data, not live Yahoo or SEC behaviour.
See NOTICE.md for provenance and licences.
