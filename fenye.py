import requests
import pandas as pd

print(pd.Timestamp.now(tz="UTC").timestamp())
now_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
start_ms = now_ms - 180 * 24 * 3600000

all_klines = []
page = 0

while True:
    page += 1
    r = requests.get(
        "https://fapi.binance.com/fapi/v1/klines",
        params={
            "symbol": "ETHUSDT",
            "interval": "1h",
            "startTime": start_ms,
            "limit": 1500,
        },
        timeout=30,
    )
    print(f"第 {page} 页: HTTP {r.status_code}, 已用权重 {r.headers.get('X-MBX-USED-WEIGHT-1M')}")

    batch = r.json()
    if not batch:                    # 空 → 没有更多数据了
        break

    all_klines.extend(batch)

    # ★ 关键：下一页 startTime = 本页最后一根 open_time + 1 小时
    # （因为 startTime 是"包含"的，不 +1h 会导致最后一根重复）
    start_ms = batch[-1][0] + 3600000

    if len(batch) < 1500:            # 不满 1500 → 已经拉到最新，结束
        break

print(f"\n总共拉到 {len(all_klines)} 根")

# 验证首尾不重复：去重后数量应该不变
times = [k[0] for k in all_klines]
print("重复的 open_time 个数:", len(times) - len(set(times)))