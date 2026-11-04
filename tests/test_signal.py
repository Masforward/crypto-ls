"""信号模块测试：未来函数测试（构造数据，不联网）。"""
import numpy as np
import pandas as pd

from src.cls.signal.factor import Momentum7d
from src.cls.signal.pipeline import _compute_one_factor


def _make_daily(n=30):
    """构造单币 n 天日线。"""
    dates = pd.date_range("2026-09-01", periods=n, freq="1D", tz="UTC")
    return pd.DataFrame({
        "symbol": "TESTUSDT",
        "open_time": dates,
        "open": np.arange(100, 100 + n, dtype=float),
        "high": np.arange(101, 101 + n, dtype=float),
        "low": np.arange(99, 99 + n, dtype=float),
        "close": np.arange(100, 100 + n, dtype=float),
        "volume": np.ones(n),
        "quote_volume": np.ones(n),
        "taker_buy_volume": np.ones(n),
        "taker_buy_quote_volume": np.ones(n),
        "count": np.ones(n),
    })


def test_no_future_function():
    """未来函数测试：污染 t 之后的数据，t 及以前的因子值必须不变。"""
    factor = Momentum7d()
    df = _make_daily(30)
    orig = _compute_one_factor(factor, df)

    # 污染 open_time >= 2026-09-20 的数据（未来）
    t = pd.Timestamp("2026-09-20", tz="UTC")
    rng = np.random.default_rng(42)
    polluted = df.copy()
    mask = polluted["open_time"] >= t
    cols = ["open", "high", "low", "close", "volume", "quote_volume"]
    polluted.loc[mask, cols] = rng.random((mask.sum(), len(cols))) * 1000

    new = _compute_one_factor(factor, polluted)

    # 验证 t 及以前的因子值不变
    before = orig.index[orig.index <= t]
    assert len(before) > 0, "测试区间内没有可验证的决策时刻"
    pd.testing.assert_frame_equal(orig.loc[before], new.loc[before])

    # 反过来：t 之后应该有变化（证明污染确实生效了）
    after = orig.index[orig.index > t]
    if len(after) > 0:
        changed = not orig.loc[after].equals(new.loc[after])
        assert changed, "污染未来后，t 之后的因子值应该变化（否则污染没生效）"
