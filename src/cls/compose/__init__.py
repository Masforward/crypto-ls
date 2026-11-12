"""因子合成模块。"""
from .composer import (
    Composer,
    DecorrelatedEqualWeight,
    EqualWeight,
    ICIRWeighted,
    ICWeighted,
    MaxCompositeICIR,
)

__all__ = [
    "Composer",
    "EqualWeight",
    "ICWeighted",
    "ICIRWeighted",
    "MaxCompositeICIR",
    "DecorrelatedEqualWeight",
]
