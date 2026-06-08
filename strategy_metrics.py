"""
strategy_metrics.py
-------------------
Backtest a trading strategy on a price series and extract the performance
metrics used in the project spreadsheet:

    hit_rate          -> "Hit-rate"
    arr               -> "ARR" (annualized return rate / CAGR)
    max_drawdown      -> "Maximum Drawdown"
    sharpe            -> "Sharpe Ratio"
    cap_vs_buyhold    -> "Current Capital / Buy & Hold"
    cap_vs_spy        -> "Current Capital / SPY"
    (+ n_trades, total_return, final_capital)

A "strategy" is just a function   signal(price_df, **kwargs) -> pd.Series
that returns the DESIRED position at each bar's close (e.g. 1 = long,
0 = flat, -1 = short; fractional exposures are allowed too). The engine
lags that position by one bar before applying returns, so there is no
look-ahead bias as long as your signal only uses past/current data.

Setup:
    pip install pandas numpy yfinance     # yfinance only needed for the demo
Run the demo:
    python strategy_metrics.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 252  # trading days; use 52 for weekly, 12 for monthly bars


# ----------------------------- metric primitives -----------------------------
def annualized_return(equity: pd.Series, ppy: int = PERIODS_PER_YEAR) -> float:
    """CAGR of an equity curve (starts at 1.0)."""
    if len(equity) < 2:
        return np.nan
    total = equity.iloc[-1] / equity.iloc[0]
    years = len(equity) / ppy
    if years <= 0 or total <= 0:
        return np.nan
    return total ** (1.0 / years) - 1.0


def sharpe_ratio(returns: pd.Series, rf: float = 0.0,
                 ppy: int = PERIODS_PER_YEAR) -> float:
    """Annualized Sharpe on per-bar strategy returns. rf is an ANNUAL rate."""
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    if sd == 0:
        return 0.0
    excess = r - rf / ppy
    return float(np.sqrt(ppy) * excess.mean() / sd)


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough decline of the equity curve (<= 0)."""
    if len(equity) == 0:
        return np.nan
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())


def extract_trade_returns(active_sign: pd.Series,
                          strat_ret: pd.Series) -> np.ndarray:
    """Round-trip trade returns. A trade is a run of constant nonzero sign in
    the (already-lagged) position series; its return is the compounded
    per-bar strategy return over that holding period."""
    sign = active_sign.to_numpy()
    sr = strat_ret.fillna(0.0).to_numpy()
    trades, i, n = [], 0, len(sign)
    while i < n:
        if sign[i] != 0:
            s, cum = sign[i], 1.0
            while i < n and sign[i] == s:
                cum *= (1.0 + sr[i])
                i += 1
            trades.append(cum - 1.0)
        else:
            i += 1
    return np.asarray(trades)


def hit_rate(trade_returns: np.ndarray) -> float:
    if len(trade_returns) == 0:
        return np.nan
    return float((trade_returns > 0).sum()) / len(trade_returns)


# -------------------------------- backtest core --------------------------------
def backtest(price: pd.DataFrame, signal_func, spy_close: pd.Series = None,
             cost_bps: float = 0.0, rf: float = 0.0,
             ppy: int = PERIODS_PER_YEAR, **strat_kwargs):
    """
    price      : DataFrame with a 'Close' column, datetime index.
    signal_func: callable(price, **strat_kwargs) -> desired position Series.
    spy_close  : optional SPY close series for the "vs SPY" ratio.
    cost_bps   : round-trip-agnostic cost charged on |change in exposure|,
                 in basis points (5 = 0.05%).
    Returns (metrics: dict, curves: DataFrame).
    """
    close = price["Close"].astype(float)
    asset_ret = close.pct_change().fillna(0.0)

    # desired position decided at each bar's close, applied to the NEXT bar
    target = signal_func(price, **strat_kwargs).reindex(close.index).fillna(0.0)
    active = target.shift(1).fillna(0.0)               # <- prevents look-ahead

    strat_ret = active * asset_ret
    if cost_bps:
        turnover = active.diff().abs().fillna(active.abs())
        strat_ret = strat_ret - turnover * (cost_bps / 1e4)

    equity_strat = (1.0 + strat_ret).cumprod()
    equity_bh = (1.0 + asset_ret).cumprod()
    trade_rets = extract_trade_returns(np.sign(active), strat_ret)

    metrics = {
        "arr":            annualized_return(equity_strat, ppy),
        "hit_rate":       hit_rate(trade_rets),
        "max_drawdown":   max_drawdown(equity_strat),
        "sharpe":         sharpe_ratio(strat_ret, rf, ppy),
        "cap_vs_buyhold": float(equity_strat.iloc[-1] / equity_bh.iloc[-1]),
        "cap_vs_spy":     np.nan,
        "n_trades":       int(len(trade_rets)),
        "total_return":   float(equity_strat.iloc[-1] - 1.0),
        "final_capital":  float(equity_strat.iloc[-1]),
    }

    if spy_close is not None:
        spy_ret = (spy_close.astype(float).pct_change()
                   .reindex(close.index).fillna(0.0))
        equity_spy = (1.0 + spy_ret).cumprod()
        metrics["cap_vs_spy"] = float(equity_strat.iloc[-1] / equity_spy.iloc[-1])

    curves = pd.DataFrame({
        "asset_ret": asset_ret, "position": active, "strat_ret": strat_ret,
        "equity_strat": equity_strat, "equity_buyhold": equity_bh,
    })
    return metrics, curves


def evaluate_strategies(price: pd.DataFrame, strategies: dict,
                        spy_close: pd.Series = None, **bt_kwargs) -> pd.DataFrame:
    """Run several strategies and return one row of metrics per strategy
    (mirrors the per-stock x strategy layout in the spreadsheet).

    strategies = {"name": (signal_func, {param: value}), ...}
    """
    rows = []
    for name, (func, kwargs) in strategies.items():
        m, _ = backtest(price, func, spy_close=spy_close, **bt_kwargs, **kwargs)
        rows.append({"strategy": name, **m})
    return pd.DataFrame(rows).set_index("strategy")


# ------------------------------- example strategies ----------------------------
def sma_crossover(price, fast=20, slow=150):
    """Long when fast SMA is above slow SMA, else flat."""
    c = price["Close"]
    return (c.rolling(fast).mean() > c.rolling(slow).mean()).astype(float)


def rsi_reversion(price, period=14, lower=30, upper=70):
    """Mean reversion: go long when RSI is oversold, exit when overbought."""
    c = price["Close"]
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    pos = pd.Series(np.nan, index=c.index)
    pos[rsi < lower] = 1.0
    pos[rsi > upper] = 0.0
    return pos.ffill().fillna(0.0)


# ----------------------------------- data loader -------------------------------
def load_prices(ticker: str, csv_path: str = None, period: str = "3y") -> pd.DataFrame:
    """Read a prices.csv produced by extract_financials.py if given,
    otherwise download from Yahoo via yfinance."""
    if csv_path and Path(csv_path).exists():
        return pd.read_csv(csv_path, index_col=0, parse_dates=True)
    import yfinance as yf
    return yf.Ticker(ticker).history(period=period, auto_adjust=True)


# --------------------------------------- demo ----------------------------------
if __name__ == "__main__":
    TICKER = "AMZN"
    price = load_prices(TICKER, csv_path=f"financial_data/{TICKER}/prices.csv")
    spy = load_prices("SPY", csv_path="financial_data/SPY/prices.csv")["Close"]

    strategies = {
        "sma_cross(20,150)": (sma_crossover, {"fast": 20, "slow": 150}),
        "rsi_reversion(14)": (rsi_reversion, {"period": 14, "lower": 30, "upper": 70}),
    }
    table = evaluate_strategies(price, strategies, spy_close=spy, cost_bps=5)

    pd.set_option("display.float_format", lambda v: f"{v:,.4f}")
    print(f"\n{TICKER} — strategy performance\n")
    print(table.to_string())
