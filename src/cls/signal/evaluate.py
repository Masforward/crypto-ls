"""信号模块：因子评价（IC/RankIC 预测力 + 稳定性 + 衰减 + 相关性 + 报告）。

只评价因子本身的预测能力，不构建组合、不回测收益。
只接收因子分数表和价格数据，对所有因子用同一套流程。
"""
import numpy as np
import pandas as pd

HORIZONS = [1, 2, 3, 5, 10]


def close_panel(symbols, start, end, interval="5m", data_dir=None):
    """日线收盘价面板（时间 × 币种），用于算下期收益。

    从数据层读 5m K 线，聚合成日线，再 pivot 成 close 面板。
    """
    from ..data import load_klines
    from .pipeline import _resample

    df = load_klines(symbols, start, end, interval, data_dir=data_dir)
    daily = _resample(df, "1d")
    return daily.pivot(index="open_time", columns="symbol", values="close")


def compute_forward_returns(close_panel, horizon=1):
    """下期收益：持有期 horizon 的累计收益 = close[t+h-1] / close[t-1] - 1。

    决策时刻 t 已知最新收盘 close[t-1]（t-1 到 t 那根已收盘），
    收益从 t 那根开始算，持有 h 根 → close[t+h-1] / close[t-1] - 1。
    """
    base = close_panel.shift(1)              # close[t-1]
    future = close_panel.shift(-(horizon - 1))  # close[t+h-1]
    return future / base - 1


def ic_series(score, forward_returns):
    """每期的 IC：因子值与下期收益的皮尔逊截面相关。"""
    out = []
    for t in score.index:
        s = score.loc[t]
        r = forward_returns.loc[t]
        valid = s.notna() & r.notna()
        out.append(np.corrcoef(s[valid], r[valid])[0, 1] if valid.sum() >= 2 else np.nan)
    return pd.Series(out, index=score.index)


def rankic_series(score, forward_returns):
    """每期的 RankIC：因子排名与收益排名的截面相关（更稳健）。"""
    out = []
    for t in score.index:
        s = score.loc[t].rank()
        r = forward_returns.loc[t].rank()
        valid = s.notna() & r.notna()
        out.append(np.corrcoef(s[valid], r[valid])[0, 1] if valid.sum() >= 2 else np.nan)
    return pd.Series(out, index=score.index)


def _newey_west_t(series, max_lag):
    """Newey-West 调整的 t 值（处理持有期>1 的重叠自相关）。

    max_lag = 持有期 - 1（持有期 h 的收益最多重叠 h-1 期）。
    """
    s = series.dropna()
    n = len(s)
    if n == 0 or s.std() == 0:
        return np.nan
    e = s - s.mean()                      # 去均值
    var = float((e ** 2).sum())           # 基础方差项 Σe²
    for lag in range(1, max_lag + 1):
        if lag >= n:
            break
        w = 1.0 - lag / (max_lag + 1)     # Bartlett 权重（越远权重越小）
        cov = float((e[lag:] * e[:-lag]).sum())
        var += 2.0 * w * cov              # 加上自协方差
    var /= n
    se = np.sqrt(var / n)                 # Newey-West 标准误
    return float(s.mean() / se)


def _ic_stats(series, max_lag=0):
    """IC 序列的统计量：均值、标准差、ICIR、为正比例、t 值。

    max_lag=0 用普通 t 值（持有期1）；max_lag>0 用 Newey-West（持有期>1 处理重叠）。
    """
    s = series.dropna()
    if len(s) == 0:
        return {"n": 0, "mean": np.nan, "std": np.nan,
                "icir": np.nan, "pos_ratio": np.nan, "t": np.nan}
    mean = s.mean()
    std = s.std(ddof=1)
    icir = mean / std if std > 0 else np.nan
    if max_lag > 0:
        t = _newey_west_t(series, max_lag)
    else:
        t = mean / (std / np.sqrt(len(s))) if std > 0 else np.nan
    return {"n": int(len(s)), "mean": float(mean), "std": float(std),
            "icir": float(icir), "pos_ratio": float((s > 0).mean()),
            "t": float(t)}


def evaluate(score, close_panel, horizons=HORIZONS):
    """评价一个因子：不同持有期的 IC/RankIC 统计量。

    score       : 因子分数表（时间 × 币种，预处理后）
    close_panel : 日线收盘价面板（时间 × 币种）
    horizons    : 持有期列表

    返回 dict：
      ic[h]      = 该持有期 IC 序列的统计量
      rankic[h]  = 该持有期 RankIC 序列的统计量
    """
    result = {"ic": {}, "rankic": {}}
    for h in horizons:
        fwd = compute_forward_returns(close_panel, h)
        result["ic"][h] = _ic_stats(ic_series(score, fwd), max_lag=h - 1)
        result["rankic"][h] = _ic_stats(rankic_series(score, fwd), max_lag=h - 1)
    return result


def monthly_rankic(score, close_panel, horizon=1):
    """分月 RankIC 均值（稳定性）：每期 RankIC 按月分组取均值。"""
    fwd = compute_forward_returns(close_panel, horizon)
    r = rankic_series(score, fwd)
    return r.groupby(r.index.tz_localize(None).to_period("M")).mean()


def factor_stability(score):
    """因子自身稳定性：相邻两期因子排名的相关系数（均值）。

    值越接近 1，说明因子值随时间变化越慢（更稳定）。
    """
    corrs = []
    prev = None
    for t in score.index:
        cur = score.loc[t].rank()
        if prev is not None:
            valid = cur.notna() & prev.notna()
            if valid.sum() >= 2:
                corrs.append(np.corrcoef(cur[valid], prev[valid])[0, 1])
        prev = cur
    return float(np.mean(corrs)) if corrs else np.nan


def coverage_stats(score, raw_score=None):
    """覆盖率与分布：有效币数比例、缺失率、极端值比例（预处理前）。

    score     : 预处理后的分数表（算有效币数、缺失率）
    raw_score : 预处理前的原始分数表（算极端值比例，可选）
    """
    n_symbols = score.shape[1]
    valid_per = (score.notna().sum(axis=1) / n_symbols).mean()
    missing_rate = 1.0 - valid_per
    extreme_ratio = np.nan
    if raw_score is not None:
        vals = raw_score.to_numpy(dtype=float)
        mu = np.nanmean(vals, axis=1, keepdims=True)
        sd = np.nanstd(vals, axis=1, keepdims=True)
        sd = np.where(sd == 0, np.nan, sd)
        z = (vals - mu) / sd
        extreme_ratio = float(np.nanmean(np.abs(z) > 3))
    return {"valid_ratio": float(valid_per), "missing_rate": float(missing_rate),
            "extreme_ratio": extreme_ratio}


def factor_correlation(scores):
    """因子相关性：每期截面相关取平均，输出相关矩阵（因子 × 因子）。"""
    names = list(scores.keys())
    n = len(names)
    corr = pd.DataFrame(np.eye(n), index=names, columns=names)
    for i in range(n):
        for j in range(i + 1, n):
            vals = []
            common = scores[names[i]].index.intersection(scores[names[j]].index)
            for t in common:
                a = scores[names[i]].loc[t]
                b = scores[names[j]].loc[t]
                valid = a.notna() & b.notna()
                if valid.sum() >= 2:
                    vals.append(np.corrcoef(a[valid], b[valid])[0, 1])
            c = float(np.mean(vals)) if vals else np.nan
            corr.iloc[i, j] = corr.iloc[j, i] = c
    return corr
