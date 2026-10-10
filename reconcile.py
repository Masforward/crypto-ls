import requests
import hashlib
import pandas as pd

SYMBOL = "BTCUSDT"
INTERVAL = "1h"

# 自动算出"上个月"是哪年哪月
now = pd.Timestamp.now(tz="UTC")
first_of_this_month = now.replace(day=1)
last_month_end = first_of_this_month - pd.Timedelta(days=1)
year, month = last_month_end.year, last_month_end.month

#https://data.binance.vision/data/futures/um/monthly/klines/{币}/{周期}/{币}-{周期}-{年}-{月}.zip

zip_name = f"{SYMBOL}-{INTERVAL}-{year}-{month:02d}.zip"
zip_url = (
    f"https://data.binance.vision/data/futures/um/monthly/klines/"
    f"{SYMBOL}/{INTERVAL}/{zip_name}"
)
checksum_url = zip_url + ".CHECKSUM"

print("目标月份:", f"{year}-{month:02d}")
print("下载:", zip_url)

r = requests.get(zip_url, timeout=60)
print("zip: HTTP", r.status_code, "大小", len(r.content), "字节")
zip_bytes = r.content

rc = requests.get(checksum_url, timeout=30)
print("CHECKSUM 原文:", repr(rc.text))

# 校验：自己算 SHA256，和官方比
sha = hashlib.sha256(zip_bytes).hexdigest()
official = rc.text.strip().split()[0]
print("本地 SHA256:", sha)
print("官方 SHA256:", official)
print("校验通过?", sha == official)

import zipfile
import io

BASE = "https://fapi.binance.com"
COLUMNS = ["open_time", "open", "high", "low", "close", "volume",
           "close_time", "quote_volume", "trades",
           "taker_buy_base", "taker_buy_quote", "ignore"]

# 1) 解压读 CSV（zip 在内存里，用 BytesIO 包一层）
z = zipfile.ZipFile(io.BytesIO(zip_bytes))
csv_name = z.namelist()[0]
print("zip 里的文件:", csv_name)
df_vision = pd.read_csv(z.open(csv_name), header=None, names=COLUMNS, skiprows=1)
print("vision 行数:", len(df_vision))

# 2) REST 拉同月数据
first_of_month = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
next_month = first_of_month + pd.DateOffset(months=1)
start_ms = int(first_of_month.timestamp() * 1000)
end_ms = int(next_month.timestamp() * 1000) - 1   # 下月1号 - 1ms = 上月最后一毫秒

r2 = requests.get(
    f"{BASE}/fapi/v1/klines",
    params={"symbol": SYMBOL, "interval": INTERVAL,
            "startTime": start_ms, "endTime": end_ms, "limit": 1500},
    timeout=30,
)
print("REST: HTTP", r2.status_code, "已用权重", r2.headers.get("X-MBX-USED-WEIGHT-1M"))
df_rest = pd.DataFrame(r2.json(), columns=COLUMNS)
print("REST 行数:", len(df_rest))

# 3) 逐行比对
for col in ["open", "high", "low", "close", "volume"]:
    df_vision[col] = df_vision[col].astype(float)
    df_rest[col] = df_rest[col].astype(float)

df_vision = df_vision.sort_values("open_time").reset_index(drop=True)
df_rest = df_rest.sort_values("open_time").reset_index(drop=True)

print("\nopen_time 是否完全一致:", (df_vision["open_time"] == df_rest["open_time"]).all())
for col in ["open", "high", "low", "close", "volume"]:
    max_diff = (df_vision[col] - df_rest[col]).abs().max()
    print(f"{col}: 与 REST 的最大差异 = {max_diff}")