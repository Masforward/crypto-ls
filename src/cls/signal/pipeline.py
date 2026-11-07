"""信号模块：流水线。读数据层 → 聚合日线 → 批量算因子 → 分数表（时间 × 币种）。

只调用数据层的对外函数（load_klines 等），不碰数据层内部。
"""
import os

import numpy as np
import pandas as pd

from ..data import load_klines
from .factor import Factor

# 聚合日线时需要保留的列（因子可能用到的）
_DAILY_AGGS = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "quote_volume": "sum",
    "taker_buy_volume": "sum",
    "taker_buy_quote_volume": "sum",
    "count": "sum",
}


def _resample(df, rule):
    """把 K 线长表按 rule（"1D" 日线 / "1H" 小时线）聚合。"""
    out = []
    for symbol, g in df.groupby("symbol"):
        d = g.set_index("open_time").resample(rule).agg(_DAILY_AGGS)
        d["symbol"] = symbol
        out.append(d.reset_index())
    return pd.concat(out, ignore_index=True)


def _compute_one_factor(factor, daily):
    """对单个因子，算所有币、所有决策时刻的原始值，返回分数表（时间 × 币种）。"""
    rows = []
    for symbol, g in daily.groupby("symbol"):
        g = g.sort_values("open_time").reset_index(drop=True)
        for i in range(factor.history, len(g) + 1):
            t = g["open_time"].iloc[i - 1]              # 决策时刻 t
            if t.hour != 0:                             # 决策时刻统一为每天 00:00 UTC（作业时间规则）
                continue
            hist = g.iloc[max(0, i - 1 - factor.history): i - 1]  # t 之前已收盘的数据
            if len(hist) < factor.history:
                continue
            val = factor.compute(hist)
            rows.append({"open_time": t, "symbol": symbol, factor.name: val})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).pivot(index="open_time", columns="symbol", values=factor.name)


def compute_scores(factors, symbols, start, end, interval="5m", data_dir=None, cache=True):
    """批量计算因子分数表。

    factors : Factor 实例或列表 —— 要计算的因子
    symbols : str 或列表 —— 币种
    start/end : 起止时间（含端点）
    interval : K 线周期（默认 5m，会聚合成日线再算因子）
    cache : True 时，分数表存到 data/signal/{因子名}.parquet，下次直接读缓存
            （数据更新后缓存会过期，传 cache=False 强制重算）
    返回 {factor.name: 分数表 DataFrame(时间 × 币种)}。
    """
    if isinstance(factors, Factor):
        factors = [factors]
    if isinstance(symbols, str):
        symbols = [symbols]

    cache_dir = os.path.join(data_dir if data_dir else "data", "signal")

    result = {}
    for f in factors:
        cache_path = os.path.join(cache_dir, f"{f.name}.parquet")
        if cache and os.path.exists(cache_path):
            result[f.name] = pd.read_parquet(cache_path)   # 命中缓存
            continue

        # 读数据（数据层对外函数）
        df = load_klines(symbols, start, end, interval, data_dir=data_dir)
        if df.empty:
            result[f.name] = pd.DataFrame()
            continue

        # 按因子频率聚合（日线因子 1d，小时线因子 1h），再算分数表
        rule = "1h" if f.frequency == "1h" else "1d"
        agg = _resample(df, rule)
        score = _compute_one_factor(f, agg)

        if cache:
            os.makedirs(cache_dir, exist_ok=True)
            score.to_parquet(cache_path)                    # 写缓存
        result[f.name] = score

    return result


def compute_size(symbols, start, end, interval="5m", data_dir=None, window=30):
    """算规模表（时间 × 币种）：近 window 天日均成交额的对数（中性化的规模暴露）。

    规模 = log(近 30 天日均 quote_volume)，用于中性化剔除"大币/小币"影响。
    """
    df = load_klines(symbols, start, end, interval, data_dir=data_dir)
    daily = _resample(df, "1d")
    rows = []
    for symbol, g in daily.groupby("symbol"):
        g = g.sort_values("open_time").copy()
        # rolling(30) 后 shift(1)：用"之前 30 天"（不含当天）的日均成交额
        rolled = g["quote_volume"].rolling(window).mean().shift(1)
        g["size"] = np.log(rolled.where(rolled > 0))  # 0/负数 → NaN，避免 log(0)=-inf 导致回归报错
        rows.append(g[["open_time", "symbol", "size"]])
    long_df = pd.concat(rows, ignore_index=True)
    return long_df.pivot(index="open_time", columns="symbol", values="size")
