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
    #输入老dataframe和新的部分，合成之后按照key的值判断并去除重复，再以key(时间)排序并重设编号。
    combined = pd.concat([existing, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=[key])
    return combined.sort_values(key).reset_index(drop=True)


def update_klines(symbols, interval, start, data_dir="data"):
    #输入合约名，区间，起始点，数据文件夹名，调用merge去重之后建文件夹(目前还没有实现时间分页功能)
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
    #输入合约名，起始点，数据文件夹名，调用merge去重之后建文件夹(目前还没有实现时间分页功能)
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
