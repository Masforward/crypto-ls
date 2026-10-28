"""币安数据层：本地 K 线数据库（采集、存储、校验、读取）。

对外只暴露五个公开函数（模块封闭性）：
    load_klines, load_panel, list_symbols, quality_report, update_klines
其余函数、类、常量以下划线开头，视为内部实现。
"""
from .backfill import update_klines
from .reader import load_klines, load_panel, list_symbols, quality_report

__all__ = [
    "load_klines",
    "load_panel",
    "list_symbols",
    "quality_report",
    "update_klines",
]
