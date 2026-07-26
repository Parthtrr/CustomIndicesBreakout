import unittest
from datetime import date

from technical.customIndex.fundamentals import (
    FundamentalMetrics,
    calculate_growth,
    current_result_period,
    parse_screener_html,
    screener_ticker,
)


SAMPLE_HTML = """
<html><body>
  <ul id="top-ratios">
    <li><span class="name">Market Cap</span><span class="number">1,23,456</span></li>
    <li><span class="name">Stock P/E</span><span class="number">23.5</span></li>
    <li><span class="name">ROCE</span><span class="number">18.7%</span></li>
    <li><span class="name">ROE</span><span class="number">15.2%</span></li>
  </ul>
  <section id="quarters"><table>
    <thead><tr><th></th><th>Jun 2025</th><th>Sep 2025</th><th>Dec 2025</th><th>Mar 2026</th><th>Jun 2026</th></tr></thead>
    <tbody>
      <tr><td>Sales +</td><td>100</td><td>105</td><td>110</td><td>120</td><td>150</td></tr>
      <tr><td>Net Profit</td><td>10</td><td>12</td><td>16</td><td>20</td><td>30</td></tr>
      <tr><td>EPS in Rs</td><td>1</td><td>1.2</td><td>1.6</td><td>2</td><td>3</td></tr>
    </tbody>
  </table></section>
  <section id="peers"><p class="sub">
    <a>Industrials</a><a>Capital Goods</a><a>Industrial Products</a><a>Industrial Components</a>
  </p></section>
</body></html>
"""


class FundamentalsTests(unittest.TestCase):
    def test_screener_ticker_removes_yahoo_exchange_suffix(self):
        self.assertEqual(screener_ticker("TCS.NS"), "TCS")
        self.assertEqual(screener_ticker("500325.BO"), "500325")
        self.assertEqual(screener_ticker("M&M"), "M&M")

    def test_current_result_period_follows_latest_completed_quarter(self):
        self.assertEqual(current_result_period(date(2026, 2, 1)), date(2025, 12, 1))
        self.assertEqual(current_result_period(date(2026, 5, 1)), date(2026, 3, 1))
        self.assertEqual(current_result_period(date(2026, 7, 1)), date(2026, 6, 1))
        self.assertEqual(current_result_period(date(2026, 10, 1)), date(2026, 9, 1))

    def test_parser_extracts_ratios_growth_and_current_result_status(self):
        metrics = parse_screener_html(
            "DEMO",
            SAMPLE_HTML,
            "https://www.screener.in/company/DEMO/consolidated/",
            as_of=date(2026, 7, 26),
        )

        self.assertEqual(metrics.market_cap_cr, 123456.0)
        self.assertEqual(metrics.stock_pe, 23.5)
        self.assertEqual(metrics.roce_pct, 18.7)
        self.assertEqual(metrics.roe_pct, 15.2)
        self.assertEqual(metrics.revenue_qoq_pct, 25.0)
        self.assertEqual(metrics.revenue_yoy_pct, 50.0)
        self.assertEqual(metrics.profit_qoq_pct, 50.0)
        self.assertEqual(metrics.profit_yoy_pct, 200.0)
        self.assertTrue(metrics.current_quarter_result_out)
        self.assertEqual(metrics.expected_result_quarter, "Jun 2026")
        self.assertEqual(metrics.latest_reported_quarter, "Jun 2026")
        self.assertEqual(metrics.screener_sector, "Capital Goods")
        self.assertEqual(metrics.screener_industry, "Industrial Components")
        self.assertEqual(metrics.fetch_status, "Retrieved")

    def test_growth_does_not_invent_a_value_when_the_prior_period_is_zero(self):
        self.assertIsNone(calculate_growth(30, 0))
        self.assertIsNone(calculate_growth(None, 20))
        self.assertEqual(calculate_growth(30, 20), 50.0)


if __name__ == "__main__":
    unittest.main()
