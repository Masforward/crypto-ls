"""本地存储：K 线 Parquet 按月分文件（data/binance/um/klines/5m/{SYMBOL}/{YYYY-MM}.parquet）。"""
import os

import pandas as pd


def _merge(existing, new, key):
    # 输入老dataframe和新的部分，合成之后按照key的值判断并去除重复，再以key(时间)排序并重设编号。
    combined = pd.concat([existing, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=[key])
    return combined.sort_values(key).reset_index(drop=True)


def _um_klines_path(data_dir, symbol, interval, year, month):
    # 新版 K 线路径：data_dir/binance/um/klines/{interval}/{SYMBOL}/{YYYY-MM}.parquet
    ym = f"{year}-{month:02d}"
    return os.path.join(data_dir, "binance", "um", "klines", interval, symbol, f"{ym}.parquet")


def _normalize_klines(df):
    # 类型转换：open_time/close_time → UTC 时间，价格/量 → float，count/ignore → int。
    df = df.copy()
    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_volume", "taker_buy_quote_volume"]:
        df[col] = df[col].astype(float)
    df["count"] = df["count"].astype(int)
    df["ignore"] = df["ignore"].astype(int)
    for col in ["open_time", "close_time"]:
        df[col] = pd.to_datetime(df[col], unit="ms", utc=True)
    return df


def write_monthly_klines(df, symbol, interval, year, month, data_dir="data"):
    #把某币某月的 K 线写盘（按月分文件）；文件已存在则合并去重。
    #返回 (path, 新增行数, 已有行数)。
    df = _normalize_klines(df)
    path = _um_klines_path(data_dir, symbol, interval, year, month)
    n_incoming = len(df)
    n_dup = 0
    if os.path.exists(path):
        existing = pd.read_parquet(path)
        n_before = len(existing)
        df = _merge(existing, df, "open_time")
        n_dup = n_before + n_incoming - len(df)   # 被去重掉的 = 已有数据
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    return path, n_incoming - n_dup, n_dup
