# Provenance of Xr project's research and backtest code (draft, for owner review)

This is a technical record, not a legal opinion. It does not claim legal clearance.

## Facts
- Another project, mercan700/claude-stock-trader-skills (commit ddf91ef), is under the PolyForm Noncommercial 1.0.0 licence.
- Its code was read and run by the person and agent who then wrote xr_project.py. So xr_project.py is NOT a clean-room work. Do not describe it as one.
- No file or code from that project is copied into Xr project.
- The timing command uses vendored scripts from Jakeschincariol/day-trader-skill (MIT, commit 3d0f4ef), kept with their licence.

## Comparison done (automated, 2026-11-24)
- Function-level text similarity of Xr project's functions (research, backtest, sizing, EPS, quarters, history) against all functions in the three related files of the noncommercial project: highest ratio 0.17, most 0.0-0.05.
- Exact shared non-trivial lines (over 25 characters): 1, and it is `if __name__ == "__main__":`.
- One near-identical idiom was found: the RSI line used pandas `ewm(alpha=1/14, adjust=False)`. It was replaced by an explicit recursion from Wilder (1978), seeded with a simple average. On 500 random prices both agree to 1e-13 (the seeds converge), and there are two new tests.

## Remaining overlap, all standard textbook methods
- Compare close against a simple moving average, hold from the next day (shift by one bar): a common look-ahead guard.
- Equity curve = cumulative product of (1 + daily return); max drawdown = equity / running max - 1; CAGR = end^(1/years) - 1.
- Same-in-spirit use of the pandas functions `pct_change`, `cumprod`, `cummax`. These are generic pandas operations, not creative expression.

## Primary references that can replace any remaining shared idiom
- RSI: J. Welles Wilder Jr., New Concepts in Technical Trading Systems (1978).
- Drawdown, CAGR: standard definitions, no source needed.
- Position sizing: fixed-fraction risk, risk amount / (entry - stop).
- EPS TTM: SEC XBRL companyfacts (public data, https://data.sec.gov).

## Residual uncertainty
- Someone could still say the structure is derived because the author had seen the other code. Options if that matters: (a) rewrite backtest from a written spec by someone who has not seen it, (b) drop research/backtest and keep only size and timing, (c) link to the other project instead of replicating it.
- Use a licence lawyer for any real clearance question.
