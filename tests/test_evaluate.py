"""评价模块自检：完美因子 RankIC=1、反向因子 RankIC=-1、随机因子 RankIC≈0。"""
import numpy as np
import pandas as pd
import pytest

from src.cls.signal.evaluate import compute_forward_returns, rankic_series


def _make_close(n_days=60, n_symbols=20, seed=0):
    """构造随机日线收盘价面板（时间 × 币种），随机游走。"""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.02, size=(n_days, n_symbols))
    close = pd.DataFrame(
        np.exp(np.cumsum(returns, axis=0)) * 100,
        index=pd.date_range("2025-01-01", periods=n_days, freq="D", tz="UTC"),
        columns=[f"S{i}" for i in range(n_symbols)],
    )
    return close


def test_perfect_factor_rankic_is_one():
    """完美因子（因子值 = 下期收益）的 RankIC 应为 +1。"""
    close = _make_close()
    fwd = compute_forward_returns(close, 1)
    assert rankic_series(fwd, fwd).mean() == pytest.approx(1.0, abs=1e-9)


def test_reverse_factor_rankic_is_minus_one():
    """反向完美因子（因子值 = -下期收益）的 RankIC 应为 -1。"""
    close = _make_close()
    fwd = compute_forward_returns(close, 1)
    assert rankic_series(-fwd, fwd).mean() == pytest.approx(-1.0, abs=1e-9)


def test_random_factor_rankic_near_zero():
    """随机因子（与收益无关）的 RankIC 应接近 0。"""
    close = _make_close()
    fwd = compute_forward_returns(close, 1)
    rng = np.random.default_rng(1)
    rand = pd.DataFrame(rng.standard_normal(fwd.shape), index=fwd.index, columns=fwd.columns)
    assert abs(rankic_series(rand, fwd).mean()) < 0.2
