"""测试 meta 的纯函数（不联网）。"""
import pandas as pd

from src.cls.data.meta import _detect_gaps, _expected_count, _validate_klines


def test_expected_count_full_month():
    onboard = pd.Timestamp("2019-09-08", tz="UTC")
    assert _expected_count(onboard, 2026, 5) == 8928   # 31 天 × 288
    assert _expected_count(onboard, 2026, 6) == 8640   # 30 天 × 288


def test_expected_count_mid_month_listing():
    onboard = pd.Timestamp("2026-07-15", tz="UTC")
    assert _expected_count(onboard, 2026, 7) == 4896   # 17 天 × 288（月中上市）


def test_validate_klines():
    df = pd.DataFrame({
        "open_time": pd.to_datetime(["2026-10-01 00:00", "2026-10-01 00:05"], utc=True),
        "open": [100.0, 100.0],
        "high": [105.0, 99.0],       # 第 2 行 high < open，非法
        "low": [95.0, 95.0],
        "close": [102.0, 102.0],
        "volume": [10.0, 10.0],
        "close_time": pd.to_datetime(
            ["2026-10-01 00:04:59.999", "2026-10-01 00:09:59.999"], utc=True),
        "quote_volume": [1000.0, 1000.0],
        "count": [100, 100],
        "taker_buy_volume": [5.0, 5.0],
        "taker_buy_quote_volume": [500.0, 500.0],
        "ignore": [0, 0],
    })
    assert _validate_klines(df).tolist() == [False, True]


def test_detect_gaps():
    df = pd.DataFrame({
        "open_time": pd.to_datetime(
            ["2026-10-01 00:00", "2026-10-01 00:05",
             "2026-10-01 00:20", "2026-10-01 00:25"], utc=True),
    })
    onboard = pd.Timestamp("2019-09-08", tz="UTC")
    gaps = _detect_gaps(df, onboard, 2026, 10, end=pd.Timestamp("2026-10-01 00:25", tz="UTC"))
    # 缺 00:10、00:15 → 一段缺口 [00:10, 00:20, 2 根]
    assert len(gaps) == 1
    assert gaps[0][0] == pd.Timestamp("2026-10-01 00:10", tz="UTC")
    assert gaps[0][2] == 2
