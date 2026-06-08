# Financial_data

A small dataset + tooling repo for a quantitative backtesting workflow. It contains:

- **Raw financial-data CSVs** for five well-known stocks (`AAPL/`, `AMZN/`,
  `MSFT/`, `NVDA/`, `PEP/`), one folder per ticker.
- **`strategy_metrics.py`** — a backtesting engine that runs a trading strategy
  on the price data and computes the performance metrics (hit-rate, ARR, max
  drawdown, Sharpe, capital vs. benchmarks) using the **same definitions as the
  columns in the source spreadsheet `projj_filled.xlsx`**.

---

## Repository structure

```
Financial_data/
├── AAPL/
│   ├── prices.csv              # daily OHLCV (+ Dividends / Stock Splits cols)
│   ├── info.csv                # market cap, P/E, sector, margins, debt, …
│   ├── income_annual.csv       # income statement (annual)
│   ├── income_quarterly.csv    # income statement (quarterly)
│   ├── balance_annual.csv      # balance sheet (annual)
│   ├── balance_quarterly.csv   # balance sheet (quarterly)
│   ├── cashflow_annual.csv     # cash flow (annual)
│   ├── cashflow_quarterly.csv  # cash flow (quarterly)
│   ├── dividends.csv           # dividend history
│   └── splits.csv              # split history
├── AMZN/   (same 10 files)
├── MSFT/   (same 10 files)
├── NVDA/   (same 10 files)
├── PEP/    (same 10 files)
├── strategy_metrics.py
└── README.md
```

The ticker folders sit at the **repository root** — there is no `financial_data/`
wrapper directory.

### Tickers included

| Folder | Company |
|--------|---------|
| `AAPL` | Apple, Inc. |
| `AMZN` | Amazon.com, Inc. |
| `MSFT` | Microsoft Corporation |
| `NVDA` | NVIDIA Corporation |
| `PEP`  | PepsiCo, Inc. |

The CSVs were pulled from Yahoo Finance via the `yfinance` library. (The
extraction script is not part of this repo.) There is no `SPY/` folder, so the
"vs SPY" benchmark is downloaded on the fly when you run the backtester — see
below.

---

## Requirements

```bash
pip install pandas numpy yfinance
```

`yfinance` is only needed if you let the backtester download the SPY benchmark
(or any ticker without a local folder).

---

## `strategy_metrics.py` — backtest & metrics

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

Run from the repository root so the relative `TICKER/prices.csv` paths resolve:

```python
from strategy_metrics import (
    backtest, evaluate_strategies, load_prices,
    sma_crossover, rsi_reversion,
)

# load price data from this repo's folders (falls back to yfinance if missing)
price = load_prices("AAPL", csv_path="AAPL/prices.csv")
spy   = load_prices("SPY",  csv_path="SPY/prices.csv")["Close"]   # downloads SPY

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

It loops over all five tickers (`AAPL, AMZN, MSFT, NVDA, PEP`), runs both example
strategies on each, and prints a metrics table per ticker. If SPY can't be
downloaded (e.g. offline), it prints a note and leaves `cap_vs_spy` as `NaN`.

---

## Metric reference

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

