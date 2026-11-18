"""回测引擎 6 项正确性自检。"""
import numpy as np
import pandas as pd
import pytest

from src.cls.backtest.cost import FixedCost
from src.cls.backtest.engine import BacktestEngine


def _prices(n=10, symbols=("BTC",), start_price=100.0, ret=0.0, seed=0):
    """构造价格面板：close = 几何随机游走；open = 前一日 close。"""
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    rng = np.random.default_rng(seed)
    returns = rng.normal(ret, 0.01, size=(n, len(symbols)))
    close = pd.DataFrame(np.exp(np.cumsum(returns, axis=0)) * start_price,
                         index=idx, columns=list(symbols))
    open_ = close.shift(1)
    open_.iloc[0] = close.iloc[0]
    return close, open_, idx


def _weights(idx, mapping):
    """构造目标权重表：每个 symbol 一列，映射给常数权重。"""
    cols = sorted(mapping.keys())
    return pd.DataFrame({s: mapping[s] for s in cols}, index=idx)


def test_zero_weights_nav_constant():
    """① 权重全 0：净值始终不变，成本与资金费率为 0。"""
    close, open_, idx = _prices(n=10, symbols=("BTC", "ETH"))
    w = _weights(idx, {"BTC": 0.0, "ETH": 0.0})
    eng = BacktestEngine({"initial_capital": 1e6})
    snap, fills, _, _ = eng.run(w, close, open_)
    assert np.allclose(snap["nav"].values, 1e6)
    assert snap["fee"].sum() == 0
    assert snap["funding"].sum() == 0


def test_full_long_nav_equals_price_change():
    """② 单币满仓做多，无成本无资金费率：净值变化 = 该币价格变化。"""
    close, open_, idx = _prices(n=6, symbols=("BTC",), start_price=100.0)
    w = _weights(idx, {"BTC": 1.0})
    eng = BacktestEngine({"initial_capital": 1e6}, cost_model=FixedCost(0.0, 0.0))
    snap, fills, _, _ = eng.run(w, close, open_)
    # 满仓做多：净值应跟随 BTC 价格（成交价用下一根开盘价，近似跟随 close）
    price_ret = close["BTC"].iloc[-1] / close["BTC"].iloc[0] - 1
    nav_ret = snap["nav"].iloc[-1] / 1e6 - 1
    assert abs(nav_ret - price_ret) < 0.05


def _constant_prices(n=6, price=100.0):
    """恒定价格面板（无波动），用于精确验证。"""
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    close = pd.DataFrame({"BTC": [price] * n}, index=idx)
    return close, close.copy(), idx


def test_same_coin_long_short_pnl_zero():
    """③ 同一币等额多空：价格盈亏为 0，净值只减少成本。"""
    close, open_, idx = _constant_prices()
    # 做多(+1) → 反手做空(-1) → 平仓(0)，价格恒定则盈亏为 0
    w = pd.DataFrame({"BTC": [1.0, 1.0, -1.0, -1.0, 0.0, 0.0]}, index=idx)
    eng = BacktestEngine({"initial_capital": 1e6}, cost_model=FixedCost(0.0, 0.0))
    snap, fills, _, _ = eng.run(w, close, open_)
    assert abs(snap["nav"].iloc[-1] - 1e6) < 1e-6


def test_cost_only_changes_nav_by_fee_diff():
    """④ 只改成本参数：两次回测净值差额 = 累计成交金额 × 费率差。"""
    close, open_, idx = _constant_prices()
    w = pd.DataFrame({"BTC": [1.0] * len(idx)}, index=idx)
    eng0 = BacktestEngine({"initial_capital": 1e6}, cost_model=FixedCost(0.0, 0.0))
    eng1 = BacktestEngine({"initial_capital": 1e6}, cost_model=FixedCost(0.001, 0.0))
    snap0, fills0, _, _ = eng0.run(w, close, open_)
    snap1, fills1, _, _ = eng1.run(w, close, open_)
    traded1 = pd.DataFrame(fills1)["notional"].sum()
    diff = snap0["nav"].iloc[-1] - snap1["nav"].iloc[-1]
    assert abs(diff - traded1 * 0.001) < 1e-6


def test_constant_funding_rate():
    """⑤ 恒定资金费率：累计 = 名义价值 × 费率 × 结算次数。"""
    close, open_, idx = _constant_prices()
    w = pd.DataFrame({"BTC": [1.0] * len(idx)}, index=idx)
    fr = pd.DataFrame({"BTC": 0.0001}, index=idx)
    eng = BacktestEngine({"initial_capital": 1e6, "cash_buffer_ratio": 0.0},
                         cost_model=FixedCost(0.0, 0.0))
    snap, fills, _, _ = eng.run(w, close, open_, funding_rate=fr)
    # 价格恒定 → 名义价值 = 1e6；第一天买入、第二天成交，故结算 n-1 次，多头付费率
    expected = 1e6 * 0.0001 * (len(idx) - 1)
    assert abs(abs(snap["funding"].sum()) - expected) < 1.0


def test_no_future_function():
    """⑥ 未来函数：改动 t 之后的行情，t 及之前的记录不变。"""
    close, open_, idx = _prices(n=10, symbols=("BTC", "ETH"), seed=1)
    w = _weights(idx, {"BTC": 1.0, "ETH": -1.0})
    eng = BacktestEngine({"initial_capital": 1e6})
    snap1, fills1, _, _ = eng.run(w, close, open_)

    # 污染第 6 根（index 5）之后的行情
    close2 = close.copy()
    open2 = open_.copy()
    close2.iloc[6:] = close2.iloc[6:] * 999.0
    open2.iloc[6:] = open2.iloc[6:] * 999.0
    snap2, fills2, _, _ = eng.run(w, close2, open2)

    # t 及之前（前 5 期）的快照应完全一致
    pd.testing.assert_frame_equal(snap1.iloc[:5], snap2.iloc[:5])
