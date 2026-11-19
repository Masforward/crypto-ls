"""回测入口：指定因子池 → 合成 → 组合 → 回测，输出绩效 + 图表。

用法：
  python -m src.cls.signal.run_backtest                    # 默认 = 旧 8 因子 + 准入的新因子
  python -m src.cls.signal.run_backtest --factors momentum_7d,vol_price_corr
  python -m src.cls.signal.run_backtest --factors all      # 全部 16 因子
  python -m src.cls.signal.run_backtest --symbols 30 --out out_dir

默认行为：先跑准入流程（新 8 因子对旧 8 因子做增量检验），因子池 = 旧 8 + 准入因子；
--factors 手动指定时覆盖（all = 全部 16 因子）。合成/组合/调仓读 config.yaml。
"""
import argparse
import os

import pandas as pd
import yaml

from ..data import list_symbols
from ..backtest.charts import save_charts
from ..backtest.performance import cost_attribution, performance_metrics
from . import compute_scores, preprocess
from .admission import run_admission
from .evaluate import close_panel, compute_forward_returns, rankic_series
from .pipeline import compute_size
from .risk import compute_risk
from .run_week6 import BASE_FACTORS, NEW_FACTORS, compose_and_backtest, open_panel

ALL_FACTORS = BASE_FACTORS + NEW_FACTORS
FACTOR_REGISTRY = {f.name: f for f in ALL_FACTORS}


def main(argv=None):
    parser = argparse.ArgumentParser(description="回测：指定因子池 → 合成 → 组合 → 回测")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="backtest_output")
    parser.add_argument("--symbols", type=int, default=None,
                        help="覆盖 config 的币种数（0=全部）")
    parser.add_argument("--factors", default=None,
                        help="因子名逗号分隔，或 all；默认 = 旧 8 + 准入因子")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    d, cc, pc, rc = cfg["data"], cfg["compose"], cfg["portfolio"], cfg.get("rebalance", {})

    # 选币
    df = list_symbols()
    symbols = df[df["start"] <= pd.Timestamp("2025-01-01", tz="UTC")]["symbol"]
    n = args.symbols if args.symbols is not None else d.get("symbols", 0)
    if n > 0:
        symbols = symbols.head(n)
    symbols = symbols.tolist()
    start, end = d["start"], d["end"]

    close = close_panel(symbols, start, end)
    open_ = open_panel(symbols, start, end)
    size = compute_size(symbols, start, end)
    fwd = compute_forward_returns(close, 1)
    risk = compute_risk(symbols, start, end)

    # 确定因子池
    if args.factors == "all":
        pool_factors = ALL_FACTORS
        pool_label = "全部 16 因子"
    elif args.factors:
        names = [x.strip() for x in args.factors.split(",") if x.strip()]
        pool_factors = [FACTOR_REGISTRY[n] for n in names if n in FACTOR_REGISTRY]
        missing = [n for n in names if n not in FACTOR_REGISTRY]
        if missing:
            print(f"警告：未知因子 {missing} 被忽略")
        pool_label = f"手动指定 {[f.name for f in pool_factors]}"
    else:
        pool_factors = None
        pool_label = "旧 8 + 准入因子"

    # 算分数表 + 预处理
    if pool_factors is not None:
        raw = {f.name: compute_scores(f, symbols, start, end, cache=False)[f.name]
               for f in pool_factors}
        processed = {f.name: preprocess(raw[f.name], f.direction, size=size)
                     for f in pool_factors}
    else:
        # 默认：准入流程，因子池 = 旧 8 + 准入新因子
        raw_all = {f.name: compute_scores(f, symbols, start, end, cache=False)[f.name]
                   for f in ALL_FACTORS}
        proc_all = {f.name: preprocess(raw_all[f.name], f.direction, size=size)
                    for f in ALL_FACTORS}
        base = {f.name: proc_all[f.name] for f in BASE_FACTORS}
        new = {f.name: proc_all[f.name] for f in NEW_FACTORS}
        raw_new = {f.name: raw_all[f.name] for f in NEW_FACTORS}
        admission_df, admitted = run_admission(new, close, raw_scores=raw_new,
                                               initial_admitted=base)
        print(f"准入因子: {admitted if admitted else '无'}")
        processed = dict(base)
        processed.update({n: proc_all[n] for n in admitted})

    print(f"币种 {len(symbols)}，区间 {start} ~ {end}")
    print(f"因子池 ({len(processed)}): {list(processed.keys())} ({pool_label})")
    print(f"合成 {cc['method']} / 组合 {pc['method']} / 调仓 {rc.get('rebalance_freq', 1)} 天")

    # 回测
    ic_history = {n: rankic_series(s, fwd) for n, s in processed.items()}
    m, snap, final_w = compose_and_backtest(processed, ic_history, close, open_,
                                            risk, cc, pc, rc)

    # 输出
    os.makedirs(args.out, exist_ok=True)
    print("\n=== 绩效 ===")
    for k in ["total_return", "ann_return", "sharpe", "sortino", "max_drawdown", "calmar", "worst_day"]:
        v = m.get(k, float("nan"))
        print(f"  {k:14s}: {v:.4f}" if isinstance(v, float) and not pd.isna(v) else f"  {k:14s}: {v}")
    print(f"  现金不足     : {m.get('cash_shortfalls', 0)} 次")

    c = cost_attribution(snap)
    print("\n=== 成本归因 ===")
    for k in ["fee", "slippage", "funding", "avg_daily_turnover"]:
        v = c.get(k, float("nan"))
        print(f"  {k:14s}: {v:.4f}" if isinstance(v, float) and not pd.isna(v) else f"  {k:14s}: {v}")

    final_w.to_csv(os.path.join(args.out, "weights.csv"), encoding="utf-8-sig")
    save_charts(snap, args.out)
    print(f"\n输出目录: {args.out}")


if __name__ == "__main__":
    main()
