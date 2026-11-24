# Provenance and licences

This is a record of where each part came from. It is not legal advice or a legal clearance.

## Original code (MIT, see LICENSE)
- xr_project.py and tests/test_xr_project.py were written for this project.
- The research, backtest and sizing functions are our own code using standard, widely used formulas (moving average, RSI, next-day execution with a switching cost, risk-based position size, trailing EPS from SEC filings).

## Third-party code included unchanged
- vendor/day-trader-skill/ (trader-entry, trader-exit, trader-timemachine) is copied unmodified from
  https://github.com/Jakeschincariol/day-trader-skill at commit 3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd.
  MIT licence, Copyright (c) 2026 Jake Schincariol. The licence file is kept at vendor/day-trader-skill/LICENSE and must stay with those files.

## Looked at, not included
- https://github.com/mercan700/claude-stock-trader-skills is under the PolyForm Noncommercial 1.0.0 licence. No file or code from it is included here.
  Its code was read during the comparison before Xr project's own functions were written. The functions are our own writing, but they do the same kind of job with standard formulas.
  Remaining uncertainty: a reviewer could compare the two and decide the similarity is too close. If that matters, rewrite xr_project.py's research and backtest functions from a clean specification, or link to that project instead of replicating it.
- https://github.com/tradermonty/claude-trading-skills (MIT, Copyright (c) 2026 TraderMonty): nothing copied. The sizing function is a plain formula.

## Data
Prices come from Yahoo Finance through the yfinance package, and fundamentals from SEC EDGAR. Their terms apply to use of the data. Check them before using this for anything beyond personal learning.

See PROVENANCE.md for the similarity check, the RSI rewrite from Wilder (1978), and why this is not described as clean-room.
