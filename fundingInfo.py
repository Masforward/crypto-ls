import requests
import pandas as pd

now_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
start_ms = now_ms - 90 * 24 * 3600 * 1000

r = requests.get(
    "https://fapi.binance.com/fapi/v1/fundingRate",
    params={"symbol": "BTCUSDT", "startTime": start_ms, "limit": 1000},
    timeout=30,
)
print("fundingRate: HTTP", r.status_code, "已用权重", r.headers.get("X-MBX-USED-WEIGHT-1M"))

fr = r.json()
print("BTCUSDT 90 天资金费率记录数:", len(fr))
print("第一条:", fr[0])
print("最后一条:", fr[-1])

# ===== 第二部分：fundingInfo 找非 8 小时结算的币 =====
r2 = requests.get("https://fapi.binance.com/fapi/v1/fundingInfo", timeout=30)
print("\nfundingInfo: HTTP", r2.status_code, "已用权重", r2.headers.get("X-MBX-USED-WEIGHT-1M"))

info = r2.json()
print("fundingInfo 返回币数:", len(info))

non8 = [x for x in info if x.get("fundingIntervalHours") != 8]
print("结算间隔不是 8 小时的币数:", len(non8))
for x in non8[:10]:
    print("   ", x["symbol"], "->", x["fundingIntervalHours"], "小时")