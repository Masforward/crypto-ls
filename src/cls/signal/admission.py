"""因子准入流程：评价 → 增量检验 → 准入门槛。

评价：RankIC / ICIR / t 值 / 衰减 / 分月 / 自相关（因子自身稳定性）/ 覆盖率。
增量检验：对已准入因子做截面回归取残差，评残差 RankIC（新因子是否带来"额外"信息）。
准入门槛：研究前定好，写死在 THRESHOLDS，事后不改。
"""
import numpy as np
import pandas as pd

from .evaluate import (compute_forward_returns, evaluate, factor_stability,
                       monthly_rankic, rankic_series, coverage_stats)

# 准入门槛（研究前定好，事后不改）
THRESHOLDS = {
    "min_abs_ic": 0.02,     # |RankIC 均值| 下限（绝对预测力）
    "min_t": 2.0,           # t 值下限（统计显著）
    "min_icir": 0.3,        # ICIR 下限（预测力稳定）
    "min_coverage": 0.5,    # 覆盖率下限（数据充分）
    "max_abs_corr": 0.8,    # 与已准入因子的相关上限（信息不重复）
}


def evaluate_factor(score, close_panel, raw_score=None):
    """单因子评价指标：RankIC 均值 / ICIR / t 值 / 正比例 / 衰减 / 稳定性 / 覆盖率。"""
    ev = evaluate(score, close_panel)
    r1 = ev["rankic"][1]
    return {
        "mean_ic": r1["mean"],
        "icir": r1["icir"],
        "t": r1["t"],
        "pos_ratio": r1["pos_ratio"],
        "decay": {str(h): ev["rankic"][h]["mean"] for h in ev["rankic"]},
        "stability": factor_stability(score),
        "coverage": coverage_stats(score, raw_score)["valid_ratio"],
        "monthly": monthly_rankic(score, close_panel, 1),
    }


def residual_rankic(score, close_panel, admitted_scores):
    """增量检验：把因子对已准入因子做截面回归，取残差，评残差 RankIC。

    残差 RankIC 显著 → 该因子在被已有因子解释后仍能预测收益（带来增量信息）。
    返回残差 RankIC 序列。
    """
    fwd = compute_forward_returns(close_panel, 1)
    resid = score.copy()
    for t in score.index:
        y = score.loc[t]
        if not admitted_scores:
            continue
        X = pd.DataFrame({n: s.loc[t] for n, s in admitted_scores.items()})
        valid = y.notna() & X.notna().all(axis=1) & fwd.loc[t].notna()
        if valid.sum() < 3:
            continue
        A = np.column_stack([np.ones(valid.sum()), X.loc[valid].to_numpy(dtype=float)])
        b = y.loc[valid].to_numpy(dtype=float)
        try:
            coef, *_ = np.linalg.lstsq(A, b, rcond=None)
            resid.loc[t, valid] = b - A @ coef
        except np.linalg.LinAlgError:
            pass
    return rankic_series(resid, fwd)


def admission_check(eval_result, corr_to_admitted=0.0, thresholds=THRESHOLDS):
    """门槛判断：返回 (通过?, 未通过原因列表)。"""
    reasons = []
    if abs(eval_result["mean_ic"]) < thresholds["min_abs_ic"]:
        reasons.append("|IC|过低")
    if abs(eval_result["t"]) < thresholds["min_t"]:
        reasons.append("t值不显著")
    if abs(eval_result["icir"]) < thresholds["min_icir"]:
        reasons.append("ICIR过低")
    if eval_result["coverage"] < thresholds["min_coverage"]:
        reasons.append("覆盖率过低")
    if abs(corr_to_admitted) > thresholds["max_abs_corr"]:
        reasons.append("与已准入因子高度相关")
    return (len(reasons) == 0, reasons)


def run_admission(scores, close_panel, raw_scores=None, thresholds=THRESHOLDS):
    """完整准入流程：按顺序评价 → 增量检验 → 门槛，返回结果表和准入名单。

    返回 (结果 DataFrame, 准入因子名列表)。
    """
    admitted = {}   # 已准入因子分数表（增量检验的基准）
    rows = []
    for name, score in scores.items():
        raw = raw_scores.get(name) if raw_scores else None
        ev = evaluate_factor(score, close_panel, raw)
        # 增量检验：残差 RankIC 均值
        resid_ic = residual_rankic(score, close_panel, admitted)
        resid_mean = float(resid_ic.mean()) if len(resid_ic) else np.nan
        # 与已准入因子的最大相关
        corr_to_admitted = 0.0
        for a_name, a_score in admitted.items():
            c = _cross_corr(score, a_score)
            corr_to_admitted = max(corr_to_admitted, abs(c))
        ok, reasons = admission_check(ev, corr_to_admitted, thresholds)
        rows.append({
            "factor": name,
            "mean_ic": ev["mean_ic"], "icir": ev["icir"], "t": ev["t"],
            "pos_ratio": ev["pos_ratio"], "coverage": ev["coverage"],
            "stability": ev["stability"], "resid_ic": resid_mean,
            "max_corr_admitted": corr_to_admitted,
            "admitted": ok, "reason": "; ".join(reasons) if reasons else "OK",
        })
        if ok:
            admitted[name] = score
    return pd.DataFrame(rows), list(admitted.keys())


def _cross_corr(a, b):
    """两个因子截面相关的均值（绝对值）。"""
    vals = []
    for t in a.index.intersection(b.index):
        x, y = a.loc[t], b.loc[t]
        valid = x.notna() & y.notna()
        if valid.sum() >= 2:
            vals.append(np.corrcoef(x[valid], y[valid])[0, 1])
    return float(np.nanmean(vals)) if vals else 0.0
