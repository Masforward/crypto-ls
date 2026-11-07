"""一条命令生成全部因子的分数表和评价报告。

用法：
  python -m src.cls.signal.run_report                          # 全量（2025 全年，全部币）
  python -m src.cls.signal.run_report --symbols 100            # 只用前 100 个币（快速测试）
  python -m src.cls.signal.run_report --start 2025-06-01 --end 2025-12-31 --out my_report

产出（默认在 report_output/）：
  report.pdf       4 张图（RankIC 累积 / 分月 / 衰减 / 相关矩阵）
  summary.csv      汇总表（每个因子一行，中性化前后对比 + 结论）
  correlation.csv  因子相关性矩阵
"""
import argparse

import pandas as pd

from ..data import list_symbols
from .factor import (
    Amplitude7d,
    MaxDailyGain,
    Momentum7d,
    OneDayReversal,
    ReturnSkew7d,
    TakerBuyRatio,
    Volatility7d,
    VolumeSurge,
)
from .report import generate_report, save_figures, save_report

FACTORS = [
    Momentum7d(), OneDayReversal(), Volatility7d(), VolumeSurge(),
    TakerBuyRatio(), MaxDailyGain(), Amplitude7d(), ReturnSkew7d(),
]


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成全部因子的分数表和评价报告")
    parser.add_argument("--start", default="2025-01-01", help="评价区间起点（默认 2025-01-01）")
    parser.add_argument("--end", default="2025-12-31", help="评价区间终点（默认 2025-12-31）")
    parser.add_argument("--symbols", type=int, default=0,
                        help="币种数量（0=全部 2025 年初已上市的币）")
    parser.add_argument("--out", default="report_output", help="输出目录")
    args = parser.parse_args(argv)

    # 选币：2025 年初已上市（避免新币无历史数据报错）
    df = list_symbols()
    symbols = df[df["start"] <= pd.Timestamp("2025-01-01", tz="UTC")]["symbol"]
    if args.symbols > 0:
        symbols = symbols.head(args.symbols)
    symbols = symbols.tolist()
    print(f"币种数：{len(symbols)}，评价区间：{args.start} ~ {args.end}")

    summary, details = generate_report(FACTORS, symbols, args.start, args.end)
    save_report(summary, details, args.out)
    pdf = save_figures(summary, details, args.out)

    print()
    print(summary.to_string(index=False))
    print()
    print(f"报告已生成：{pdf}")


if __name__ == "__main__":
    main()
