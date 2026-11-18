"""回测成本模型：只负责算钱（手续费 + 滑点），不决定是否成交。

可替换组件，在配置中选择：
  fixed     —— 固定费率：手续费按吃单费率，滑点按固定基点
  impact    —— 冲击成本：固定费率基础上加冲击成本（∝ 金额/成交额 的平方根）
"""


class CostModel:
    """成本模型基类。"""

    name = ""

    def cost(self, notional, daily_volume=None):
        """算一笔成交的总成本（手续费 + 滑点）。

        notional     : 成交金额（名义价值）
        daily_volume : 该币日均成交额（冲击成本用，固定费率可忽略）
        返回 dict {fee, slippage, total}
        """
        raise NotImplementedError


class FixedCost(CostModel):
    """固定费率：手续费按吃单费率，滑点按固定基点，都按成交金额算。"""

    name = "fixed"

    def __init__(self, fee_rate=0.0005, slippage_bps=2.0):
        self.fee_rate = fee_rate          # 吃单费率（如 0.05%）
        self.slippage_bps = slippage_bps  # 滑点基点（如 2bp = 0.02%）

    def cost(self, notional, daily_volume=None):
        fee = notional * self.fee_rate
        slippage = notional * self.slippage_bps / 10000.0
        return {"fee": fee, "slippage": slippage, "total": fee + slippage}


class ImpactCost(FixedCost):
    """冲击成本：固定费率基础上加冲击成本，与订单金额占日均成交额比例的平方根成正比。"""

    name = "impact"

    def __init__(self, fee_rate=0.0005, slippage_bps=2.0, impact_coef=0.001):
        super().__init__(fee_rate, slippage_bps)
        self.impact_coef = impact_coef     # 冲击成本系数

    def cost(self, notional, daily_volume=None):
        base = super().cost(notional, daily_volume)
        impact = 0.0
        if daily_volume and daily_volume > 0:
            ratio = notional / daily_volume           # 订单金额占日均成交额比例
            impact = notional * self.impact_coef * (ratio ** 0.5)
        return {"fee": base["fee"], "slippage": base["slippage"] + impact,
                "total": base["fee"] + base["slippage"] + impact}
