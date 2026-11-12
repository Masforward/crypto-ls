"""第五周：一条命令从数据跑到目标权重和诊断报告。

用法：
  python -m src.cls.portfolio.run_week5                     # 用默认 config.yaml
  python -m src.cls.portfolio.run_week5 --config config.yaml --out week5_output

流程：数据 → 因子分数 → 预处理 → 合成 → 组合 → 换手控制 → 权重 + 诊断。
"""
import argparse
import os

import pandas as pd
import yaml

from ..data import list_symbols
from ..signal import (
    Amplitude7d,
    MaxDailyGain,
    Momentum7d,
    OneDayReversal,
    ReturnSkew7d,
    TakerBuyRatio,
    Volatility7d,
    VolumeSurge,
    compute_scores,
    preprocess,
)
from ..signal.evaluate import close_panel, compute_forward_returns, rankic_series
from ..signal.pipeline import compute_size
from ..signal.risk import compute_risk
from ..compose import EqualWeight, ICIRWeighted, ICWeighted
from .builder import InverseVolWeighted, QuantileLongShort, ScoreWeighted
from .rebalance import turnover_control

FACTORS = [
    Momentum7d(), OneDayReversal(), Volatility7d(), VolumeSurge(),
    TakerBuyRatio(), MaxDailyGain(), Amplitude7d(), ReturnSkew7d(),
]

COMPOSERS = {"equal_weight": EqualWeight, "ic_weighted": ICWeighted, "icir_weighted": ICIRWeighted}
BUILDERS = {"quantile_long_short": QuantileLongShort,
            "score_weighted": ScoreWeighted, "inverse_vol": InverseVolWeighted}


def main(argv=None):
    parser = argparse.ArgumentParser(description="第五周：一条命令跑合成 + 组合")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="week5_output")
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
    if d.get("symbols", 0) > 0:
        symbols = symbols.head(d["symbols"])
    symbols = symbols.tolist()
    start, end = d["start"], d["end"]
    print(f"币种数 {len(symbols)}，区间 {start} ~ {end}")

    # ② 因子分数表 + 预处理（规模中性）
    raw = {f.name: compute_scores(f, symbols, start, end, cache=False)[f.name] for f in FACTORS}
    size = compute_size(symbols, start, end)
    processed = {f.name: preprocess(raw[f.name], f.direction, size=size) for f in FACTORS}

    # ③ 合成（历史 RankIC 序列供 IC/ICIR 加权用）
    close = close_panel(symbols, start, end)
    fwd = compute_forward_returns(close, 1)
    ic_history = {name: rankic_series(s, fwd) for name, s in processed.items()}

    composer_cls = COMPOSERS[cc["method"]]
    composer = composer_cls(
        lookback=cc.get("lookback", 60),
        holdback=cc.get("holdback", 2),
        allow_negative=cc.get("allow_negative", False),
        cap=cc.get("cap"),
    )
    composite, factor_weights = composer.compose(processed, ic_history)
    print(f"合成方法 {cc['method']}，综合分数表 {composite.shape}")

    # ④ 风险输入
    risk = compute_risk(symbols, start, end)

    # ⑤ 组合
    builder_cls = BUILDERS[pc["method"]]
    builder = builder_cls()
    weights, diagnostics = builder.build(composite, risk=risk, config=pc)

    # ⑥ 换手控制
    final_weights, turnovers = turnover_control(weights, rc)

    # ⑦ 输出
    os.makedirs(args.out, exist_ok=True)
    final_weights.to_csv(os.path.join(args.out, "weights.csv"), encoding="utf-8-sig")
    diagnostics.to_csv(os.path.join(args.out, "diagnostics.csv"), encoding="utf-8-sig")
    factor_weights.to_csv(os.path.join(args.out, "factor_weights.csv"), encoding="utf-8-sig")
    pd.DataFrame({"turnover": turnovers}).to_csv(os.path.join(args.out, "turnover.csv"), encoding="utf-8-sig")

    print()
    print("=== 诊断统计（均值） ===")
    print(f"平均持仓数      : 多 {diagnostics['n_long'].mean():.1f} / 空 {diagnostics['n_short'].mean():.1f}")
    print(f"平均总杠杆      : {diagnostics['gross'].mean():.3f}")
    print(f"平均换手率      : {turnovers.mean():.3f}")
    print(f"美元中性满足比例: {(diagnostics['dollar_neutral_ok']).mean():.1%}")
    print(f"总杠杆满足比例  : {(diagnostics['gross_ok']).mean():.1%}")
    print(f"单币上限满足比例: {(diagnostics['max_weight_ok']).mean():.1%}")
    print(f"输出目录        : {args.out}")


if __name__ == "__main__":
    main()
