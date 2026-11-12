"""换手控制：调仓频率 + 缓冲区 + 部分调整 + 换手率。"""
import numpy as np
import pandas as pd


def _dollar_neutralize(w):
    """美元中性：多空两边缩到相同总金额（换手调整后重新保证）。"""
    longs = w[w > 0]
    shorts = w[w < 0]
    ls = longs.sum()
    ss = -shorts.sum()
    if ls > 0 and ss > 0:
        scale = min(ls, ss)
        w = w.copy()
        w[w > 0] = w[w > 0] / ls * scale
        w[w < 0] = w[w < 0] / ss * scale
    return w


def turnover_control(weights, config):
    """对目标权重表做换手控制，返回 (最终权重表, 换手率序列)。

    config:
      rebalance_freq : 调仓频率（每 N 天调一次，非调仓日沿用上期）
      buffer         : 缓冲区（新旧权重差 < buffer 的币不调整）
      adjustment     : 部分调整系数（新 = 旧 + 系数×(目标−旧)，1=全调，0=不调）
      dollar_neutral : 调整后是否重新美元中性
    """
    freq = config.get("rebalance_freq", 1)
    buffer = config.get("buffer", 0.0)
    adj = config.get("adjustment", 1.0)
    dollar_neutral = config.get("dollar_neutral", True)

    final = pd.DataFrame(np.nan, index=weights.index, columns=weights.columns)
    turnovers = []
    prev = None

    for i, t in enumerate(weights.index):
        target = weights.loc[t]

        # ① 调仓频率：非调仓日沿用上期权重
        if prev is not None and (i % freq != 0):
            final.loc[t] = prev
            turnovers.append(0.0)
            continue

        if prev is None:
            new = target.copy()
        else:
            # ② 缓冲区 + ③ 部分调整
            new = prev.copy()
            for col in weights.columns:
                tv = target[col]
                pv = prev[col]
                if pd.isna(tv) or pd.isna(pv):
                    new[col] = tv if pd.notna(tv) else pv
                    continue
                diff = tv - pv
                if abs(diff) < buffer:          # 差异小于缓冲区 → 不动
                    continue
                new[col] = pv + adj * diff       # 部分调整

        # ④ 调整后重新美元中性（部分调整可能破坏中性）
        if dollar_neutral:
            new = _dollar_neutralize(new)

        # ⑤ 换手率 = 权重变化绝对值之和
        turnover = 0.0 if prev is None else (new - prev).abs().sum()
        final.loc[t] = new
        turnovers.append(turnover)
        prev = new

    return final, pd.Series(turnovers, index=weights.index)
