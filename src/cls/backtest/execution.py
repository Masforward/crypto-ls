"""成交模拟：目标权重 → 订单 → 成交记录。

交易台的职责：生成订单、模拟成交。不修改目标权重、不记账。
"""
import numpy as np
import pandas as pd

from .cost import FixedCost


class ExecutionSimulator:
    """成交模拟器：把目标权重差额转成订单和成交。"""

    name = "execution"

    def __init__(self, config=None, cost_model=None):
        cfg = config or {}
        self.min_qty = cfg.get("min_qty", 0.0)          # 最小下单数量
        self.qty_step = cfg.get("qty_step", 0.0)        # 数量步长
        self.min_notional = cfg.get("min_notional", 0.0)  # 最小名义金额
        self.volume_frac = cfg.get("volume_frac", 0.05)   # 单笔 ≤ 日均成交额 × 此比例
        self.cost_model = cost_model or FixedCost()

    def generate_orders(self, target_weights, positions, prices, nav):
        """目标权重 → 目标数量 → 与当前持仓差额 → 订单列表。

        target_weights : 目标权重 Series（正做多、负做空，NaN 不交易）
        positions      : 当前持仓数量 Series（币种 → 数量）
        prices         : 当前价格 Series
        nav            : 当前净值
        """
        orders = []
        ignored_notional = 0.0
        for symbol, tw in target_weights.items():
            if pd.isna(tw):
                continue
            price = prices.get(symbol)
            if price is None or pd.isna(price) or price <= 0:
                continue
            target_qty = tw * nav / price                 # 目标数量
            cur_qty = positions.get(symbol, 0.0)
            diff = target_qty - cur_qty                   # 差额
            if abs(diff) < 1e-12:
                continue
            qty = self._round_qty(abs(diff))
            if qty <= 0 or qty < self.min_qty:
                ignored_notional += abs(diff) * price
                continue
            if qty * price < self.min_notional:
                ignored_notional += abs(diff) * price
                continue
            orders.append({
                "symbol": symbol,
                "side": 1 if diff > 0 else -1,            # 1 买 / -1 卖
                "qty": qty,
                "ref_price": price,
            })
        return orders, ignored_notional

    def _round_qty(self, qty):
        """按数量步长向下取整。"""
        if self.qty_step and self.qty_step > 0:
            return np.floor(qty / self.qty_step) * self.qty_step
        return qty

    def execute(self, orders, fill_prices, daily_volume):
        """订单 → 成交：按成交价成交，扣成本，超流动性上限的部分未成交。

        fill_prices  : 成交价 Series（symbol → 价格）
        daily_volume : 日均成交额 Series（symbol → 金额）
        返回 (成交记录列表, 未成交金额)
        """
        fills = []
        unfilled_notional = 0.0
        for o in orders:
            sym = o["symbol"]
            price = fill_prices.get(sym)
            if price is None or pd.isna(price) or price <= 0:
                unfilled_notional += o["qty"] * o["ref_price"]
                continue
            notional = o["qty"] * price
            # 流动性上限：单笔 ≤ 日均成交额 × 比例
            vol = daily_volume.get(sym) if daily_volume is not None else None
            if vol and vol > 0 and notional > vol * self.volume_frac:
                capped_qty = vol * self.volume_frac / price
                unfilled_notional += (o["qty"] - capped_qty) * price
                o["qty"] = capped_qty
                notional = o["qty"] * price
            cost = self.cost_model.cost(notional, vol)
            fills.append({
                "symbol": sym,
                "side": o["side"],
                "qty": o["qty"],
                "price": price,
                "notional": notional,
                "fee": cost["fee"],
                "slippage": cost["slippage"],
            })
        return fills, unfilled_notional
