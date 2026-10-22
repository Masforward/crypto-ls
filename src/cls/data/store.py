"""本地存储与增量更新：Parquet 按数据类型/周期/币种存放，update 幂等。"""
import os

import pandas as pd

from .funding import get_funding_rates
from .klines import get_klines


def klines_path(data_dir, interval, symbol):
    """K 线存储路径：data_dir/klines/{interval}/{symbol}.parquet"""
    return os.path.join(data_dir, "klines", interval, f"{symbol}.parquet")


def funding_path(data_dir, symbol):
    """资金费率存储路径：data_dir/funding/{symbol}.parquet"""
    return os.path.join(data_dir, "funding", f"{symbol}.parquet")


def _merge(existing, new, key):
    """纯函数：纵向合并 + 按 key 去重 + 排序（幂等的核心，可离线测试）。"""
    combined = pd.concat([existing, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=[key])
    return combined.sort_values(key).reset_index(drop=True)


def update_klines(symbols, interval, start, data_dir="data"):
    """增量更新 K 线：只补本地缺失部分，重复执行结果不变（幂等）。

    start : 首次拉取的起点（本地无数据时才用到）。
    """
    if isinstance(symbols, str):
        symbols = [symbols]
    step = pd.Timedelta(interval)
    now = pd.Timestamp.now(tz="UTC")

    for symbol in symbols:
        path = klines_path(data_dir, interval, symbol)
        if os.path.exists(path):
            existing = pd.read_parquet(path)
            fetch_start = existing["open_time"].max() + step  # 从下一根开始
        else:
            existing = None
            fetch_start = pd.Timestamp(start)

        new = get_klines(symbol, interval, fetch_start, now)

        if existing is not None:
            out = _merge(existing, new, "open_time") if not new.empty else existing
        else:
            out = new

        if not out.empty:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            out.to_parquet(path, index=False)


def update_funding(symbols, start, data_dir="data"):
    """增量更新资金费率，逻辑同 update_klines。"""
    if isinstance(symbols, str):
        symbols = [symbols]
    now = pd.Timestamp.now(tz="UTC")

    for symbol in symbols:
        path = funding_path(data_dir, symbol)
        if os.path.exists(path):
            existing = pd.read_parquet(path)
            fetch_start = existing["funding_time"].max() + pd.Timedelta("1ms")
        else:
            existing = None
            fetch_start = pd.Timestamp(start)

        new = get_funding_rates(symbol, fetch_start, now)

        if existing is not None:
            out = _merge(existing, new, "funding_time") if not new.empty else existing
        else:
            out = new

        if not out.empty:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            out.to_parquet(path, index=False)
