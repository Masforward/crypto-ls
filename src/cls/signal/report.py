"""信号模块：评价报告（汇总表 + 4 张图 + 每个因子一句结论）。

只评价因子预测力，不构建组合。只用 2025 年数据（样本内），2026 留作样本外。
"""
import os

import numpy as np
import pandas as pd

from .evaluate import (
    close_panel,
    coverage_stats,
    evaluate,
    factor_correlation,
    factor_stability,
    monthly_rankic,
)
from .pipeline import compute_scores, compute_size
from .preprocess import preprocess

HORIZON_MAIN = 1  # 汇总表主用持有期 1 的统计量


def _conclusion(rankic_mean, icir):
    """根据 RankIC 均值和 ICIR 给一句结论（继续/观察/放弃）。"""
    if abs(rankic_mean) < 0.01:            # 几乎无预测力
        return "放弃"
    if icir >= 0.3:                        # 方向对且稳定
        return "继续"
    return "观察"                          # 方向对但不稳定


def generate_report(factors, symbols, start, end, data_dir=None):
    """生成全部因子的评价报告。

    factors : 因子实例列表
    symbols : 币种列表
    start, end : 评价区间（应为 2025 年，样本内）

    返回：
      summary : 汇总表（DataFrame，每个因子一行，中性化前后各一列）
      details : 每个因子的完整评价结果（dict）
    """
    close = close_panel(symbols, start, end, data_dir=data_dir)
    size = compute_size(symbols, start, end, data_dir=data_dir)

    rows = []
    details = {}
    scores = {}  # 预处理后（中性化后）的分数表，用于相关性矩阵

    for factor in factors:
        raw = compute_scores(factor, symbols, start, end, cache=False)[factor.name]

        # 中性化前（不传 size）与中性化后（传 size）
        pre = preprocess(raw, factor.direction)
        post = preprocess(raw, factor.direction, size=size)
        scores[factor.name] = post

        ev_pre = evaluate(pre, close)
        ev_post = evaluate(post, close)

        rc_pre = ev_pre["rankic"][HORIZON_MAIN]["mean"]
        rc_post = ev_post["rankic"][HORIZON_MAIN]["mean"]
        icir_pre = ev_pre["rankic"][HORIZON_MAIN]["icir"]
        icir_post = ev_post["rankic"][HORIZON_MAIN]["icir"]

        rows.append({
            "factor": factor.name,
            "方向": factor.direction,
            "RankIC均值_前": round(rc_pre, 4) if not np.isnan(rc_pre) else np.nan,
            "RankIC均值_后": round(rc_post, 4) if not np.isnan(rc_post) else np.nan,
            "ICIR_前": round(icir_pre, 3) if not np.isnan(icir_pre) else np.nan,
            "ICIR_后": round(icir_post, 3) if not np.isnan(icir_post) else np.nan,
            "结论": _conclusion(rc_post, icir_post),
        })

        details[factor.name] = {
            "pre": ev_pre, "post": ev_post,
            "monthly_rankic": monthly_rankic(post, close, HORIZON_MAIN),
            "stability": factor_stability(post),
            "coverage": coverage_stats(post, raw),
        }

    summary = pd.DataFrame(rows)
    details["_correlation"] = factor_correlation(scores)
    return summary, details


def save_report(summary, details, out_dir):
    """保存汇总表（csv）和相关性矩阵（csv）。图在 save_figures 里。"""
    os.makedirs(out_dir, exist_ok=True)
    summary.to_csv(os.path.join(out_dir, "summary.csv"), index=False)
    details["_correlation"].round(3).to_csv(os.path.join(out_dir, "correlation.csv"))
    return out_dir
