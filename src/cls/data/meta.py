from .config import data_dir as _data_dir
import os

import pandas as pd

from .universe import get_universe


def _meta_path(data_dir, name):
    # meta 文件路径：data_dir/binance/um/meta/{name}.parquet
    return os.path.join(data_dir, "binance", "um", "meta", f"{name}.parquet")


def save_symbols(data_dir=None, as_of=None):
    if data_dir is None:
        data_dir = _data_dir()
    #采集 as_of 当天可交易的 USDT 永续合约清单，保存到 symbols.parquet。
    #复用 get_universe（onboardDate ≤ as_of < deliveryDate 判断，消除幸存者偏差）。
    #字段：symbol, onboard_date（上市时间）, status, as_of, collected_at（采集时刻）。
    if as_of is None:
        as_of = pd.Timestamp.now(tz="UTC")
    else:
        as_of = pd.Timestamp(as_of)
        if as_of.tzinfo is None:
            as_of = as_of.tz_localize("UTC")

    df = get_universe(as_of=as_of)  # 返回 symbol, onboardDate, deliveryDate
    df = df.rename(columns={"onboardDate": "onboard_date"})
    df["status"] = "TRADING"
    df["as_of"] = as_of
    df["collected_at"] = pd.Timestamp.now(tz="UTC")
    df = df[["symbol", "onboard_date", "status", "as_of", "collected_at"]]

    path = _meta_path(data_dir, "symbols")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def _expected_count(onboard_date, year, month, interval="5m", end=None):
    # 输入上市日，年月区间，计算K线应有条数。
    month_start = pd.Timestamp(year, month, 1, tz="UTC")
    if month == 12:
        month_end = pd.Timestamp(year + 1, 1, 1, tz="UTC")
    else:
        month_end = pd.Timestamp(year, month + 1, 1, tz="UTC")
    if end is not None:
        month_end = min(month_end, end)

    start = max(month_start, onboard_date)
    if start >= month_end:
        return 0
    step = pd.Timedelta(interval)
    return int((month_end - start) / step)


def _effective_onboard(onboard, sym_dir):
    # 返回币的真实上市时间：min(onboardDate, 数据实际起点)。
    # 合约变更币的 onboardDate 是"合约变更时间"（晚于真实上市），
    # 用数据实际起点（最早月的 min open_time）修正，避免 expected 算少。
    files = sorted(f for f in os.listdir(sym_dir) if f.endswith(".parquet"))
    if not files:
        return onboard
    first = pd.read_parquet(os.path.join(sym_dir, files[0]))
    return min(onboard, first["open_time"].min())


def check_coverage(data_dir=None, interval="5m"):
    """对每个币每个月，计算应有根数 vs 实有根数，写 coverage_5m.parquet。

    返回 coverage DataFrame（symbol, month, expected, actual, gaps）。
    """
    if data_dir is None:
        data_dir = _data_dir()
    symbols = pd.read_parquet(_meta_path(data_dir, "symbols"))
    klines_root = os.path.join(data_dir, "binance", "um", "klines", interval)
    now = pd.Timestamp.now(tz="UTC")

    rows = []
    for _, r in symbols.iterrows():
        symbol = r["symbol"]
        sym_dir = os.path.join(klines_root, symbol)
        if not os.path.isdir(sym_dir):
            continue
        onboard = _effective_onboard(r["onboard_date"], sym_dir)
        for fname in sorted(os.listdir(sym_dir)):
            if not fname.endswith(".parquet"):
                continue
            ym = fname[:-len(".parquet")]          # "2026-05"
            year, month = int(ym[:4]), int(ym[5:7])
            # 当前月：应有根数算到 now，避免把"未来"误判成缺口
            end = now if (year, month) == (now.year, now.month) else None
            expected = _expected_count(onboard, year, month, interval, end)
            df = pd.read_parquet(os.path.join(sym_dir, fname))
            actual = len(df)
            rows.append({
                "symbol": symbol,
                "month": ym,
                "expected": expected,
                "actual": actual,
                "gaps": expected - actual,
            })

    coverage = pd.DataFrame(rows)
    path = _meta_path(data_dir, "coverage_5m")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    coverage.to_parquet(path, index=False)
    return coverage


def _update_coverage_symbol(symbol, onboard, interval="5m", data_dir=None):
    """回填完一个币后，增量更新该币在 coverage 报告里的行（崩溃安全）。

    只重算这一个币的 coverage 行，替换报告里该币的旧行。
    """
    now = pd.Timestamp.now(tz="UTC")
    sym_dir = os.path.join(data_dir, "binance", "um", "klines", interval, symbol)
    onboard = _effective_onboard(onboard, sym_dir)
    rows = []
    if os.path.isdir(sym_dir):
        for fname in sorted(os.listdir(sym_dir)):
            if not fname.endswith(".parquet"):
                continue
            ym = fname[:-len(".parquet")]
            year, month = int(ym[:4]), int(ym[5:7])
            end = now if (year, month) == (now.year, now.month) else None
            expected = _expected_count(onboard, year, month, interval, end)
            df = pd.read_parquet(os.path.join(sym_dir, fname))
            actual = len(df)
            rows.append({"symbol": symbol, "month": ym,
                         "expected": expected, "actual": actual, "gaps": expected - actual})

    cov_path = _meta_path(data_dir, "coverage_5m")
    if os.path.exists(cov_path):
        cov = pd.read_parquet(cov_path)
        cov = cov[cov["symbol"] != symbol]          # 删掉该币的旧行
    else:
        cov = pd.DataFrame(columns=["symbol", "month", "expected", "actual", "gaps"])
    if rows:
        cov = pd.concat([cov, pd.DataFrame(rows)], ignore_index=True)
    os.makedirs(os.path.dirname(cov_path), exist_ok=True)
    cov.to_parquet(cov_path, index=False)


def _detect_gaps(df, onboard, year, month, interval="5m", end=None):
    """检测某月数据中的缺口（缺失时间段），返回 [(gap_start, gap_end, missing_count)]。

    检测范围与 _expected_count 一致：max(月初, 上市时间) 到月底（或 end）。
    """
    step = pd.Timedelta(interval)
    month_start = pd.Timestamp(year, month, 1, tz="UTC")
    if month == 12:
        month_end = pd.Timestamp(year + 1, 1, 1, tz="UTC")
    else:
        month_end = pd.Timestamp(year, month + 1, 1, tz="UTC")
    if end is not None:
        month_end = min(month_end, end)

    start = max(month_start, onboard)
    if start >= month_end:
        return []

    full = pd.date_range(start, month_end, freq=step, inclusive="left")
    actual = set(df["open_time"])

    gaps = []
    gap_start = None
    for t in full:
        if t not in actual:
            if gap_start is None:
                gap_start = t              # 缺口起点
        else:
            if gap_start is not None:
                gaps.append((gap_start, t, int((t - gap_start) / step)))
                gap_start = None           # 缺口结束
    if gap_start is not None:              # 尾部缺口（一直缺到 month_end）
        gaps.append((gap_start, month_end, int((month_end - gap_start) / step)))
    return gaps


def check_gaps(data_dir=None, interval="5m"):
    """对每个币每个月，检测具体缺口（缺失时间段），写 gaps_5m.parquet。

    返回 gaps DataFrame（symbol, gap_start, gap_end, missing_count）。
    """
    if data_dir is None:
        data_dir = _data_dir()
    symbols = pd.read_parquet(_meta_path(data_dir, "symbols"))
    klines_root = os.path.join(data_dir, "binance", "um", "klines", interval)
    now = pd.Timestamp.now(tz="UTC")

    rows = []
    for _, r in symbols.iterrows():
        symbol = r["symbol"]
        sym_dir = os.path.join(klines_root, symbol)
        if not os.path.isdir(sym_dir):
            continue
        onboard = _effective_onboard(r["onboard_date"], sym_dir)
        for fname in sorted(os.listdir(sym_dir)):
            if not fname.endswith(".parquet"):
                continue
            ym = fname[:-len(".parquet")]
            year, month = int(ym[:4]), int(ym[5:7])
            end = now if (year, month) == (now.year, now.month) else None
            df = pd.read_parquet(os.path.join(sym_dir, fname))
            for gap_start, gap_end, cnt in _detect_gaps(df, onboard, year, month, interval, end):
                rows.append({
                    "symbol": symbol,
                    "gap_start": gap_start,
                    "gap_end": gap_end,
                    "missing_count": cnt,
                })

    gaps = pd.DataFrame(rows)
    path = _meta_path(data_dir, "gaps_5m")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gaps.to_parquet(path, index=False)
    return gaps


def _validate_klines(df, interval="5m"):
    """逐行校验 K 线合法性，返回非法行的布尔 mask（True = 非法）。

    校验：时间戳对齐（open_time 是 interval 整数倍、close_time = open + step - 1ms）、
    OHLC 关系（high ≥ open/close、low ≤ open/close）、价格 > 0、volume ≥ 0、
    主动买入量 ≤ 总成交量。
    """
    step = pd.Timedelta(interval)
    step_ms = int(step.total_seconds() * 1000)

    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    open_ms = (df["open_time"] - epoch) // pd.Timedelta("1ms")   # 与 epoch 相减，精度/时区无关
    close_ms = (df["close_time"] - epoch) // pd.Timedelta("1ms")

    align_ok = (open_ms % step_ms) == 0                       # open_time 是 interval 整数倍
    close_ok = close_ms == (open_ms + step_ms - 1)            # close = open + step - 1ms
    high_ok = (df["high"] >= df["open"]) & (df["high"] >= df["close"])
    low_ok = (df["low"] <= df["open"]) & (df["low"] <= df["close"])
    price_ok = (df[["open", "high", "low", "close"]] > 0).all(axis=1)
    volume_ok = df["volume"] >= 0
    taker_ok = df["taker_buy_volume"] <= df["volume"]

    return ~(align_ok & close_ok & high_ok & low_ok & price_ok & volume_ok & taker_ok)


def reconcile_sample(n=5, interval="5m", data_dir=None):
    """随机抽 n 个币、每币 1 天，对比 vision 与 REST 数据，返回对账结果。

    对比：行数、open_time 集合、close 最大差异。用于验证两种来源写入的是同一份数据。
    """
    if data_dir is None:
        data_dir = _data_dir()
    import random

    from .backfill import _rest_day
    from .reader import list_symbols
    from .vision import download_daily

    lst = list_symbols(interval, data_dir)
    if lst.empty:
        return pd.DataFrame()
    sample = lst.sample(n=min(n, len(lst)), random_state=42)

    results = []
    for _, r in sample.iterrows():
        symbol = r["symbol"]
        days = (r["end"] - r["start"]).days
        if days < 3:
            continue
        day = (r["start"] + pd.Timedelta(days=random.randint(0, days - 3))).floor("1D")

        v = download_daily(symbol, interval, day.year, day.month, day.day)
        rest = _rest_day(symbol, interval, day.year, day.month, day.day)

        common = sorted(set(v["open_time"]) & set(rest["open_time"]))
        v_close = v.set_index("open_time")["close"].astype(float)
        r_close = rest.set_index("open_time")["close"].astype(float)
        max_diff = float((v_close[common] - r_close[common]).abs().max()) if common else float("nan")

        results.append({
            "symbol": symbol,
            "date": day.date(),
            "vision_rows": len(v),
            "rest_rows": len(rest),
            "same_rows": len(v) == len(rest),
            "same_times": set(v["open_time"]) == set(rest["open_time"]),
            "max_close_diff": max_diff,
        })

    return pd.DataFrame(results)
