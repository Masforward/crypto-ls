"""回测主循环：逐时点推进，只调度各模块（不自己算盈亏/记账）。

顺序：资金费率结算 → 读目标权重 → 生成订单 → 成交 → 交给账户记账 → 快照。
主循环只负责按时间推进和调用各模块；成本/盈亏/持仓/现金都由对应模块处理。
"""
import pandas as pd

from .account import AccountBook
from .cost import FixedCost
from .execution import ExecutionSimulator


class BacktestEngine:
    """回测引擎：目标权重表 + 行情 → 账户记录（只调度，不内联计算）。"""

    name = "backtest_engine"

    def __init__(self, config=None, cost_model=None):
        cfg = config or {}
        self.initial_capital = float(cfg.get("initial_capital", 1e6))
        self.buffer_ratio = float(cfg.get("cash_buffer_ratio", 0.01))
        self.cost_model = cost_model or FixedCost()
        self.executor = ExecutionSimulator(cfg, self.cost_model)

    def run(self, target_weights, close_prices, open_prices=None, daily_volume=None,
            funding_rate=None):
        """跑回测，返回 (账户快照表, 成交记录表)。

        target_weights : 目标权重表（时间×币种，正做多负做空，NaN 不交易）
        close_prices   : 收盘价面板（时间×币种，用于按市值计价）
        open_prices    : 开盘价面板（成交价 = 下一根开盘价，缺省用收盘价）
        daily_volume   : 日均成交额面板（时间×币种）
        funding_rate   : 资金费率面板（时间×币种，可选）——【暂时悬空】
                        数据层尚未落盘资金费率（funding.py 未导出对外函数），
                        目前回测只用 K 线表，真实回测此参数传 None。
        """
        dates = list(target_weights.index)
        account = AccountBook(self.initial_capital, self.buffer_ratio)
        all_fills = []
        cash_shortfalls = []

        for i, t in enumerate(dates):
            close = close_prices.loc[t] if t in close_prices.index else pd.Series(dtype=float)

            # ① 资金费率结算（悬空参数，传 None 则跳过）
            fr_t = (funding_rate.loc[t]
                    if funding_rate is not None and t in funding_rate.index else None)
            funding_paid = account.settle_funding(close, fr_t)

            # ② 读目标权重 → 生成订单（预留现金缓冲，不参与买入）
            nav = account.nav(close)
            investable_nav = max(nav - account.buffer, 0.0)  # 预留 buffer 吸收执行偏差
            tw = target_weights.loc[t]
            orders, ignored_notional = self.executor.generate_orders(
                tw, account.positions, close, investable_nav)

            # ③ 成交：t 决策，t 之后成交（下一根开盘价）
            if i + 1 < len(dates):
                next_t = dates[i + 1]
                if open_prices is not None and next_t in open_prices.index:
                    fill_prices = open_prices.loc[next_t]
                else:
                    fill_prices = close_prices.loc[next_t] if next_t in close_prices.index else close
            else:
                fill_prices = close
            vol = daily_volume.loc[t] if daily_volume is not None and t in daily_volume.index else None
            fills, unfilled = self.executor.execute(orders, fill_prices, vol)

            # ④ 记账（交给账户记账模块）
            cost = account.apply_fills(fills)
            for f in fills:
                all_fills.append({"time": t, **f})
            # 记账后检查现金：透支超过缓冲 → 记录（不中断回测）
            if account.cash < 0:
                cash_shortfalls.append((t, account.cash))

            # ⑤ 账户快照（交给账户记账模块）
            snap = account.snapshot(
                t, close, funding_paid=funding_paid,
                traded=cost["traded_notional"], fee=cost["fee"],
                slippage=cost["slippage"], ignored=ignored_notional,
                unfilled=unfilled)
            account.snapshots.append(snap)

        return account.to_frame(), pd.DataFrame(all_fills), account.position_snapshots, cash_shortfalls
