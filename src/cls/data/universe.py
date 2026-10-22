"""币种池：get_universe（含已下架币，用 onboardDate/deliveryDate 判断 as_of 当天可交易）。"""
import pandas as pd

from .client import request


def _filter_universe(symbols, as_of_ms):
    """纯函数：筛 USDT 永续，且在 as_of 那天已上市、未下架（可离线测试）。

    可交易判断：onboardDate <= as_of < deliveryDate
    - 已下架的币（deliveryDate 是过去）在 as_of 之前仍会被正确纳入，
      从而消除"只用当前 TRADING 币"带来的幸存者偏差。
    """
    rows = []
    for s in symbols:
        if (s.get("quoteAsset") == "USDT"
                and s.get("contractType") == "PERPETUAL"
                and s.get("onboardDate", 0) <= as_of_ms
                and s.get("deliveryDate", 0) > as_of_ms):
            rows.append({
                "symbol": s["symbol"],
                "onboardDate": s["onboardDate"],
                "deliveryDate": s["deliveryDate"],
            })
    return rows


def get_universe(as_of=None):
    """返回 as_of 当天可交易的 USDT 永续合约，含上市/下架日期。

    as_of : pd.Timestamp | None —— 默认现在（UTC）。
    返回列：symbol, onboardDate, deliveryDate（均为 UTC 时间）。
    """
    if as_of is None:
        as_of = pd.Timestamp.now(tz="UTC")
    as_of_ms = int(as_of.timestamp() * 1000)

    resp = request("/fapi/v1/exchangeInfo")
    symbols = resp.json()["symbols"]

    rows = _filter_universe(symbols, as_of_ms)
    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ["onboardDate", "deliveryDate"]:
            df[col] = pd.to_datetime(df[col], unit="ms", utc=True)
    return df
