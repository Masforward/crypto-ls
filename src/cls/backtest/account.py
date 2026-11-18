"""账户记账模块（清算中台）：维护持仓、现金、净值，产出账户快照。

只接收成交记录和行情，负责记账和算盈亏；不下单、不读未来数据。
"""
import numpy as np
import pandas as pd


class AccountBook:
    """账户记账：接收成交，维护现金/持仓/净值，产出逐日快照。"""

    name = "account_book"

    def __init__(self, initial_capital=1e6, buffer_ratio=0.01):
        self.initial_capital = float(initial_capital)
        self.buffer = self.initial_capital * buffer_ratio  # 预留现金缓冲（不参与买入）
        self.cash = self.initial_capital
        self.positions = {}          # symbol -> 数量（正=多，负=空）
        self.snapshots = []
        self.position_snapshots = []  # 每期逐币持仓快照（对账用）

    # ---- 核心操作 ----

    def nav(self, close):
        """按市值计价：现金 + 持仓市值（用当前价）。"""
        total = self.cash
        for s, qty in self.positions.items():
            if s in close.index and not pd.isna(close[s]):
                total += qty * close[s]
        return total

    def apply_fills(self, fills):
        """记账：把成交记录应用到现金和持仓。返回成本汇总。"""
        traded = fee = slippage = 0.0
        for f in fills:
            self.cash -= f["side"] * f["qty"] * f["price"]   # 买入付钱 / 卖出收钱
            self.cash -= f["fee"] + f["slippage"]            # 成本
            self.positions[f["symbol"]] = (
                self.positions.get(f["symbol"], 0.0) + f["side"] * f["qty"])
            traded += f["notional"]
            fee += f["fee"]
            slippage += f["slippage"]
        return {"traded_notional": traded, "fee": fee, "slippage": slippage}

    def settle_funding(self, close, funding_rate):
        """资金费率结算（悬空参数，暂不用）。返回净付出（负=付出，正=收到）。"""
        if funding_rate is None or not self.positions:
            return 0.0
        funding_paid = 0.0
        for s, qty in self.positions.items():
            if s in close.index and s in funding_rate.index \
                    and not pd.isna(close[s]) and not pd.isna(funding_rate[s]):
                funding_paid -= qty * close[s] * funding_rate[s]
        self.cash += funding_paid
        return funding_paid

    def snapshot(self, t, close, funding_paid=0.0, traded=0.0, fee=0.0,
                 slippage=0.0, ignored=0.0, unfilled=0.0):
        """生成账户快照（成交后按市值计价）。"""
        self.position_snapshots.append((t, dict(self.positions)))
        long_mv = short_mv = 0.0
        for s, qty in self.positions.items():
            if s in close.index and not pd.isna(close[s]):
                mv = qty * close[s]
                if qty > 0:
                    long_mv += mv
                else:
                    short_mv += mv
        nav_after = self.cash + long_mv + short_mv
        return {
            "time": t,
            "nav": nav_after,
            "cash": self.cash,
            "long_mv": long_mv,
            "short_mv": short_mv,
            "gross": (long_mv - short_mv) / nav_after if nav_after else 0.0,
            "net": (long_mv + short_mv) / nav_after if nav_after else 0.0,
            "traded_notional": traded,
            "fee": fee,
            "slippage": slippage,
            "funding": funding_paid,
            "ignored_notional": ignored,
            "unfilled_notional": unfilled,
            "n_positions": len([p for p in self.positions.values() if abs(p) > 1e-12]),
        }

    def to_frame(self):
        """所有快照 → DataFrame（index = 时间）。"""
        return pd.DataFrame(self.snapshots).set_index("time")
