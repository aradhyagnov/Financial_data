# Stock Data & Strategy Metrics Toolkit

A small two-script toolkit for a quantitative backtesting workflow:

1. **`extract_financials.py`** — pulls raw price + fundamental data for a list of
   tickers from Yahoo Finance and saves it as CSV.
2. **`strategy_metrics.py`** — backtests a trading strategy on that price data and
   computes the performance metrics (hit-rate, ARR, max drawdown, Sharpe,
   capital vs. benchmarks)

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

