"""测试 store 的纯函数（不联网）。"""
import os

import pandas as pd

from src.cls.data.store import _merge, funding_path, klines_path


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


def test_paths():
    # 用 os.path.join 构造期望路径，跨平台（Windows 是 \，Linux 是 /）都能通过
    assert klines_path("data", "1h", "BTCUSDT") == os.path.join(
        "data", "klines", "1h", "BTCUSDT.parquet")
    assert funding_path("data", "BTCUSDT") == os.path.join(
        "data", "funding", "BTCUSDT.parquet")
