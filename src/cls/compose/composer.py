"""因子合成模块：多个因子分数表 → 一张综合分数表 + 每期因子权重。

只依赖分数表（和历史评价结果），不读数据、不联网、不知道具体因子。
输入是预处理过的分数（方向已统一、已标准化）。
"""
import numpy as np
import pandas as pd


class Composer:
    """合成器基类：输入多个因子分数表，输出综合分数表 + 每期因子权重。"""

    name = ""
    min_factors = 2      # 有效因子数下限，不足则该币当期为缺失

    def __init__(self, **kwargs):
        # 接受任意配置参数；等权等方法用不到就忽略
        self.config = kwargs

    def compose(self, scores, ic_history=None):
        """合成。

        scores     : dict {因子名: 分数表（时间×币种，预处理后）}
        ic_history : dict {因子名: Series（index=IC 计算时刻，值=RankIC）}，可选
        返回 (综合分数表 时间×币种, 权重表 时间×因子)
        """
        raise NotImplementedError

    # ---- 公共工具 ----

    def _align(self, scores):
        """按时间和币种对齐（union），缺失处 NaN。"""
        idx = None
        cols = None
        for s in scores.values():
            idx = s.index if idx is None else idx.union(s.index)
            cols = s.columns if cols is None else cols.union(s.columns)
        idx = idx.sort_values()
        cols = cols.sort_values()
        aligned = {k: v.reindex(index=idx, columns=cols) for k, v in scores.items()}
        return aligned, idx, cols

    def _zscore(self, df):
        """截面标准化（每行减均值、除标准差），保证综合分数每期尺度一致。"""
        mu = df.mean(axis=1)
        sd = df.std(axis=1).replace(0, np.nan)
        return df.sub(mu, axis=0).div(sd, axis=0)

    def _weighted_composite(self, aligned, idx, cols, weights):
        """按每期因子权重加权平均（缺失因子跳过、权重重新归一），得综合分数。"""
        names = list(aligned.keys())
        comp = pd.DataFrame(np.nan, index=idx, columns=cols)
        for t in idx:
            w = weights.loc[t].to_dict()
            vals = np.column_stack([aligned[n].loc[t].to_numpy() for n in names])
            w_arr = np.array([w[n] for n in names], dtype=float)
            valid = ~np.isnan(vals)
            n_valid = valid.sum(axis=1)
            denom = np.where(valid, w_arr, 0.0).sum(axis=1)
            num = np.nansum(np.where(valid, vals * w_arr, 0.0), axis=1)
            row = np.where(n_valid >= self.min_factors, num / denom, np.nan)
            comp.loc[t] = row
        return self._zscore(comp)

    def _equal_weights(self, idx, names):
        return pd.DataFrame(1.0 / len(names), index=idx, columns=names)


class EqualWeight(Composer):
    """等权合成：各因子分数简单平均。"""

    name = "equal_weight"

    def compose(self, scores, ic_history=None):
        aligned, idx, cols = self._align(scores)
        weights = self._equal_weights(idx, list(aligned.keys()))
        comp = self._weighted_composite(aligned, idx, cols, weights)
        return comp, weights


class _ICBased(Composer):
    """基于历史 IC 的加权合成（IC 加权 / ICIR 加权 的公共逻辑）。"""

    def __init__(self, lookback=60, holdback=2, allow_negative=False, cap=None):
        self.lookback = lookback          # 回看窗口 N 期
        self.holdback = holdback          # 时点：t 时刻只能用 < t-holdback 的 IC（持有1期滞后1期→2）
        self.allow_negative = allow_negative
        self.cap = cap                    # 单因子权重上限

    def _score_of(self, hist):
        """从历史 RankIC 序列算该因子的"得分"（IC 加权=均值，ICIR 加权=均值/标准差）。"""
        raise NotImplementedError

    def _compute_weights(self, idx, names, ic_history):
        weights = pd.DataFrame(np.nan, index=idx, columns=names)
        for t in idx:
            w = {}
            for n in names:
                hist = ic_history.get(n) if ic_history else None
                if hist is None:
                    w[n] = np.nan
                else:
                    past = hist[hist.index < t - pd.Timedelta(days=self.holdback - 1)]
                    past = past.tail(self.lookback)
                    w[n] = self._score_of(past) if len(past) >= self.lookback else np.nan
            # 历史不足 → 退回等权
            if any(np.isnan(v) for v in w.values()):
                weights.loc[t] = 1.0 / len(names)
                continue
            # 不允许负权重：负→0
            if not self.allow_negative:
                w = {k: max(v, 0.0) for k, v in w.items()}
            total = sum(w.values())
            if total <= 0:                 # 全为 0/负 → 退回等权
                weights.loc[t] = 1.0 / len(names)
                continue
            w = {k: v / total for k, v in w.items()}   # 归一
            # 单因子权重上限：截断后重新归一（迭代一次）
            if self.cap is not None:
                for k in w:
                    if w[k] > self.cap:
                        w[k] = self.cap
                s = sum(w.values())
                w = {k: v / s for k, v in w.items()}
            weights.loc[t] = w
        return weights

    def compose(self, scores, ic_history=None):
        aligned, idx, cols = self._align(scores)
        names = list(aligned.keys())
        weights = self._compute_weights(idx, names, ic_history)
        comp = self._weighted_composite(aligned, idx, cols, weights)
        return comp, weights


class ICWeighted(_ICBased):
    """IC 加权：权重 ∝ 过去 N 期 RankIC 均值。"""

    name = "ic_weighted"

    def _score_of(self, hist):
        return float(hist.mean())


class ICIRWeighted(_ICBased):
    """ICIR 加权：权重 ∝ 过去 N 期 ICIR（均值/标准差），兼顾预测力和稳定性。"""

    name = "icir_weighted"

    def _score_of(self, hist):
        mean = hist.mean()
        std = hist.std()
        return float(mean / std) if std > 0 else float(mean)  # std=0 退化：退回均值
