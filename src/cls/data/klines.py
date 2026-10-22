import pandas as pd

from .client import request

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]
LIMIT = 1500  # klines 单次最多返回根数


def _step_ms(interval):

    return int(pd.Timedelta(interval).total_seconds() * 1000)


def _rows_to_frame(rows, symbol):
    df = pd.DataFrame(rows, columns=KLINE_COLUMNS)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df.insert(0, "symbol", symbol)
    return df


def _finalize(df, start, end, now, step):
    """纯函数：左闭右开 [start, end) 过滤 + 剔除未收盘 K 线。"""
    df = df[(df["open_time"] >= start) & (df["open_time"] < end)]
    df = df[df["open_time"] + step <= now]  # open_time + 周期还没到 = 未收盘
    return df


def _fetch_one(symbol, interval, start_ms, end_ms):
    """拉单个币的全部 K 线（内部自动分页），返回原始 list。"""
    step = _step_ms(interval)
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        resp = request("/fapi/v1/klines", params={
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": LIMIT,
        })
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + step  # 下一页从下一根开始，避免重复
        if len(batch) < LIMIT:
            break
    return rows


def get_klines(symbols, interval, start, end):
    """拉多个币的 K 线，自动分页、剔除未收盘，返回长表。

    symbols : str | list[str]
    interval : str，如 "1h"
    start, end : pd.Timestamp（UTC），区间左闭右开 [start, end)
    返回列：symbol, open_time, open, high, low, close, volume, quote_volume
    """
    if isinstance(symbols, str):
        symbols = [symbols]

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    now = pd.Timestamp.now(tz="UTC")
    step = pd.Timedelta(interval)

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    frames = []
    for symbol in symbols:
        rows = _fetch_one(symbol, interval, start_ms, end_ms)
        df = _rows_to_frame(rows, symbol)
        df = _finalize(df, start, end, now, step)
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    return out[["symbol", "open_time", "open", "high", "low", "close",
                "volume", "quote_volume"]]
