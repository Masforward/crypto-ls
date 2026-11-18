"""稳健性检验：权重推迟一天、成本加倍、两种成交价、调仓频率 1/3/5 天。"""
import pandas as pd

from ..portfolio.rebalance import turnover_control
from .cost import FixedCost
from .performance import performance_metrics


def _summary(metrics):
    """提取关键指标做对比。"""
    return {
        "total_return": metrics.get("total_return", float("nan")),
        "ann_return": metrics.get("ann_return", float("nan")),
        "sharpe": metrics.get("sharpe", float("nan")),
        "max_drawdown": metrics.get("max_drawdown", float("nan")),
    }


def robustness_checks(engine, target_weights, close, open_, daily_volume=None,
                      base_cost=None):
    """跑多个变体，返回 {变体名: 关键绩效指标}。

    engine          : 基线回测引擎
    target_weights  : 目标权重表
    close / open_   : 收盘/开盘价面板
    daily_volume    : 日均成交额面板
    base_cost       : 基线成本模型（用于成本加倍的变体）
    """
    results = {}

    # 基线
    snap, *_ = engine.run(target_weights, close, open_, daily_volume)
    results["baseline"] = _summary(performance_metrics(snap))

    # ① 权重整体推迟一天
    shifted = target_weights.shift(1)
    shifted.iloc[0] = 0.0
    snap, *_ = engine.run(shifted, close, open_, daily_volume)
    results["weight_shift_1d"] = _summary(performance_metrics(snap))

    # ② 成本加倍（新建双倍费率的引擎）
    if base_cost is not None:
        double_cost = FixedCost(base_cost.fee_rate * 2, base_cost.slippage_bps * 2)
        cfg = {"initial_capital": engine.initial_capital,
               "cash_buffer_ratio": engine.buffer_ratio}
        eng2 = engine.__class__(cfg, cost_model=double_cost)
        snap, *_ = eng2.run(target_weights, close, open_, daily_volume)
        results["cost_doubled"] = _summary(performance_metrics(snap))

    # ③ 两种成交价：用收盘价成交（代替下一根开盘价）
    snap, *_ = engine.run(target_weights, close, close, daily_volume)
    results["fill_at_close"] = _summary(performance_metrics(snap))

    # ④ 调仓频率 3、5 天（用换手控制"每 N 天调一次，其他天沿用"）
    for freq in (3, 5):
        w_freq, _ = turnover_control(target_weights, {"rebalance_freq": freq, "adjustment": 1.0})
        snap, *_ = engine.run(w_freq, close, open_, daily_volume)
        results[f"rebalance_{freq}d"] = _summary(performance_metrics(snap))

    return pd.DataFrame(results).T
