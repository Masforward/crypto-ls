"""绩效图表：净值与回撤、滚动夏普、分月收益表（输出到一个 PDF）。"""
import os

import numpy as np
import pandas as pd


def save_charts(snapshots, out_dir):
    """画 3 张图（净值+回撤 / 滚动夏普 / 分月收益），存到一个 PDF。返回 pdf 路径。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "performance.pdf")
    nav = snapshots["nav"]
    returns = nav.pct_change().dropna()

    with PdfPages(pdf_path) as pdf:
        # 图1：净值 + 回撤（双轴）
        fig, ax1 = plt.subplots(figsize=(10, 5))
        cum = nav / nav.iloc[0]
        ax1.plot(nav.index, cum, label="NAV", color="tab:blue", lw=1.5)
        ax1.set_ylabel("NAV (normalized)")
        ax1.set_xlabel("Time")
        running_max = cum.cummax()
        drawdown = cum / running_max - 1
        ax2 = ax1.twinx()
        ax2.fill_between(nav.index, drawdown, 0, color="tab:red", alpha=0.3, label="Drawdown")
        ax2.set_ylabel("Drawdown")
        ax1.legend(loc="upper left")
        ax2.legend(loc="upper right")
        ax1.set_title("NAV and Drawdown")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 图2：滚动夏普（30 天）
        fig, ax = plt.subplots(figsize=(10, 5))
        roll_mean = returns.rolling(30).mean()
        roll_std = returns.rolling(30).std()
        roll_sharpe = roll_mean / roll_std * np.sqrt(365)
        ax.plot(roll_sharpe.index, roll_sharpe, color="tab:green", lw=1.2)
        ax.axhline(0, color="gray", lw=0.8, ls="--")
        ax.set_title("Rolling Sharpe (30d)")
        ax.set_ylabel("Sharpe (annualized)")
        ax.set_xlabel("Time")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # 图3：分月收益柱状图
        fig, ax = plt.subplots(figsize=(10, 5))
        monthly = nav.resample("ME").last().pct_change().dropna()
        colors = ["tab:red" if v < 0 else "tab:blue" for v in monthly]
        ax.bar(monthly.index.astype(str), monthly.values, color=colors)
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_title("Monthly Returns")
        ax.set_ylabel("Return")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    return pdf_path


def monthly_returns_table(snapshots):
    """分月收益表（用于报告）。"""
    nav = snapshots["nav"]
    monthly = nav.resample("ME").last().pct_change().dropna()
    monthly.index = monthly.index.to_period("M")
    monthly.name = "return"
    return monthly
