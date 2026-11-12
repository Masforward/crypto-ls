"""组合管理模块：综合分数表 + 风险输入 + 约束 → 目标权重表 + 诊断。

不知道分数由哪些因子合成而来。只接收综合分数表、风险输入、约束配置。
"""
import numpy as np
import pandas as pd


class PortfolioBuilder:
    """组合构建器基类：输入综合分数表、风险输入、约束配置 → 目标权重表。"""

    name = ""

    def __init__(self, config=None):
        self.config = config or {}

    def build(self, scores, risk=None, config=None, prev_weights=None):
        raise NotImplementedError


def _default_config():
    return {
        "long_short_frac": 0.2,      # 分位多空比例（前/后 20%）
        "gross": 1.0,                # 总杠杆上限（多空权重绝对值之和）
        "max_weight": 0.05,          # 单币权重上限
        "min_names": 5,              # 每边最少持仓数
        "dollar_neutral": True,      # 美元中性
        "liquidity_frac": 0.01,      # 单币持仓金额 ≤ 日均成交额 × 此比例
        "capital": 1e6,              # 资金规模（算流动性用）
    }


class QuantileLongShort(PortfolioBuilder):
    """分位多空基类：分数前 20% 做多、后 20% 做空，内部权重由 _assign_weights 决定。"""

    name = "quantile_long_short"

    def build(self, scores, risk=None, config=None, prev_weights=None):
        cfg = {**_default_config(), **(config or {})}
        frac = cfg["long_short_frac"]

        weights = pd.DataFrame(np.nan, index=scores.index, columns=scores.columns)
        diagnostics = []

        for t in scores.index:
            row = scores.loc[t].dropna()

            # ① 先排除不满足流动性的币
            row = self._filter_liquidity(row, risk, t, cfg)

            if len(row) == 0:
                weights.loc[t] = 0.0
                diagnostics.append({"built": False, "reason": "no_liquid"})
                continue

            # ② 分位多空选币
            n_side = max(int(len(row) * frac), 1)
            ranked = row.sort_values()
            shorts = ranked.index[:n_side]
            longs = ranked.index[-n_side:]

            # 最少持仓数不足 → 当期不建仓
            if len(longs) < cfg["min_names"] or len(shorts) < cfg["min_names"]:
                weights.loc[t] = 0.0
                diagnostics.append({"built": False, "reason": "min_names"})
                continue

            # ③ 分配权重（子类覆盖）
            w = self._assign_weights(row, longs, shorts, risk, t, cfg, scores.columns)

            # ④ 约束：截断归一 → 美元中性 → beta 中性（可选）
            w = self._constrain(w, cfg, risk, t)

            weights.loc[t] = w
            diagnostics.append(self._diagnose(w, cfg))

        return weights, pd.DataFrame(diagnostics, index=scores.index)

    def _assign_weights(self, row, longs, shorts, risk, t, cfg, all_columns):
        """等权：每边 1/n。子类覆盖实现分数加权 / 波动率倒数加权。"""
        w = pd.Series(0.0, index=all_columns)
        w[longs] = 1.0 / len(longs)
        w[shorts] = -1.0 / len(shorts)
        return w

    # ---- 子步骤 ----

    def _filter_liquidity(self, row, risk, t, cfg):
        """排除不满足流动性的币：单币最大持仓金额 ≤ 日均成交额 × 比例。"""
        if risk is None or "volume" not in risk or not cfg.get("liquidity_frac"):
            return row
        vol = risk["volume"]
        if t not in vol.index:
            return row
        vol_row = vol.loc[t].reindex(row.index)
        max_amount = cfg["capital"] * cfg["max_weight"]
        liquid = vol_row[vol_row >= max_amount / cfg["liquidity_frac"]]
        return row.reindex(liquid.index).dropna()

    def _constrain(self, w, cfg, risk=None, t=None):
        """按上限截断并重新归一，再调整美元中性（可选 beta 中性）。"""
        w = w.clip(-cfg["max_weight"], cfg["max_weight"])
        if cfg.get("dollar_neutral", True):
            w = self._dollar_neutralize(w)
        if cfg.get("beta_neutral", False) and risk and "beta" in risk and t is not None and t in risk["beta"].index:
            w = self._beta_neutralize(w, risk["beta"].loc[t])
        gross = w.abs().sum()
        if gross > cfg["gross"] and gross > 0:
            w = w * (cfg["gross"] / gross)
        return w

    def _beta_neutralize(self, w, beta_row):
        """beta 中性（选做，简化）：调整空头总额，使组合 beta 接近 0。

        组合 beta = Σ w_i·β_i。用空头对冲多头 beta：调整空头总额 S' = L·β_long/β_short。
        注意：这会轻微破坏美元中性（beta 中性优先）。
        """
        b = beta_row.reindex(w.index).fillna(0.0)
        port_beta = float((w * b).sum())
        if abs(port_beta) < 1e-6:
            return w
        mask_long = w > 0
        mask_short = w < 0
        if not mask_long.any() or not mask_short.any():
            return w
        lb = float((w * b)[mask_long].sum() / w[mask_long].sum())
        sb = float((w * b)[mask_short].sum() / -w[mask_short].sum())
        if lb > 1e-6 and sb > 1e-6:
            w = w.copy()
            target_short = w[mask_long].sum() * lb / sb
            cur_short = -w[mask_short].sum()
            w[mask_short] = w[mask_short] * (target_short / cur_short)
        return w

    def _dollar_neutralize(self, w):
        """把多头、空头两边都缩放到相同的总金额（美元中性）。"""
        longs = w[w > 0]
        shorts = w[w < 0]
        long_sum = longs.sum()
        short_sum = -shorts.sum()
        if long_sum > 0 and short_sum > 0:
            scale = min(long_sum, short_sum)
            w = w.copy()
            w[w > 0] = w[w > 0] / long_sum * scale
            w[w < 0] = w[w < 0] / short_sum * scale
        return w

    def _diagnose(self, w, cfg):
        """诊断：多空币数、总杠杆、净敞口、最大单币权重、约束是否满足。"""
        gross = w.abs().sum()
        net = w.sum()
        return {
            "built": True,
            "n_long": int((w > 0).sum()),
            "n_short": int((w < 0).sum()),
            "gross": float(gross),
            "net": float(net),
            "max_weight": float(w.abs().max()) if len(w) else 0.0,
            "dollar_neutral_ok": bool(abs(net) < 1e-6),
            "gross_ok": bool(gross <= cfg["gross"] + 1e-6),
            "max_weight_ok": bool((w.abs() <= cfg["max_weight"] + 1e-6).all()),
        }


class ScoreWeighted(QuantileLongShort):
    """分数加权：权重 ∝ 去均值后的分数，多头、空头各自归一。"""

    name = "score_weighted"

    def _assign_weights(self, row, longs, shorts, risk, t, cfg, all_columns):
        centered = row - row.mean()
        w = pd.Series(0.0, index=all_columns)
        long_scores = centered[longs]
        short_scores = centered[shorts]
        if long_scores.sum() != 0:
            w[longs] = long_scores / long_scores.sum()
        if short_scores.abs().sum() != 0:
            w[shorts] = short_scores / short_scores.abs().sum()   # 负权重，绝对值 ∝ |分数|
        return w


class InverseVolWeighted(QuantileLongShort):
    """波动率倒数加权：在分位多空基础上，权重 ∝ 1 / 波动率。"""

    name = "inverse_vol"

    def _assign_weights(self, row, longs, shorts, risk, t, cfg, all_columns):
        w = pd.Series(0.0, index=all_columns)
        if risk is None or "volatility" not in risk:
            return super()._assign_weights(row, longs, shorts, risk, t, cfg, all_columns)
        vol = risk["volatility"]
        if t not in vol.index:
            return super()._assign_weights(row, longs, shorts, risk, t, cfg, all_columns)
        vol_row = vol.loc[t].reindex(all_columns)
        inv_vol = 1.0 / vol_row.replace(0, np.nan)
        if inv_vol[longs].sum() > 0:
            w[longs] = inv_vol[longs] / inv_vol[longs].sum()
        if inv_vol[shorts].sum() > 0:
            w[shorts] = -inv_vol[shorts] / inv_vol[shorts].sum()
        return w


class MeanVariance(QuantileLongShort):
    """均值方差优化（选做）：预期收益 = 分数 × 经验 IC 系数，权重 ∝ μ/var（对角协方差）。"""

    name = "mean_variance"

    def _assign_weights(self, row, longs, shorts, risk, t, cfg, all_columns):
        ic_coef = cfg.get("ic_coef", 0.05)          # 经验 IC 系数
        mu = (row - row.mean()) * ic_coef            # 预期收益 ∝ 去均值分数
        w = pd.Series(0.0, index=all_columns)
        # 方差（对角协方差简化）：波动率²
        if risk and "volatility" in risk and t in risk["volatility"].index:
            vol = risk["volatility"].loc[t].reindex(all_columns)
        else:
            vol = pd.Series(1.0, index=all_columns)
        var = vol ** 2
        raw = mu / var                                # w ∝ μ / var（对角协方差的最优解）
        # 多头、空头各自归一
        if raw[longs].sum() > 0:
            w[longs] = raw[longs] / raw[longs].sum()
        if raw[shorts].abs().sum() > 0:
            w[shorts] = raw[shorts] / raw[shorts].abs().sum()
        return w
