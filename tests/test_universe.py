"""测试 universe 的纯函数（不联网）。"""
import pandas as pd

from src.cls.data.universe import _filter_universe


def _ms(ts):
    return int(pd.Timestamp(ts, tz="UTC").timestamp() * 1000)


def test_filter_universe_as_of_before_delist():
    symbols = [
        {"symbol": "BTCUSDT", "quoteAsset": "USDT", "contractType": "PERPETUAL",
         "status": "TRADING", "onboardDate": _ms("2019-08-14"),
         "deliveryDate": _ms("2100-01-01")},
        # 已下架的币，但 as_of 在下架之前 → 应该保留（补幸存者偏差）
        {"symbol": "OMGUSDT", "quoteAsset": "USDT", "contractType": "PERPETUAL",
         "status": "SETTLING", "onboardDate": _ms("2020-07-02"),
         "deliveryDate": _ms("2025-01-31")},
        {"symbol": "BTCUSDC", "quoteAsset": "USDC", "contractType": "PERPETUAL",
         "status": "TRADING", "onboardDate": _ms("2019-08-14"),
         "deliveryDate": _ms("2100-01-01")},
    ]
    as_of_ms = _ms("2024-06-01")   # OMGUSDT 在 2024-06 还在交易
    rows = _filter_universe(symbols, as_of_ms)
    assert [r["symbol"] for r in rows] == ["BTCUSDT", "OMGUSDT"]


def test_filter_universe_as_of_after_delist():
    symbols = [
        {"symbol": "BTCUSDT", "quoteAsset": "USDT", "contractType": "PERPETUAL",
         "status": "TRADING", "onboardDate": _ms("2019-08-14"),
         "deliveryDate": _ms("2100-01-01")},
        {"symbol": "OMGUSDT", "quoteAsset": "USDT", "contractType": "PERPETUAL",
         "status": "SETTLING", "onboardDate": _ms("2020-07-02"),
         "deliveryDate": _ms("2025-01-31")},
    ]
    as_of_ms = _ms("2025-06-01")   # OMGUSDT 在 2025-01 已下架
    rows = _filter_universe(symbols, as_of_ms)
    assert [r["symbol"] for r in rows] == ["BTCUSDT"]
