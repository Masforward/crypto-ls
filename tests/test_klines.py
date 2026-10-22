"""测试 klines 的纯函数（不联网）。"""
import pandas as pd

from src.cls.data.klines import _finalize, _rows_to_frame


def test_rows_to_frame_types():
    row = [1728000000000, "60100.0", "60500.0", "59900.0", "60250.0",
           "123.45", 1728003599999, "7400000.0", "8901", "60.1",
           "3600000.0", "0"]
    df = _rows_to_frame([row], "BTCUSDT")
    assert df["symbol"].iloc[0] == "BTCUSDT"
    assert df["open"].dtype == float
    assert df["close"].iloc[0] == 60250.0
    assert df["open_time"].iloc[0].tzinfo is not None  # 带 UTC 时区


def test_finalize_range_and_unclosed():
    df = pd.DataFrame({
        "open_time": pd.to_datetime([
            "2026-01-01 00:00", "2026-01-01 01:00",
            "2026-01-01 02:00", "2026-01-01 03:00",
        ], utc=True),
        "close": [100.0, 101.0, 102.0, 103.0],
    })
    start = pd.Timestamp("2026-01-01 00:00", tz="UTC")
    end = pd.Timestamp("2026-01-01 03:00", tz="UTC")   # 右开：不含 03:00
    now = pd.Timestamp("2026-01-01 02:30", tz="UTC")   # 02:00 那根收盘于 03:00 还没到
    step = pd.Timedelta("1h")

    out = _finalize(df, start, end, now, step)
    # 00:00、01:00 已收盘保留；02:00 未收盘剔除；03:00 右开过滤
    assert out["open_time"].tolist() == pd.to_datetime(
        ["2026-01-01 00:00", "2026-01-01 01:00"], utc=True).tolist()
