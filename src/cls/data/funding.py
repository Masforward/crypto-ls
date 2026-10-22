
import pandas as pd

from .client import request

LIMIT = 1000  # fundingRate 单次最多返回条数


def _rows_to_frame(rows):
    df = pd.DataFrame(rows)  # 每条含 symbol, fundingTime, fundingRate
    df["funding_rate"] = df["fundingRate"].astype(float)
    df["funding_time"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    return df[["symbol", "funding_time", "funding_rate"]]


def _fetch_one(symbol, start_ms, end_ms):
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        resp = request("/fapi/v1/fundingRate", params={
            "symbol": symbol,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": LIMIT,
        })
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1]["fundingTime"] + 1  # 从下一条开始，避免重复
        if len(batch) < LIMIT:
            break
    return rows


def get_funding_rates(symbols, start, end):

    if isinstance(symbols, str):
        symbols = [symbols]

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    frames = []
    for symbol in symbols:
        rows = _fetch_one(symbol, start_ms, end_ms)
        frames.append(_rows_to_frame(rows))

    out = pd.concat(frames, ignore_index=True)
    # 左闭右开 [start, end)
    out = out[(out["funding_time"] >= start) & (out["funding_time"] < end)]
    return out.reset_index(drop=True)
