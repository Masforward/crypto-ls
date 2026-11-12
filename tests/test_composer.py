"""因子合成模块测试：随机因子能跑、完美因子权重最大、权重无未来函数。"""
import numpy as np
import pandas as pd

from src.cls.compose import EqualWeight, ICIRWeighted, ICWeighted


def _make_scores(n_days=100, n_symbols=10, n_factors=3, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n_days, freq="D", tz="UTC")
    cols = [f"S{i}" for i in range(n_symbols)]
    return {
        f"f{i}": pd.DataFrame(rng.standard_normal((n_days, n_symbols)), index=idx, columns=cols)
        for i in range(n_factors)
    }, idx, cols


def test_equal_weight_runs_on_random_factors():
    """全是随机因子时等权合成能正常运行。"""
    scores, idx, cols = _make_scores()
    comp, weights = EqualWeight().compose(scores)
    assert comp.shape == (len(idx), len(cols))
    assert weights.shape == (len(idx), 3)
    assert np.allclose(weights.iloc[0], 1 / 3)


def test_ic_weighted_prefers_perfect_factor():
    """加入完美因子（RankIC=1）后，IC/ICIR 加权给它的权重应明显最大。"""
    scores, idx, cols = _make_scores()
    ic_history = {
        "f0": pd.Series(1.0, index=idx),   # 完美因子
        "f1": pd.Series(0.0, index=idx),   # 随机
        "f2": pd.Series(0.0, index=idx),   # 随机
    }
    for cls in (ICWeighted, ICIRWeighted):
        _, weights = cls(lookback=60).compose(scores, ic_history)
        last = weights.iloc[-1]
        assert last["f0"] > 0.9, f"{cls.name} 应给完美因子最大权重"


def test_weights_no_future_function():
    """未来函数测试：改动 t 之后的 IC，t 时刻及以前的权重不变。"""
    scores, idx, cols = _make_scores(seed=1)
    rng = np.random.default_rng(2)
    ic_history = {f"f{i}": pd.Series(rng.standard_normal(100), index=idx) for i in range(3)}

    _, w1 = ICWeighted(lookback=20).compose(scores, ic_history)

    # 污染 index 后半段（>= 第 50 个时刻）的 IC
    polluted = {k: v.copy() for k, v in ic_history.items()}
    for v in polluted.values():
        v.iloc[50:] = 999.0

    _, w2 = ICWeighted(lookback=20).compose(scores, polluted)

    # holdback=2，所以 t 时刻只用 < t-2 的 IC；改动第 50 个及以后的 IC，
    # 第 50 个时刻（用 < 48 的 IC）及以前的权重应完全不变
    pd.testing.assert_frame_equal(w1.iloc[:50], w2.iloc[:50])
