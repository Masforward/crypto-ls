"""测试写盘 + 读回（用 pytest 临时目录，不碰真实 data/）。"""
import os

import pandas as pd

from src.cls.data.reader import load_klines
from src.cls.data.store import write_monthly_klines


def _sample():
    """构造一个月的 2 根 5 分钟 K 线样本。"""
    return pd.DataFrame({
        "open_time": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:05"], utc=True),
        "open": [100.0, 100.5],
        "high": [101.0, 101.5],
        "low": [99.0, 99.5],
        "close": [100.8, 101.2],
        "volume": [10.0, 11.0],
        "close_time": pd.to_datetime(
            ["2026-01-01 00:04:59.999", "2026-01-01 00:09:59.999"], utc=True),
        "quote_volume": [1000.0, 1100.0],
        "count": [100, 110],
        "taker_buy_volume": [5.0, 5.5],
        "taker_buy_quote_volume": [500.0, 550.0],
        "ignore": [0, 0],
    })


def test_write_and_load_roundtrip(tmp_path):
    """写盘到临时目录，再读回，数据一致。"""
    write_monthly_klines(_sample(), "TESTUSDT", "5m", 2026, 1, data_dir=str(tmp_path))
    loaded = load_klines("TESTUSDT", "2026-01-01", "2026-01-02", data_dir=str(tmp_path))
    assert len(loaded) == 2
    assert loaded["close"].tolist() == [100.8, 101.2]
    assert loaded["symbol"].tolist() == ["TESTUSDT", "TESTUSDT"]


def test_write_twice_idempotent(tmp_path):
    """重复写同一批数据，去重后不产生重复行（幂等）。"""
    write_monthly_klines(_sample(), "TESTUSDT", "5m", 2026, 1, data_dir=str(tmp_path))
    write_monthly_klines(_sample(), "TESTUSDT", "5m", 2026, 1, data_dir=str(tmp_path))
    loaded = load_klines("TESTUSDT", "2026-01-01", "2026-01-02", data_dir=str(tmp_path))
    assert len(loaded) == 2   # 第二次写盘去重，仍是 2 行
    assert loaded["open_time"].duplicated().sum() == 0
