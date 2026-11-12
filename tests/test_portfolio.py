"""组合管理模块测试：随机分数约束满足、分数相同不报错、最少持仓不足空仓。"""
import numpy as np
import pandas as pd

from src.cls.portfolio import InverseVolWeighted, QuantileLongShort, ScoreWeighted


def _make_scores(n_days=5, n_symbols=30, seed=0, constant=None):
    idx = pd.date_range("2025-01-01", periods=n_days, freq="D", tz="UTC")
    cols = [f"S{i}" for i in range(n_symbols)]
    if constant is not None:
        data = np.full((n_days, n_symbols), constant)
    else:
        rng = np.random.default_rng(seed)
        data = rng.standard_normal((n_days, n_symbols))
    return pd.DataFrame(data, index=idx, columns=cols), idx, cols


def _risk(idx, cols, seed=1):
    rng = np.random.default_rng(seed)
    return {
        "volatility": pd.DataFrame(rng.uniform(0.01, 0.1, (len(idx), len(cols))), index=idx, columns=cols),
        "volume": pd.DataFrame(rng.uniform(1e6, 1e8, (len(idx), len(cols))), index=idx, columns=cols),
    }


def test_random_scores_constraints_satisfied():
    """输入随机分数，所有约束每期都满足。"""
    scores, idx, cols = _make_scores()
    risk = _risk(idx, cols)
    cfg = {"min_names": 3, "gross": 1.0, "max_weight": 0.05}
    for builder in (QuantileLongShort(), ScoreWeighted(), InverseVolWeighted()):
        weights, diag = builder.build(scores, risk=risk, config=cfg)
        for t in idx:
            w = weights.loc[t]
            assert abs(w.sum()) < 1e-6, f"{builder.name} 美元中性不满足 @{t}"
            assert w.abs().sum() <= 1.0 + 1e-6, f"{builder.name} 总杠杆超限 @{t}"
            assert w.abs().max() <= 0.05 + 1e-6, f"{builder.name} 单币超限 @{t}"


def test_identical_scores_no_error():
    """输入分数完全相同时，程序不报错。"""
    scores, idx, cols = _make_scores(constant=0.5)
    risk = _risk(idx, cols)
    weights, diag = QuantileLongShort().build(scores, risk=risk, config={"min_names": 3})
    assert weights.shape == scores.shape   # 不报错且输出形状正常


def test_min_names_empty_when_insufficient():
    """最少持仓数不足时，当期为空仓（权重全 0 或 NaN）。"""
    scores, idx, cols = _make_scores(n_symbols=20)
    risk = _risk(idx, cols)
    # 每边只有 20×0.2=4 个币，但 min_names=10 → 不足 → 空仓
    weights, diag = QuantileLongShort().build(scores, risk=risk, config={"min_names": 10})
    for t in idx:
        w = weights.loc[t]
        assert (w == 0).all() or w.isna().all(), f"最少持仓不足应空仓 @{t}"
