import pandas as pd

from .client import request

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]
LIMIT = 1500  # klines 单次最多返回根数


def _step_ms(interval):
    #把区间转换成毫秒单位。
    return int(pd.Timedelta(interval).total_seconds() * 1000)


def _rows_to_frame(rows, symbol):
    #输入合约名和列信息，转换成dataframe，并将数字的数据类型变为浮点，时间类型变为utc毫秒。
    df = pd.DataFrame(rows, columns=KLINE_COLUMNS)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df.insert(0, "symbol", symbol)
    return df


def _finalize(df, start, end, now, step):
    #输入dataframe，起始时间，结束时间，当前时间，步长。输出规避未来函数的处理过的原始数据。注意目前列数没有发生变化。
    df = df[(df["open_time"] >= start) & (df["open_time"] < end)]
    df = df[df["open_time"] + step <= now]  # open_time + 周期还没到 = 未收盘！！
    return df


def _fetch_one(symbol, interval, start_ms, end_ms):
    #输入一个合约名，步长区间，起始时间点和结束时间点，返回含有所有符合条件的K线字典的列表也就是request，
    #注意我只调整startTime，不调整endtime，因为到单次limit他自己会截断。“batch[-1][0]”是opentime。
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
    #输入多个合约名，步长区间，起始结束时间点，此时的end时间可以是任何数字，大于现在也可以，finalize会修正。
    #返回一个shape为(n*8)的长表，8列的名字是固定的。
    #i.e. get_klines("BTCUSDT", "1h", start="2026-09-01", end="2026-09-05")
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
