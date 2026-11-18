"""回测主循环：逐时点推进，按固定顺序调度各模块。

顺序：资金费率结算 → 行情更新/按市值计价 → 读目标权重 → 生成订单
     → 成交 → 记账 → 账户快照。
每一步只能用当前时刻之前的数据（成交价用下一根开盘价，结构上避免未来函数）。
"""
import numpy as np
import pandas as pd

from .cost import FixedCost
from .execution import ExecutionSimulator


class BacktestEngine:
    """回测引擎：目标权重表 + 行情 → 账户记录。"""

    name = "backtest_engine"

    def __init__(self, config=None, cost_model=None):
        cfg = config or {}
        self.initial_capital = float(cfg.get("initial_capital", 1e6))
        self.cost_model = cost_model or FixedCost()
        self.executor = ExecutionSimulator(cfg, self.cost_model)

    def run(self, target_weights, close_prices, open_prices=None, daily_volume=None,
            funding_rate=None):
        """跑回测，返回 (账户快照列表, 全部成交记录)。

        target_weights : 目标权重表（时间×币种，正做多负做空，NaN 不交易）
        close_prices   : 收盘价面板（时间×币种，用于按市值计价）
        open_prices    : 开盘价面板（成交价 = 下一根开盘价，缺省用收盘价）
        daily_volume   : 日均成交额面板（时间×币种）
        funding_rate   : 资金费率面板（时间×币种，可选）
        """
        dates = list(target_weights.index)
        cash = self.initial_capital
        positions = {}                      # symbol -> 数量
        snapshots = []
        all_fills = []

        for i, t in enumerate(dates):
            close = close_prices.loc[t] if t in close_prices.index else pd.Series(dtype=float)

            # ① 行情更新 + 按市值计价
            nav = cash
            for s, qty in positions.items():
                if s in close.index and not pd.isna(close[s]):
                    nav += qty * close[s]

            # ② 资金费率结算（多头付/空头收，按持仓名义价值）
            funding_paid = 0.0
            if funding_rate is not None and t in funding_rate.index and positions:
                fr = funding_rate.loc[t]
                for s, qty in positions.items():
                    if s in fr.index and not pd.isna(fr[s]) and s in close.index:
                        funding_paid -= qty * close[s] * fr[s]
                cash += funding_paid

            # ③ 读目标权重 → 生成订单
            tw = target_weights.loc[t]
            orders, ignored_notional = self.executor.generate_orders(
                tw, positions, close, nav)

            # ④ 成交：t 决策，t 之后成交（下一根开盘价）
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

            # ⑤ 记账
            traded_notional = 0.0
            fee_total = 0.0
            slippage_total = 0.0
            for f in fills:
                cash -= f["side"] * f["qty"] * f["price"]   # 买入付钱 / 卖出收钱
                cash -= f["fee"] + f["slippage"]            # 成本
                positions[f["symbol"]] = positions.get(f["symbol"], 0.0) + f["side"] * f["qty"]
                traded_notional += f["notional"]
                fee_total += f["fee"]
                slippage_total += f["slippage"]
                all_fills.append({"time": t, **f})

            # ⑥ 账户快照（成交后重新按市值计价）
            long_mv = 0.0
            short_mv = 0.0
            for s, qty in positions.items():
                if s in close.index and not pd.isna(close[s]):
                    mv = qty * close[s]
                    if qty > 0:
                        long_mv += mv
                    else:
                        short_mv += mv
            nav_after = cash + long_mv + short_mv
            snapshots.append({
                "time": t,
                "nav": nav_after,
                "cash": cash,
                "long_mv": long_mv,
                "short_mv": short_mv,
                "gross": (long_mv - short_mv) / nav_after if nav_after else 0.0,
                "net": (long_mv + short_mv) / nav_after if nav_after else 0.0,
                "traded_notional": traded_notional,
                "fee": fee_total,
                "slippage": slippage_total,
                "funding": funding_paid,
                "ignored_notional": ignored_notional,
                "unfilled_notional": unfilled,
                "n_positions": len([p for p in positions.values() if abs(p) > 1e-12]),
            })

        snapshots_df = pd.DataFrame(snapshots).set_index("time")
        fills_df = pd.DataFrame(all_fills)
        return snapshots_df, fills_df
