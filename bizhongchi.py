import requests

r = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=30)
print(r.status_code)
print("已用权重 X-MBX-USED-WEIGHT-1M:", r.headers.get("X-MBX-USED-WEIGHT-1M"))

data = r.json()
#print(list(data.keys()))

symbols = data["symbols"]
print("总合约数:", len(symbols))

pool = []

for s in symbols:
    if s["quoteAsset"] == "USDT" and s["contractType"] == "PERPETUAL" and s["status"] == "TRADING":
        pool.append(s)

print("币种池数量:", len(pool))
