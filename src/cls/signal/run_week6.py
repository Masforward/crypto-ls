"""第六周：一条命令跑因子扩展准入 → 合成 → 组合 → 回测 → 对比。

用法：
  python -m src.cls.signal.run_week6                                    # 用 config.yaml
  python -m src.cls.signal.run_week6 --config config.yaml --out week6_output
  python -m src.cls.signal.run_week6 --factors vol_price_corr,idio_vol  # 只加指定因子

合成/组合/调仓方法读 config.yaml（compose.method / portfolio.method / rebalance），
和第五周一致；额外因子默认 = 所有准入因子，可用 --factors 手动指定子集。
"""
import argparse
import os

import pandas as pd
import yaml

from ..data import list_symbols
from ..backtest.charts import save_charts
from ..backtest.cost import FixedCost
from ..backtest.engine import BacktestEngine
from ..backtest.performance import performance_metrics
from ..compose import (DecorrelatedEqualWeight, EqualWeight, ICIRWeighted,
                       ICWeighted, MaxCompositeICIR)
from ..portfolio.builder import (InverseVolWeighted, MeanVariance,
                                 QuantileLongShort, ScoreWeighted)
from ..portfolio.rebalance import turnover_control
from . import (
    Amihud, Amplitude7d, BtcBeta, IdioVol, IntradayRangePos, MaxDailyGain,
    Momentum7d, OneDayReversal, OvernightReturn, RealizedSkew30d, ReturnSkew7d,
    TakerBuyRatio, UpDownVolRatio, VolPriceCorr, Volatility7d, VolumeSurge,
    compute_scores, preprocess,
)
from .admission import run_admission
from .evaluate import close_panel, compute_forward_returns, rankic_series
from .pipeline import _resample, compute_size
from .risk import compute_risk

BASE_FACTORS = [
    Momentum7d(), OneDayReversal(), Volatility7d(), VolumeSurge(),
    TakerBuyRatio(), MaxDailyGain(), Amplitude7d(), ReturnSkew7d(),
]
NEW_FACTORS = [
    OvernightReturn(), IntradayRangePos(), RealizedSkew30d(), UpDownVolRatio(),
    VolPriceCorr(), Amihud(), BtcBeta(), IdioVol(),
]

COMPOSERS = {
    "equal_weight": EqualWeight, "ic_weighted": ICWeighted,
    "icir_weighted": ICIRWeighted, "max_composite_icir": MaxCompositeICIR,
    "decorrelated_equal_weight": DecorrelatedEqualWeight,
}
BUILDERS = {
    "quantile_long_short": QuantileLongShort, "score_weighted": ScoreWeighted,
    "inverse_vol": InverseVolWeighted, "mean_variance": MeanVariance,
}


def open_panel(symbols, start, end, interval="5m", data_dir=None):
    """日线开盘价面板（时间 × 币种），回测成交价用下一根开盘价。"""
    from ..data import load_klines
    df = load_klines(symbols, start, end, interval, data_dir=data_dir)
    daily = _resample(df, "1d")
    return daily.pivot(index="open_time", columns="symbol", values="open")


def compose_and_backtest(processed, ic_history, close, open_, risk, cc, pc, rc):
    """按 config 的合成/组合/调仓方法跑回测，返回绩效指标 dict。"""
    composer_cls = COMPOSERS[cc["method"]]
    composer = composer_cls(
        lookback=cc.get("lookback", 60),
        holdback=cc.get("holdback", 2),
        allow_negative=cc.get("allow_negative", False),
        cap=cc.get("cap"),
    )
    composite, _ = composer.compose(processed, ic_history)

    builder_cls = BUILDERS[pc["method"]]
    weights, _ = builder_cls().build(composite, risk=risk, config=pc)
    final_w, _ = turnover_control(weights, rc)

    eng = BacktestEngine({"initial_capital": pc.get("capital", 1e6),
                          "cash_buffer_ratio": pc.get("cash_buffer_ratio", 0.01)},
                         cost_model=FixedCost(pc.get("fee_rate", 0.001),
                                              pc.get("slippage_bps", 2.0)))
    snap, fills, _, shortfalls = eng.run(final_w, close, open_)
    m = performance_metrics(snap)
    m["cash_shortfalls"] = len(shortfalls)
    return m, snap, final_w


def main(argv=None):
    parser = argparse.ArgumentParser(description="第六周：因子扩展准入 + 合成 + 组合 + 回测")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="week6_output")
    parser.add_argument("--symbols", type=int, default=None,
                        help="覆盖 config 的币种数（0=全部）")
    parser.add_argument("--factors", default=None,
                        help="额外因子子集（逗号分隔），默认=所有准入因子")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    d = cfg["data"]
    cc = cfg["compose"]
    pc = cfg["portfolio"]
    rc = cfg.get("rebalance", {})

    # ① 选币
    df = list_symbols()
    symbols = df[df["start"] <= pd.Timestamp("2025-01-01", tz="UTC")]["symbol"]
    n_symbols = args.symbols if args.symbols is not None else d.get("symbols", 0)
    if n_symbols > 0:
        symbols = symbols.head(n_symbols)
    symbols = symbols.tolist()
    start, end = d["start"], d["end"]
    print(f"币种数 {len(symbols)}，区间 {start} ~ {end}")
    print(f"合成 {cc['method']} / 组合 {pc['method']} / 调仓 {rc.get('rebalance_freq', 1)} 天")

    # ② 分数表 + 预处理
    all_factors = BASE_FACTORS + NEW_FACTORS
    raw = {f.name: compute_scores(f, symbols, start, end, cache=False)[f.name]
           for f in all_factors}
    size = compute_size(symbols, start, end)
    processed = {f.name: preprocess(raw[f.name], f.direction, size=size) for f in all_factors}

    base_processed = {f.name: processed[f.name] for f in BASE_FACTORS}
    new_processed = {f.name: processed[f.name] for f in NEW_FACTORS}

    close = close_panel(symbols, start, end)
    open_ = open_panel(symbols, start, end)
    fwd = compute_forward_returns(close, 1)

    # ③ 准入流程（新因子对旧 8 因子做增量检验）
    print("\n=== 准入流程 ===")
    raw_new = {f.name: raw[f.name] for f in NEW_FACTORS}
    admission_df, admitted = run_admission(new_processed, close, raw_scores=raw_new,
                                           initial_admitted=base_processed)
    print(admission_df[["factor", "mean_ic", "icir", "t", "resid_ic", "admitted", "reason"]]
          .round(4).to_string(index=False))
    print(f"\n自动准入因子: {admitted if admitted else '无'}")

    # ④ 确定额外因子子集（--factors 覆盖默认）
    if args.factors:
        selected = [x.strip() for x in args.factors.split(",") if x.strip()]
        extra = {n: new_processed[n] for n in selected if n in new_processed}
        missing = [n for n in selected if n not in new_processed]
        if missing:
            print(f"警告：未知因子 {missing} 被忽略")
        print(f"手动选择额外因子: {list(extra.keys())}")
    else:
        extra = {n: new_processed[n] for n in admitted}
        print(f"使用自动准入因子: {list(extra.keys())}")

    risk = compute_risk(symbols, start, end)

    # ⑤ 回测：基线（旧 8）vs 扩展（旧 8 + 额外因子）
    base_ic = {n: rankic_series(s, fwd) for n, s in base_processed.items()}
    m_base, snap_base, _ = compose_and_backtest(base_processed, base_ic, close, open_,
                                                risk, cc, pc, rc)

    extended = dict(base_processed)
    extended.update(extra)
    ext_ic = {n: rankic_series(s, fwd) for n, s in extended.items()}
    m_ext, snap_ext, _ = compose_and_backtest(extended, ext_ic, close, open_,
                                              risk, cc, pc, rc)

    # ⑥ 对比 + 落盘
    print("\n=== 回测对比 ===")
    cmp = pd.DataFrame({"baseline_8f": m_base, "extended": m_ext}).T[
        ["total_return", "ann_return", "sharpe", "max_drawdown", "cash_shortfalls"]]
    print(cmp.round(4).to_string())

    os.makedirs(args.out, exist_ok=True)
    cmp.to_csv(os.path.join(args.out, "comparison.csv"), encoding="utf-8-sig")
    admission_df.to_csv(os.path.join(args.out, "admission.csv"), index=False, encoding="utf-8-sig")
    save_charts(snap_ext, args.out)
    print(f"\n输出目录: {args.out}")


if __name__ == "__main__":
    main()
