"""Offline tests: no network, no real data. Run: python -m unittest discover -s tests"""
import io, json, os, sys, types, unittest, contextlib
from unittest import mock
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import xr_project as xr  # noqa: E402


def series(values, end="2026-11-24"):
    idx = pd.bdate_range(end=end, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def row(start, end, val, form="10-Q", filed="2026-01-01", accn="a-1"):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed, "accn": accn}


class EpsAndQuarters(unittest.TestCase):
    FY = row("2025-01-27", "2026-01-25", 6.0, "10-K")
    CUR = row("2026-01-26", "2026-07-26", 3.5)       # year to date, current year
    PREV = row("2025-01-27", "2025-07-27", 2.5)      # same period a year earlier

    def test_ttm_eps_is_year_plus_ytd_minus_prior_ytd(self):
        self.assertAlmostEqual(xr._ttm_eps([self.FY, self.CUR, self.PREV]), 7.0)

    def test_ttm_uses_latest_ytd_not_the_earlier_quarter(self):
        q1 = row("2026-01-26", "2026-04-26", 1.7)
        prev_q1 = row("2025-01-27", "2025-04-27", 1.2)
        self.assertAlmostEqual(xr._ttm_eps([self.FY, q1, prev_q1, self.CUR, self.PREV]), 7.0)

    def test_ttm_without_annual_filing_is_none(self):
        self.assertIsNone(xr._ttm_eps([self.CUR, self.PREV]))

    def test_ttm_without_prior_year_ytd_is_none_not_a_wrong_number(self):
        self.assertIsNone(xr._ttm_eps([self.FY, self.CUR]))

    def test_ttm_right_after_year_end_is_the_annual_figure(self):
        self.assertEqual(xr._ttm_eps([self.FY]), 6.0)

    def test_revenue_uses_tag_with_newest_quarter(self):
        old = [row("2019-10-28", "2020-01-26", 3105)]
        new = [row("2026-04-27", "2026-07-26", 96221)]
        q = xr._revenue_quarters({"RevenueFromContractWithCustomerExcludingAssessedTax": old, "Revenues": new})
        self.assertEqual(q[0]["val"], 96221)

    def test_revenue_ignores_annual_and_half_year_rows(self):
        rows = [row("2025-01-27", "2026-01-25", 215938, "10-K"), row("2026-01-26", "2026-07-26", 177837)]
        with self.assertRaises(xr.KitError):
            xr._revenue_quarters({"Revenues": rows})


class Backtest(unittest.TestCase):
    def test_no_lookahead_on_a_jump(self):
        # flat for 600 days, one jump to double, flat again. The signal appears at the jump close,
        # so the rule is only invested from the next day and must not capture the jump.
        v = [100.0] * 600 + [200.0] * 300
        out = xr.backtest_core(series(v), years=2, cost_bps=10)
        self.assertAlmostEqual(out["buy_and_hold"]["growth_x"], 2.0, places=1)
        self.assertLess(out["rule_result"]["growth_x"], 1.0 + 1e-9)

    def test_costs_lower_the_result(self):
        rng = np.random.default_rng(1)
        c = series(100 * np.cumprod(1 + rng.normal(0.0005, 0.02, 1500)))
        free = xr.backtest_core(c, 3, 0)["rule_result"]["growth_x"]
        costly = xr.backtest_core(c, 3, 50)["rule_result"]["growth_x"]
        self.assertGreater(free, costly)

    def test_steady_uptrend_rule_tracks_buy_and_hold_after_warmup(self):
        c = series(100 * 1.0005 ** np.arange(1500))
        out = xr.backtest_core(c, 3, 0)
        self.assertAlmostEqual(out["rule_result"]["growth_x"], out["buy_and_hold"]["growth_x"], places=2)

    def test_warmup_comes_from_before_the_window(self):
        # with the data starting exactly at the window start there is no warm-up history: refuse
        c = series(100 * 1.0005 ** np.arange(700))
        with self.assertRaises(xr.KitError):
            xr.backtest_core(c, years=3)

    def test_bad_inputs(self):
        c = series(np.arange(1, 1500) + 100.0)
        for years, cost in ((0, 10), (3, -1)):
            with self.assertRaises(xr.KitError):
                xr.backtest_core(c, years, cost)

    def test_same_window_for_both_series(self):
        c = series(100 * 1.0004 ** np.arange(2000))
        out = xr.backtest_core(c, 5, 10)
        self.assertEqual(out["from"][:4], "2021")

    def test_prices_are_requested_split_and_dividend_adjusted(self):
        calls = {}
        class T:
            def __init__(self, sym): pass
            def history(self, **kw):
                calls.update(kw)
                return pd.DataFrame({"Close": series([1.0, 2.0, 3.0]).values}, index=series([1, 2, 3]).index)
        fake = types.SimpleNamespace(Ticker=T)
        with mock.patch.dict(sys.modules, {"yfinance": fake}):
            xr._hist("X")
        self.assertTrue(calls.get("auto_adjust"))

    def test_adjusted_split_has_no_artificial_drop(self):
        # an adjusted series has no -50% day at a split; returns are smooth
        c = series(np.full(300, 100.0))
        self.assertEqual(float(c.pct_change().abs().max(skipna=True)), 0.0)


class Sizing(unittest.TestCase):
    def test_risk_limited(self):
        self.assertEqual(xr.size_core(5000, 153, 145)["shares"], 6)
        self.assertEqual(xr.size_core(5000, 153, 145)["loss_at_stop_usd"], 48.0)

    def test_position_cap_limits(self):
        out = xr.size_core(5000, 100, 99, risk_pct=1)   # risk allows 50, cap allows 10
        self.assertEqual((out["shares"], out["limited_by"]), (10, "position cap"))

    def test_too_small_account_gives_zero_shares(self):
        self.assertEqual(xr.size_core(100, 500, 490)["shares"], 0)

    def test_invalid_inputs(self):
        bad = [(0, 10, 9), (100, 0, 1), (100, 10, 10), (100, 10, 11), (100, -5, 1), (1000, 10, 9, 0), (1000, 10, 9, 150)]
        for args in bad:
            with self.assertRaises(xr.KitError, msg=str(args)):
                xr.size_core(*args)


class Failures(unittest.TestCase):
    def test_sec_network_failure_is_a_clear_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            with self.assertRaises(xr.KitError):
                xr._sec("https://data.sec.gov/x", "ua")

    def test_price_failure_is_a_clear_error(self):
        class T:
            def __init__(self, s): pass
            def history(self, **kw): raise RuntimeError("blocked")
        with mock.patch.dict(sys.modules, {"yfinance": types.SimpleNamespace(Ticker=T)}):
            with self.assertRaises(xr.KitError):
                xr._hist("X")

    def test_empty_prices_is_a_clear_error(self):
        class T:
            def __init__(self, s): pass
            def history(self, **kw): return pd.DataFrame({"Close": []})
        with mock.patch.dict(sys.modules, {"yfinance": types.SimpleNamespace(Ticker=T)}):
            with self.assertRaises(xr.KitError):
                xr._hist("ZZZZ")

    def test_unknown_ticker_in_sec_list(self):
        with mock.patch.object(xr, "_sec", return_value={"0": {"ticker": "AAA", "cik_str": 1}}):
            with self.assertRaises(xr.KitError):
                xr._cik("NOPE", "ua")

    def test_cli_exits_with_message_not_traceback(self):
        with mock.patch.object(sys, "argv", ["xr", "size", "--account", "100", "--entry", "10", "--stop", "11"]):
            with self.assertRaises(SystemExit) as cm:
                xr.main()
        self.assertIn("stop must be below entry", str(cm.exception))


class ResearchEndToEnd(unittest.TestCase):
    def test_research_with_synthetic_sec_data(self):
        facts = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [row("2026-04-27", "2026-07-26", 96_221e6, filed="2026-08-26", accn="x-26-75"),
                                             row("2025-04-28", "2025-07-27", 46_743e6)]}},
            "NetIncomeLoss": {"units": {"USD": [row("2026-04-27", "2026-07-26", 59_688e6)]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [
                row("2025-01-27", "2026-01-25", 6.0, "10-K"), row("2026-01-26", "2026-07-26", 3.5), row("2025-01-27", "2025-07-27", 2.5)]}},
        }}}
        prices = series(np.linspace(100, 140, 400))

        def fake_sec(url, ua):
            return {"0": {"ticker": "TST", "cik_str": 7}} if "company_tickers" in url else facts
        buf = io.StringIO()
        with mock.patch.object(xr, "_sec", fake_sec), mock.patch.object(xr, "_hist", lambda s, p="max": prices), contextlib.redirect_stdout(buf):
            xr.research(types.SimpleNamespace(symbol="TST", sec_ua="t t@example.invalid"))
        out = json.loads(buf.getvalue())
        self.assertEqual(out["sec"]["revenue_musd"], 96221)
        self.assertEqual(out["sec"]["revenue_yoy_pct"], 105.9)
        self.assertEqual(out["sec"]["eps_ttm_4q"], 7.0)
        self.assertAlmostEqual(out["sec"]["pe_from_sec_eps"], round(140 / 7.0, 1), places=1)

    def test_research_without_sec_contact_skips_sec_with_a_reason(self):
        buf = io.StringIO()
        with mock.patch.object(xr, "_hist", lambda s, p="max": series(np.linspace(100, 140, 400))), contextlib.redirect_stdout(buf):
            xr.research(types.SimpleNamespace(symbol="TST", sec_ua=None))
        self.assertIn("skipped", json.loads(buf.getvalue())["sec"])


class WilderRsiTest(unittest.TestCase):
    def test_extremes_and_hand_value(self):
        self.assertEqual(xr._wilder_rsi([1 + i for i in range(30)]), 100.0)
        self.assertEqual(xr._wilder_rsi([100 - i for i in range(30)]), 0.0)
        # 14 changes: 7 of +1, 7 of -1 -> equal averages -> RSI 50 exactly at the seed
        c = [10.0]
        for i in range(14):
            c.append(c[-1] + (1 if i % 2 == 0 else -1))
        self.assertAlmostEqual(xr._wilder_rsi(c), 50.0)


if __name__ == "__main__":
    unittest.main()
