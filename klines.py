import requests
import pandas as pd

r = requests.get(
    "https://fapi.binance.com/fapi/v1/klines",
    params={"symbol": "BTCUSDT", "interval": "1h", "limit": 1500},
    timeout=30,
)
print(r.status_code)
print("已用权重:", r.headers.get("X-MBX-USED-WEIGHT-1M"))

data = r.json()
print("K 线根数:", len(data))

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]

df = pd.DataFrame(data, columns=COLUMNS)

df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
    df[col] = df[col].astype(float)

diff = df["open_time"].diff()          # 错位相减，第一行会是 NaT
diff = diff.dropna()                    # 去掉第一行的 NaT
not_1h = (diff != pd.Timedelta(hours=1)).sum()
print(type(not_1h))
print("\n缺口数（相邻间隔 ≠ 1 小时）:", not_1h)

if not_1h > 0:
    print("异常的间隔:")
    print(diff[diff != pd.Timedelta(hours=1)])

dup = df["open_time"].duplicated().sum()
print("重复的 open_time 个数:", dup)


now = pd.Timestamp.now(tz="UTC")

if df["close_time"].iloc[-1] > now:
    df = df.iloc[:-1]
    print("最后一根未收盘，已删除，剩余根数:", len(df))
else:
    print("最后一根已收盘，保留")