"""信号模块：预处理（6 步，每步在每个时刻的截面上做）。

步骤：①方向统一 ②缺失处理 ③去极值 ④标准化 ⑤中性化 ⑥再标准化。
①②③④ = 中性化前；再加⑤⑥ = 中性化后。
"""
import numpy as np
import pandas as pd

MAD_SCALE = 1.4826   # MAD → 标准差的换算系数（正态分布下）
WINSOR_K = 3.0       # 去极值的标准差倍数


def _winsorize(series):
    """③ 去极值：截断到 中位数 ± 3×1.4826×MAD。"""
    med = series.median()
    mad = (series - med).abs().median()
    if pd.isna(mad) or mad == 0:
        return series
    upper = med + WINSOR_K * MAD_SCALE * mad
    lower = med - WINSOR_K * MAD_SCALE * mad
    return series.clip(lower, upper)


def _zscore(series):
    """④ 标准化：截面 z-score（减均值、除标准差）。"""
    std = series.std()
    if pd.isna(std) or std == 0:
        return series - series.mean()
    return (series - series.mean()) / std


def _neutralize(series, exposures):
    """⑤ 中性化：对 exposures（一列或多列）做多元回归，取残差。"""
    valid = series.notna()
    for e in exposures:
        valid &= e.notna()
    if valid.sum() < 3:
        return series
    y = series[valid].values.astype(float)
    cols = [np.ones(valid.sum())] + [e[valid].values.astype(float) for e in exposures]
    X = np.column_stack(cols)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    out = series.copy()
    out[valid] = y - X @ coef
    return out


def preprocess(score, direction, size=None, beta=None, min_valid=20):
    """对因子分数表做预处理（6 步）。

    score     : 分数表（时间 × 币种），因子原始值
    direction : 预期方向（+1 / -1）
    size      : 规模表（时间 × 币种，成交额对数），中性化暴露；None 则只做到④（中性化前）
    beta      : beta 表（时间 × 币种），可选，和 size 一起做多元回归
    min_valid : 有效币数阈值，少于该数的时刻整行不出信号

    返回处理后的分数表：不传 size 时 = 中性化前（①②③④），传 size 时 = 中性化后（全部 6 步）。
    """
    # ① 方向统一：让分数越高越看多
    out = score * direction

    # ② 缺失处理：保留缺失，有效币数 < min_valid 的时刻整行 NaN
    valid_count = out.notna().sum(axis=1)
    out = out.copy()
    out[valid_count < min_valid] = np.nan

    # ③④（⑤⑥）逐行（每个时刻的截面）做
    exposures = []
    if size is not None:
        exposures.append(size)
    if beta is not None:
        exposures.append(beta)

    for idx in out.index:
        row = out.loc[idx]
        if row.notna().sum() < min_valid:
            continue
        row = _winsorize(row)          # ③ 去极值
        row = _zscore(row)             # ④ 标准化
        if exposures:                  # ⑤ 中性化 + ⑥ 再标准化
            exps = [e.loc[idx] for e in exposures]
            row = _neutralize(row, exps)
            row = _zscore(row)
        out.loc[idx] = row

    return out
