"""风险函数：每个币的近 30 天波动率、对 BTC 的 beta、日均成交额。

独立于组合模块——组合模块只接收这里算好的结果，不自己计算。
只用决策时刻之前的数据（滚动窗口）。
"""
import numpy as np
import pandas as pd

from ..data import load_klines
from .pipeline import _resample


def compute_risk(symbols, start, end, interval="5m", data_dir=None, window=30,
                 btc_symbol="BTCUSDT"):
    """算风险输入面板（时间 × 币种）。

    返回 dict：
      volatility : 日收益滚动 window 天标准差
      beta       : 日收益对 BTC 日收益的滚动回归斜率
      volume     : 日成交额（quote_volume）滚动 window 天均值
    """
    all_symbols = list(symbols)
    if btc_symbol not in all_symbols:
        all_symbols = all_symbols + [btc_symbol]

    # 往前多读 window 天，保证滚动窗口在 start 处就有值（否则前 window-1 天是 NaN）
    load_start = pd.Timestamp(start) - pd.Timedelta(days=window + 5)
    df = load_klines(all_symbols, load_start, end, interval, data_dir=data_dir)
    daily = _resample(df, "1d")

    close = daily.pivot(index="open_time", columns="symbol", values="close")
    qvol = daily.pivot(index="open_time", columns="symbol", values="quote_volume")

    ret = close.pct_change()

    # 波动率：日收益滚动标准差
    volatility = ret.rolling(window).std()

    # beta：该币日收益对 BTC 日收益的滚动回归斜率 = cov(币, btc)/var(btc)
    beta = pd.DataFrame(np.nan, index=ret.index, columns=ret.columns)
    btc_ret = ret[btc_symbol]
    for col in ret.columns:
        if col == btc_symbol:
            beta[col] = 1.0
            continue
        cov = ret[col].rolling(window).cov(btc_ret)
        var = btc_ret.rolling(window).var()
        beta[col] = cov / var

    # 成交额：滚动日均
    volume = qvol.rolling(window).mean()

    # 只保留 start 之后的行
    start_ts = pd.Timestamp(start)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize("UTC")
    volatility = volatility[volatility.index >= start_ts]
    beta = beta[beta.index >= start_ts]
    volume = volume[volume.index >= start_ts]

    drop = [btc_symbol]
    return {
        "volatility": volatility.drop(columns=drop, errors="ignore"),
        "beta": beta.drop(columns=drop, errors="ignore"),
        "volume": volume.drop(columns=drop, errors="ignore"),
    }
