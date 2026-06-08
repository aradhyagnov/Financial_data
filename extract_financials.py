"""
extract_financials.py
----------------------
Pull basic raw financial data (prices + fundamentals) for a set of tickers
from Yahoo Finance via yfinance, and save everything to CSV (one folder per
ticker).

Setup:
    pip install yfinance pandas

Run:
    python extract_financials.py

Output layout:
    financial_data/
        AMZN/
            prices.csv              # raw OHLCV (+ dividends/splits columns)
            info.csv                # key stats snapshot (mkt cap, P/E, sector, ...)
            income_annual.csv       # income statement (annual)
            income_quarterly.csv    # income statement (quarterly)
            balance_annual.csv      # balance sheet (annual)
            balance_quarterly.csv   # balance sheet (quarterly)
            cashflow_annual.csv     # cash flow (annual)
            cashflow_quarterly.csv  # cash flow (quarterly)
            dividends.csv           # dividend history
            splits.csv              # split history
        MSFT/ ...
        PEP/  ...
        NVDA/ ...
"""

import time
from pathlib import Path

import pandas as pd
import yfinance as yf

# ------------------------------- CONFIG -------------------------------
TICKERS = ["AMZN", "MSFT", "PEP", "NVDA"]   # Amazon, Microsoft, Pepsi, Nvidia

PRICE_PERIOD   = "5y"     # 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
PRICE_INTERVAL = "1d"     # 1d,1wk,1mo  (intraday like 1h requires period <= 730d)
AUTO_ADJUST    = False    # False -> keep raw OHLC + separate Dividends/Splits cols
                          # True  -> split/dividend-adjusted OHLC

OUTPUT_DIR = Path("financial_data")

GET_PRICES     = True
GET_INFO       = True
GET_STATEMENTS = True     # income statement / balance sheet / cash flow
GET_DIVIDENDS  = True     # dividend + split history

PAUSE_SECONDS  = 1.0      # polite delay between tickers to avoid rate limits
# ----------------------------------------------------------------------


def save_csv(df, path: Path, label: str) -> None:
    """Write a DataFrame to CSV if it has data; otherwise log a skip."""
    if df is None or len(df) == 0:
        print(f"   [skip] {label}: no data returned")
        return
    df.to_csv(path)
    print(f"   [ok]   {label}: {df.shape[0]} rows -> {path.name}")


def fetch_prices(tk: yf.Ticker, folder: Path) -> None:
    hist = tk.history(
        period=PRICE_PERIOD,
        interval=PRICE_INTERVAL,
        auto_adjust=AUTO_ADJUST,
    )
    save_csv(hist, folder / "prices.csv", "prices (OHLCV)")


def fetch_info(tk: yf.Ticker, folder: Path) -> None:
    """Key-stats snapshot. fast_info is reliable; .info is richer but
    occasionally rate-limited, so each source is wrapped separately."""
    rows = {}

    try:
        fi = tk.fast_info
        for k in ("last_price", "market_cap", "shares", "currency",
                  "year_high", "year_low",
                  "fifty_day_average", "two_hundred_day_average"):
            rows[k] = getattr(fi, k, None)
    except Exception as e:
        print(f"   [warn] fast_info failed: {e}")

    try:
        info = tk.info  # dict
        for k in ("longName", "sector", "industry", "marketCap",
                  "trailingPE", "forwardPE", "priceToBook",
                  "dividendYield", "beta", "profitMargins",
                  "grossMargins", "returnOnEquity", "totalRevenue",
                  "totalCash", "totalDebt", "freeCashflow"):
            rows[k] = info.get(k)
    except Exception as e:
        print(f"   [warn] .info failed: {e}")

    df = pd.DataFrame(list(rows.items()), columns=["field", "value"])
    save_csv(df, folder / "info.csv", "key stats / info")


def fetch_statements(tk: yf.Ticker, folder: Path) -> None:
    statements = {
        "income_annual":      lambda: tk.income_stmt,
        "income_quarterly":   lambda: tk.quarterly_income_stmt,
        "balance_annual":     lambda: tk.balance_sheet,
        "balance_quarterly":  lambda: tk.quarterly_balance_sheet,
        "cashflow_annual":    lambda: tk.cashflow,
        "cashflow_quarterly": lambda: tk.quarterly_cashflow,
    }
    for name, getter in statements.items():
        try:
            df = getter()
        except Exception as e:
            print(f"   [warn] {name} failed: {e}")
            continue
        save_csv(df, folder / f"{name}.csv", name)


def fetch_dividends(tk: yf.Ticker, folder: Path) -> None:
    try:
        div = tk.dividends
        save_csv(div.to_frame(name="Dividend"), folder / "dividends.csv", "dividends")
    except Exception as e:
        print(f"   [warn] dividends failed: {e}")
    try:
        spl = tk.splits
        save_csv(spl.to_frame(name="Split"), folder / "splits.csv", "splits")
    except Exception as e:
        print(f"   [warn] splits failed: {e}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving to: {OUTPUT_DIR.resolve()}\n")

    for ticker in TICKERS:
        print(f"=== {ticker} ===")
        folder = OUTPUT_DIR / ticker
        folder.mkdir(parents=True, exist_ok=True)
        tk = yf.Ticker(ticker)

        if GET_PRICES:
            fetch_prices(tk, folder)
        if GET_INFO:
            fetch_info(tk, folder)
        if GET_STATEMENTS:
            fetch_statements(tk, folder)
        if GET_DIVIDENDS:
            fetch_dividends(tk, folder)

        time.sleep(PAUSE_SECONDS)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
