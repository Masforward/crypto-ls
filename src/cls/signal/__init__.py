"""信号模块：因子与流水线。

对外接口：
  Factor —— 因子基类（继承它写新因子）
  6 个必做因子：Momentum7d / OneDayReversal / Volatility7d / VolumeSurge / TakerBuyRatio / MaxDailyGain
  compute_scores —— 流水线：输入因子 + 币种 + 时间，输出分数表（时间 × 币种）
"""
from .factor import (
    Amihud,
    Amplitude7d,
    BtcBeta,
    Factor,
    IdioVol,
    IntradayRangePos,
    MaxDailyGain,
    Momentum7d,
    OneDayReversal,
    OvernightReturn,
    RealizedSkew30d,
    ReturnSkew7d,
    TakerBuyRatio,
    UpDownVolRatio,
    Volatility7d,
    VolPriceCorr,
    VolumeSurge,
)
from .pipeline import compute_scores
from .preprocess import preprocess
from .report import generate_report, save_figures, save_report

__all__ = [
    "Factor",
    "Momentum7d",
    "OneDayReversal",
    "Volatility7d",
    "VolumeSurge",
    "TakerBuyRatio",
    "MaxDailyGain",
    "Amplitude7d",
    "ReturnSkew7d",
    "OvernightReturn",
    "IntradayRangePos",
    "RealizedSkew30d",
    "UpDownVolRatio",
    "VolPriceCorr",
    "Amihud",
    "BtcBeta",
    "IdioVol",
    "compute_scores",
    "preprocess",
    "generate_report",
    "save_report",
    "save_figures",
]
