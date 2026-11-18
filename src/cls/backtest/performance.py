"""绩效分析：收益风险指标、成本归因、收益归因。"""
import numpy as np
import pandas as pd


def _annualize(total_return, n_days):
    """按 365 天年化（复利）。"""
    if n_days <= 0:
        return np.nan
    return (1 + total_return) ** (365 / n_days) - 1


def performance_metrics(snapshots):
    """收益与风险指标（按 365 天年化）。

    返回 dict：total_return / ann_return / ann_vol / sharpe / sortino /
    max_drawdown / dd_days / calmar / worst_day / worst_month
    """
    nav = snapshots["nav"]
    returns = nav.pct_change().dropna()
    n = len(returns)

    total_return = nav.iloc[-1] / nav.iloc[0] - 1 if len(nav) > 1 else 0.0
    ann_return = _annualize(total_return, n)
    ann_vol = returns.std() * np.sqrt(365) if len(returns) > 1 else np.nan
    sharpe = ann_return / ann_vol if ann_vol and ann_vol > 0 else np.nan

    downside = returns[returns < 0]
    dvol = downside.std() * np.sqrt(365) if len(downside) > 1 else np.nan
    sortino = ann_return / dvol if dvol and dvol > 0 else np.nan

    # 最大回撤 + 持续天数
    cum = nav / nav.iloc[0]
    running_max = cum.cummax()
    drawdown = cum / running_max - 1
    max_dd = float(drawdown.min())
    dd_days = 0
    if max_dd < 0:
        peak_idx = running_max.idxmax() if len(running_max) else nav.index[0]
        trough_idx = drawdown.idxmin() if len(drawdown) else nav.index[0]
        # 从峰到恢复（或期末）的天数
        after_trough = cum.loc[trough_idx:]
        recovered = after_trough[after_trough >= 1.0]
        end_idx = recovered.index[0] if len(recovered) else nav.index[-1]
        dd_days = int((end_idx - peak_idx).days)

    calmar = ann_return / abs(max_dd) if max_dd < 0 else np.nan
    worst_day = float(returns.min()) if len(returns) else np.nan
    monthly = nav.resample("ME").last().pct_change().dropna()
    worst_month = float(monthly.min()) if len(monthly) else np.nan

    return {
        "total_return": float(total_return),
        "ann_return": float(ann_return),
        "ann_vol": float(ann_vol) if not pd.isna(ann_vol) else np.nan,
        "sharpe": float(sharpe) if not pd.isna(sharpe) else np.nan,
        "sortino": float(sortino) if not pd.isna(sortino) else np.nan,
        "max_drawdown": max_dd,
        "dd_days": dd_days,
        "calmar": float(calmar) if not pd.isna(calmar) else np.nan,
        "worst_day": worst_day,
        "worst_month": worst_month,
        "n_days": int(n),
    }


def cost_attribution(snapshots):
    """成本归因：手续费/滑点/资金费率的累计与年化，及占毛收益比例。"""
    nav = snapshots["nav"]
    total_return = nav.iloc[-1] / nav.iloc[0] - 1 if len(nav) > 1 else 0.0
    n = len(nav)

    fee = snapshots["fee"].sum()
    slippage = snapshots["slippage"].sum()
    funding = snapshots["funding"].sum()
    gross_pnl = nav.iloc[-1] - nav.iloc[0] + fee + slippage - funding  # 还原成本前的盈亏

    def share(x):
        return x / gross_pnl if abs(gross_pnl) > 1e-9 else np.nan

    return {
        "gross_pnl": float(gross_pnl),
        "fee": float(fee),
        "slippage": float(slippage),
        "funding": float(funding),
        "fee_ann": float(_annualize(1 + fee / nav.iloc[0], n)),
        "slippage_ann": float(_annualize(1 + slippage / nav.iloc[0], n)),
        "funding_ann": float(_annualize(1 + funding / nav.iloc[0], n)),
        "fee_share": share(fee),
        "slippage_share": share(slippage),
        "funding_share": share(funding),
        "total_return": float(total_return),
        "avg_daily_turnover": float(snapshots["traded_notional"].mean() / nav.iloc[0]) if len(snapshots) else 0.0,
    }


def return_attribution(snapshots, btc_close=None):
    """收益归因：多头端/空头端各自收益；对 BTC 的 beta 和相关性。"""
    # 多头/空头市值变化近似各自收益（用市值差分 ÷ 期初净值）
    nav = snapshots["nav"]
    long_ret = snapshots["long_mv"].diff() / nav.shift(1)
    short_ret = snapshots["short_mv"].diff() / nav.shift(1)

    result = {
        "long_pnl": float(snapshots["long_mv"].iloc[-1] - snapshots["long_mv"].iloc[0]) if len(snapshots) else np.nan,
        "short_pnl": float(snapshots["short_mv"].iloc[-1] - snapshots["short_mv"].iloc[0]) if len(snapshots) else np.nan,
    }

    # 对 BTC 的 beta 和相关性（用净值收益 vs BTC 收益）
    if btc_close is not None and len(nav) > 1:
        strat_ret = nav.pct_change().dropna()
        btc_ret = btc_close.pct_change().reindex(strat_ret.index).dropna()
        common = strat_ret.index.intersection(btc_ret.index)
        if len(common) > 2:
            s = strat_ret.loc[common]
            b = btc_ret.loc[common]
            result["beta_to_btc"] = float(np.cov(s, b)[0, 1] / np.var(b))
            result["corr_to_btc"] = float(np.corrcoef(s, b)[0, 1])
            result["market_neutral"] = bool(abs(result["beta_to_btc"]) < 0.1)
    return result
