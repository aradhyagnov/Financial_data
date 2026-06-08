# Stock Data & Strategy Metrics Toolkit

A small two-script toolkit for a quantitative backtesting workflow:

1. **`extract_financials.py`** — pulls raw price + fundamental data for a list of
   tickers from Yahoo Finance and saves it as CSV.
2. **`strategy_metrics.py`** — backtests a trading strategy on that price data and
   computes the performance metrics (hit-rate, ARR, max drawdown, Sharpe,
   capital vs. benchmarks) using the **same definitions as the columns in
   `projj_filled.xlsx`**.

The intended flow is: **extract data → run strategies → read metrics**.

---

## Requirements

```bash
pip install yfinance pandas numpy
```

- `yfinance` — data source (free, no API key).
- `pandas`, `numpy` — used by both scripts.

Tested with `yfinance 1.4.1`. Works as-is on Windows, macOS, and Linux
(all paths use `pathlib`).

---

## 1. `extract_financials.py` — pull raw data

Downloads, per ticker: raw OHLCV prices, a key-stats snapshot, the three
financial statements (annual + quarterly), and corporate-action history.

### Configure

Edit the `CONFIG` block at the top:

| Setting | Default | Notes |
|---|---|---|
| `TICKERS` | `["AMZN", "MSFT", "PEP", "NVDA"]` | Amazon, Microsoft, Pepsi, Nvidia |
| `PRICE_PERIOD` | `"5y"` | `1y`, `2y`, `5y`, `10y`, `max`, … |
| `PRICE_INTERVAL` | `"1d"` | `1d`, `1wk`, `1mo` |
| `AUTO_ADJUST` | `False` | `True` → split/dividend-adjusted OHLC |
| `OUTPUT_DIR` | `financial_data` | root folder for output |

> **Tip:** add `"SPY"` to `TICKERS` so the backtester can use it as the
> market benchmark (the "vs SPY" metric). Otherwise `strategy_metrics.py`
> will fetch SPY from Yahoo on the fly.

### Run

```bash
python extract_financials.py
```

### Output layout

```
financial_data/
├── AMZN/
│   ├── prices.csv              # raw OHLCV (+ Dividends / Stock Splits cols)
│   ├── info.csv                # market cap, P/E, sector, margins, debt, …
│   ├── income_annual.csv       # income statement (annual)
│   ├── income_quarterly.csv    # income statement (quarterly)
│   ├── balance_annual.csv      # balance sheet (annual)
│   ├── balance_quarterly.csv   # balance sheet (quarterly)
│   ├── cashflow_annual.csv     # cash flow (annual)
│   ├── cashflow_quarterly.csv  # cash flow (quarterly)
│   ├── dividends.csv           # dividend history
│   └── splits.csv              # split history
├── MSFT/  …
├── PEP/   …
└── NVDA/  …
```

Each data fetch is wrapped in its own `try/except`, so if Yahoo rate-limits
one statement the rest still save.

---

## 2. `strategy_metrics.py` — backtest & metrics

### The strategy interface

A "strategy" is just a function that returns the **desired position** at each
bar's close:

```python
def my_strategy(price_df, **params) -> pd.Series:
    # 1.0 = long, 0.0 = flat, -1.0 = short (fractional exposures allowed)
    ...
```

The engine lags that position by one bar before applying returns, so a signal
computed at today's close earns **tomorrow's** return — **no look-ahead bias**
as long as your signal only uses past/current data.

Two example strategies ship with the file: `sma_crossover` and `rsi_reversion`.

### Usage

```python
from strategy_metrics import (
    backtest, evaluate_strategies, load_prices,
    sma_crossover, rsi_reversion,
)

# load price data (reads the CSV from script 1, else downloads via yfinance)
price = load_prices("AMZN", csv_path="financial_data/AMZN/prices.csv")
spy   = load_prices("SPY",  csv_path="financial_data/SPY/prices.csv")["Close"]

# --- one strategy ---
metrics, curves = backtest(
    price, sma_crossover, spy_close=spy,
    fast=20, slow=150, cost_bps=5,        # cost_bps = 0.05% on exposure changes
)
print(metrics)

# --- many strategies → one metrics row each (like the spreadsheet grid) ---
table = evaluate_strategies(price, {
    "sma_cross(20,150)": (sma_crossover, {"fast": 20, "slow": 150}),
    "rsi_reversion(14)":  (rsi_reversion, {"period": 14, "lower": 30, "upper": 70}),
}, spy_close=spy, cost_bps=5)
print(table)
```

`backtest()` returns `(metrics_dict, curves_df)`. The `curves` DataFrame holds
`asset_ret`, `position`, `strat_ret`, `equity_strat`, and `equity_buyhold` so you
can plot or audit the equity path.

### Run the built-in demo

```bash
python strategy_metrics.py
```

---

## Metric reference

The metric keys map directly onto the `projj_filled.xlsx` columns:

| Code key | Spreadsheet column | Definition |
|---|---|---|
| `arr` | ARR | CAGR of the equity curve, annualized (252 trading days) |
| `hit_rate` | Hit-rate | winning round-trip trades ÷ total trades |
| `max_drawdown` | Maximum Drawdown | worst peak-to-trough decline (≤ 0) |
| `sharpe` | Sharpe Ratio | annualized, √252 × mean ÷ std of per-bar returns |
| `cap_vs_buyhold` | Current Capital / Buy & Hold | strategy final equity ÷ buy-&-hold final |
| `cap_vs_spy` | Current Capital / SPY | strategy final equity ÷ SPY buy-&-hold final |
| `n_trades` | — | number of round-trip trades |
| `total_return` | — | cumulative return over the window |
| `final_capital` | — | ending equity (starts at 1.0) |

**Annualization** is controlled by `PERIODS_PER_YEAR` (252 daily / 52 weekly /
12 monthly) — match it to your bar frequency.

---

## End-to-end example

```bash
# 1. pull data for the four stocks + SPY benchmark
#    (add "SPY" to TICKERS in extract_financials.py first)
python extract_financials.py

# 2. backtest and print the metrics table
python strategy_metrics.py
```

---

## Results — analysis of `projj_filled.xlsx`

The source workbook contains a backtest of **5,523 stocks × 150 strategy/parameter
combinations** (828,450 rows in the `train` sheet), plus a curated `final rank`
sheet of the top performers.

### How the ranking is built

For each stock, its **champion** = the single strategy/parameter combo with the
highest 3-year ARR. Ranking all 5,523 champions by ARR gives each stock's
"rank in the file." Reference points across the full universe:

- **Median** champion ARR: **17.6%**
- **Top-decile** champion ARR cutoff: **87%**

### The 15 most famous stocks, ranked best → worst

Where each megacap's champion strategy lands against all 5,523 stocks:

| # | Ticker | Company | Rank | ARR | Sharpe | vs B&H | vs SPY |
|---|--------|---------|-----:|------:|-------:|-------:|-------:|
| 1 | AAPL | Apple | 2,247 | 23.2% | 2.02 | 1.07× | 1.04× |
| 2 | GOOGL | Alphabet | 2,352 | 21.8% | 1.29 | 0.63× | 1.01× |
| 3 | CSCO | Cisco Systems | 2,684 | 18.4% | 1.79 | 0.99× | 0.94× |
| 4 | NVDA | Nvidia | 3,265 | 14.0% | 1.24 | 0.31× | 0.85× |
| 5 | AMD | Advanced Micro Devices | 3,267 | 14.0% | 0.78 | 0.80× | 0.85× |
| 6 | NFLX | Netflix | 3,330 | 13.5% | 1.09 | 0.50× | 0.84× |
| 7 | QCOM | Qualcomm | 3,437 | 12.7% | 1.03 | 0.93× | 0.83× |
| 8 | META | Meta Platforms | 3,577 | 12.0% | 1.16 | 0.54× | 0.82× |
| 9 | AVGO | Broadcom | 3,883 | 10.2% | 0.80 | 0.25× | 0.78× |
| 10 | TSLA | Tesla | 4,039 | 9.3% | 0.61 | 0.58× | 0.77× |
| 11 | COST | Costco Wholesale | 4,109 | 8.8% | 0.98 | 0.69× | 0.76× |
| 12 | ADBE | Adobe | 4,500 | 6.6% | 0.52 | 1.53× | 0.72× |
| 13 | AMZN | Amazon.com | 5,120 | 3.2% | 0.38 | 0.56× | 0.67× |
| 14 | MSFT | Microsoft | 5,133 | 3.1% | 0.74 | 0.73× | 0.66× |
| 15 | PEP | PepsiCo | 5,381 | 1.4% | 0.18 | 1.26× | 0.64× |

### Key findings

- **The famous megacaps rank poorly.** The best of them (AAPL) only reaches the
  top ~41% of the universe; MSFT, AMZN, and PEP sit near the very bottom
  (rank 5,100+). All 15 fall below the median champion ARR except AAPL, GOOGL,
  and CSCO.
- **Only AAPL (1.04×) and GOOGL (1.01×) beat SPY.** The other 13 underperformed
  the index even with their optimal strategy, and most have a "vs B&H" below
  1.0× — i.e., the strategy did worse than simply holding the stock.
- **Edge concentrates in volatile small-caps.** The workbook's `final rank`
  top performers are all obscure microcaps (LBGJ, VOR, LPCN, …), where the
  strategies find exploitable inefficiency that doesn't exist in large,
  efficient names. This is the textbook outcome for technical timing strategies.

### Data extracted by `extract_financials.py`

| Ticker | Company |
|--------|---------|
| AMZN | Amazon.com, Inc. |
| MSFT | Microsoft Corporation |
| PEP | PepsiCo, Inc. |
| NVDA | NVIDIA Corporation |
| SPY *(recommended)* | SPDR S&P 500 ETF Trust — market benchmark |

---

## Notes & caveats

- **Prices from yfinance are reliable; fundamentals are patchy.** Yahoo's
  statement data can be partial or stale, and `.info` is occasionally
  rate-limited. For audited fundamentals, use **SEC EDGAR** (`companyfacts` API,
  free) or a keyed provider (Financial Modeling Prep, Alpha Vantage).
- **Hit-rate convention.** This toolkit defines hit-rate as the *round-trip
  trade* win rate. If your pipeline uses the fraction of *bars* with positive
  return instead, swap `hit_rate(trade_rets)` for `(strat_ret > 0).mean()` in
  `backtest()`.
- **ARR convention.** Computed as CAGR. If `projj_filled.xlsx` annualizes
  differently, adjust `annualized_return()` accordingly.
- **Transaction costs** are a simple `cost_bps` charge on changes in exposure;
  slippage, borrow costs, and market impact are not modeled.
```
