"""pandas 练习：长宽转换、时序、截面、重采样、时间对齐（全部向量化）。"""
import pandas as pd

from src.cls.data.funding import get_funding_rates
from src.cls.data.klines import get_klines

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
           "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT"]

# ===== 拉数据 =====
end = pd.Timestamp.now(tz="UTC")
start = end - pd.Timedelta(days=30)

print("拉取 K 线...")
klines = get_klines(SYMBOLS, "1h", start, end)
print("K 线 shape:", klines.shape)

print("拉取资金费率...")
funding = get_funding_rates(SYMBOLS, start, end)
print("资金费率 shape:", funding.shape)

# ===== 练习 1：长宽转换 =====
wide = klines.pivot(index="open_time", columns="symbol", values="close")
long_again = wide.stack().reset_index()
long_again.columns = ["open_time", "symbol", "close"]
orig = (klines[["symbol", "open_time", "close"]]
        .sort_values(["symbol", "open_time"]).reset_index(drop=True))
back = long_again.sort_values(["symbol", "open_time"]).reset_index(drop=True)
print("\n[练习1] 与原数据一致?", orig["close"].equals(back["close"]))

# ===== 练习 2：时序计算 =====
klines["ret_24h"] = klines.groupby("symbol")["close"].pct_change(24)
klines["ret_1h"] = klines.groupby("symbol")["close"].pct_change(1)
klines["vol_7d"] = (klines.groupby("symbol")["ret_1h"]
                    .rolling(168).std()
                    .reset_index(level=0, drop=True))
print("\n[练习2] BTCUSDT 最近 3 行:")
print(klines[klines["symbol"] == "BTCUSDT"]
      [["open_time", "close", "ret_24h", "vol_7d"]].tail(3))

# ===== 练习 3：截面计算 =====
ret_wide = klines.pivot(index="open_time", columns="symbol",
                        values="close").pct_change(24)
ranked = ret_wide.rank(axis=1, ascending=False)
t = ranked.dropna(how="all").index[100]
row = ranked.loc[t]
print(f"\n[练习3] 截面排名 ({t}):")
print("  前 3 名:", row[row <= 3].index.tolist())
print("  后 3 名:", row[row >= len(SYMBOLS) - 2].index.tolist())

# ===== 练习 4：重采样（1h → 4h 和日线）=====
btc = klines[klines["symbol"] == "BTCUSDT"].set_index("open_time")

AGG = {"open": "first", "high": "max", "low": "min",
       "close": "last", "volume": "sum"}

btc_4h = btc.resample("4h").agg(AGG)
btc_1d = btc.resample("1D").agg(AGG)

print(f"\n[练习4] 重采样：1h 有 {len(btc)} 根, 4h 有 {len(btc_4h)} 根, 日线有 {len(btc_1d)} 根")
print(btc_4h[["open", "high", "low", "close", "volume"]].head(3))

# ===== 练习 5：merge_asof 时间对齐 =====
fund_btc = funding[funding["symbol"] == "BTCUSDT"].sort_values("funding_time")
kline_btc = klines[klines["symbol"] == "BTCUSDT"].sort_values("open_time")

merged = pd.merge_asof(
    kline_btc,
    fund_btc[["funding_time", "funding_rate"]],
    left_on="open_time",
    right_on="funding_time",
    direction="backward",   # 只匹配 <= open_time 的最近费率（已结算）
)

print("\n[练习5] merge_asof 对齐（前 9 根 K 线 + 最近已结算费率）:")
print(merged[["open_time", "funding_time", "funding_rate"]].head(9))
