"""读取接口：从本地 Parquet 数据库读取 K 线（不联网）。"""
from .config import data_dir as _data_dir
import os

import pandas as pd

from .backfill import _month_range
from .klines import KLINE_COLUMNS
from .store import _um_klines_path


def load_klines(symbols, start, end, interval="5m", fields=None, data_dir=None):
    """读取指定币种、指定时间段 [start, end) 的 K 线，返回长表。

    只读与时间段重叠的月份文件；按 (open_time, symbol) 排序；fields 可只取部分列。
    本地没有的币种、或非法时间段（start >= end）会抛异常（不静默返回空表）。
    """
    if data_dir is None:
        data_dir = _data_dir()
    if isinstance(symbols, str):
        symbols = [symbols]
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    if start >= end:
        raise ValueError(f"非法时间段：start={start} 必须 < end={end}")

    klines_root = os.path.join(data_dir, "binance", "um", "klines", interval)
    for symbol in symbols:
        if not os.path.isdir(os.path.join(klines_root, symbol)):
            raise ValueError(f"本地没有币种 {symbol} 的数据")

    # 与 [start, end) 重叠的月份
    months = _month_range(start, end - pd.Timedelta("1ms"))

    frames = []
    for symbol in symbols:
        for year, month in months:
            path = _um_klines_path(data_dir, symbol, interval, year, month)
            if os.path.exists(path):
                df = pd.read_parquet(path)
                df.insert(0, "symbol", symbol)   # 文件内无 symbol 列，从币种循环补上
                frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["symbol"] + KLINE_COLUMNS)

    out = pd.concat(frames, ignore_index=True)
    out = out[(out["open_time"] >= start) & (out["open_time"] < end)]
    out = out.sort_values(["open_time", "symbol"]).reset_index(drop=True)

    if fields is not None:
        out = out[fields]
    return out


def load_panel(field, symbols, start, end, interval="5m", data_dir=None):
    """返回某个字段的宽表（行为时间、列为币种），行是完整网格，缺失为 NaN。"""
    if data_dir is None:
        data_dir = _data_dir()
    long = load_klines(symbols, start, end, interval,
                       fields=["open_time", "symbol", field], data_dir=data_dir)
    panel = long.pivot(index="open_time", columns="symbol", values=field)
    step = pd.Timedelta(interval)
    full = pd.date_range(start, end, freq=step, inclusive="left", tz="UTC")
    return panel.reindex(full)


def list_symbols(interval="5m", data_dir=None):
    """返回本地已有数据的币种及其起止时间。"""
    if data_dir is None:
        data_dir = _data_dir()
    klines_root = os.path.join(data_dir, "binance", "um", "klines", interval)
    rows = []
    if os.path.isdir(klines_root):
        for symbol in sorted(os.listdir(klines_root)):
            sym_dir = os.path.join(klines_root, symbol)
            if not os.path.isdir(sym_dir):
                continue
            files = sorted(f for f in os.listdir(sym_dir) if f.endswith(".parquet"))
            if not files:
                continue
            first = pd.read_parquet(os.path.join(sym_dir, files[0]))
            last = pd.read_parquet(os.path.join(sym_dir, files[-1]))
            rows.append({
                "symbol": symbol,
                "start": first["open_time"].min(),
                "end": last["open_time"].max(),
                "months": len(files),
            })
    return pd.DataFrame(rows)


def quality_report(symbols=None, interval="5m", data_dir=None):
    """返回每个币的应有根数、实有根数、缺口数、非法行数。"""
    if data_dir is None:
        data_dir = _data_dir()
    from .meta import _meta_path, _validate_klines

    # 读已有的 coverage 报告（backfill/update_klines 每币回填完就更新它，所以是最新的）
    cov_path = _meta_path(data_dir, "coverage_5m")
    if os.path.exists(cov_path):
        coverage = pd.read_parquet(cov_path)
    else:
        coverage = pd.DataFrame(columns=["symbol", "month", "expected", "actual", "gaps"])
    report = coverage.groupby("symbol").agg(
        expected=("expected", "sum"),
        actual=("actual", "sum"),
        gaps=("gaps", "sum"),
    ).reset_index()

    klines_root = os.path.join(data_dir, "binance", "um", "klines", interval)
    invalid_counts = []
    for _, r in report.iterrows():
        sym_dir = os.path.join(klines_root, r["symbol"])
        bad = 0
        for fname in os.listdir(sym_dir):
            if fname.endswith(".parquet"):
                df = pd.read_parquet(os.path.join(sym_dir, fname))
                bad += int(_validate_klines(df, interval).sum())
        invalid_counts.append(bad)
    report["invalid"] = invalid_counts

    if symbols is not None:
        if isinstance(symbols, str):
            symbols = [symbols]
        report = report[report["symbol"].isin(symbols)]
    return report
