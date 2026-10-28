"""测试 store 的纯函数（不联网）。"""
import os

import pandas as pd

from src.cls.data.store import _merge, _normalize_klines, _um_klines_path


def test_merge_dedup_and_sort():
    existing = pd.DataFrame({
        "open_time": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00"], utc=True),
        "close": [100.0, 101.0],
    })
    new = pd.DataFrame({
        "open_time": pd.to_datetime(["2026-01-01 01:00", "2026-01-01 02:00"], utc=True),
        "close": [101.0, 102.0],
    })
    out = _merge(existing, new, "open_time")
    assert out["open_time"].duplicated().sum() == 0   # 去重成功
    assert len(out) == 3
    assert out["open_time"].iloc[-1] == pd.Timestamp("2026-01-01 02:00", tz="UTC")


def test_um_klines_path():
    # 第三周按月分文件路径（跨平台用 os.path.join），interval 可变
    assert _um_klines_path("data", "BTCUSDT", "5m", 2025, 1) == os.path.join(
        "data", "binance", "um", "klines", "5m", "BTCUSDT", "2025-01.parquet")
    assert _um_klines_path("data", "ETHUSDT", "1h", 2026, 12) == os.path.join(
        "data", "binance", "um", "klines", "1h", "ETHUSDT", "2026-12.parquet")


def test_normalize_klines():
    df = pd.DataFrame({
        "open_time": [1728000000000],
        "open": [60100.0], "high": [60500.0], "low": [59900.0],
        "close": [60250.0], "volume": [123.45],
        "close_time": [1728003599999], "quote_volume": [7400000.0],
        "count": [8901], "taker_buy_volume": [60.1],
        "taker_buy_quote_volume": [3600000.0], "ignore": [0],
    })
    out = _normalize_klines(df)
    assert out["open_time"].iloc[0].tzinfo is not None   # 带 UTC 时区
    assert out["open"].dtype == float
    assert out["count"].dtype == int
