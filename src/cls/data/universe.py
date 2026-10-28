"""币种池：get_universe（含已下架币，用 onboardDate/deliveryDate 判断 as_of 当天可交易）。"""
import pandas as pd

from .client import request


def _filter_universe(symbols, as_of_ms, contract_type="PERPETUAL", quote_asset="USDT"):
    #输入未加工的返回文本以及查询时间，合约类型和币种，筛选返回当时市场上的交易币种。
    rows = []
    for s in symbols:
        if (s.get("quoteAsset") == quote_asset
                and s.get("contractType") == contract_type
                and s.get("status") != "PENDING_TRADING"   # 排除待交易币（还没上市交易，无数据）；保留 SETTLING（下架前有历史数据，消除幸存者偏差）
                and s.get("onboardDate", 0) <= as_of_ms
                and s.get("deliveryDate", 0) > as_of_ms):
            rows.append({
                "symbol": s["symbol"],
                "onboardDate": s["onboardDate"],
                "deliveryDate": s["deliveryDate"],
            })
    return rows


def get_universe(as_of=None, contract_type="PERPETUAL", quote_asset="USDT"):
    #输入查询时间，返回dataframe，带有合约名，上市时间，退市时间。
    #contract_type：合约类型（PERPETUAL 永续 / CURRENT_QUARTER 当季 / NEXT_QUARTER 次季）。
    #quote_asset：交易币种（USDT / USDC 等）。
    if as_of is None:
        as_of = pd.Timestamp.now(tz="UTC")
    as_of_ms = int(as_of.timestamp() * 1000)

    resp = request("/fapi/v1/exchangeInfo")
    symbols = resp.json()["symbols"]

    rows = _filter_universe(symbols, as_of_ms, contract_type, quote_asset)
    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ["onboardDate", "deliveryDate"]:
            df[col] = pd.to_datetime(df[col], unit="ms", utc=True)
    return df
