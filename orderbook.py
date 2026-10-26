"""订单簿：拉取、整理、计算价差/中间价/失衡/滑点。"""
import pandas as pd

from src.cls.data.client import request


def fetch_depth(symbol, limit=20):
    #输入合约名，调出当前订单簿深度数据。
    r = request("/fapi/v1/depth", params={"symbol": symbol, "limit": limit})
    return r.json()


def depth_to_frame(d):
    #输入d，把 bids/asks 拼成买卖方，价格，数量三列的长表。一般的df就从这里来
    bids = pd.DataFrame(d["bids"], columns=["price", "qty"]) #bids是个有两个字典的列表
    bids["side"] = "buy"
    asks = pd.DataFrame(d["asks"], columns=["price", "qty"])
    asks["side"] = "sell"
    df = pd.concat([bids, asks], ignore_index=True)
    df["price"] = df["price"].astype(float)
    df["qty"] = df["qty"].astype(float)
    return df[["side", "price", "qty"]] #调序


def spread_metrics(df):
    #买一、卖一、中间价、价差（绝对 + 基点）。
    best_bid = df[df["side"] == "buy"]["price"].max()
    best_ask = df[df["side"] == "sell"]["price"].min()
    mid = (best_bid + best_ask) / 2
    spread_abs = best_ask - best_bid
    spread_bps = spread_abs / mid * 10000
    return {"best_bid": best_bid, "best_ask": best_ask, "mid": mid,
            "spread_abs": spread_abs, "spread_bps": spread_bps}


def orderbook_imbalance(df, levels=5):
    # 输入df和档位，前 levels 档买卖量失衡：(买量 − 卖量) ÷ (买量 + 卖量)。
    bids = df[df["side"] == "buy"].sort_values("price", ascending=False)
    asks = df[df["side"] == "sell"].sort_values("price", ascending=True)
    bid_qty = bids.head(levels)["qty"].sum()
    ask_qty = asks.head(levels)["qty"].sum()
    return (bid_qty - ask_qty) / (bid_qty + ask_qty)


def simulate_market_buy(df, notional=100_000):
    """模拟市价买入：逐档吃卖盘，直到花够 notional USDT。

    返回 (平均成交价, 总买到的数量)。若订单簿不够深，吃不完的部分会提示。
    """
    asks = df[df["side"] == "sell"].sort_values("price").reset_index(drop=True)
    remaining = float(notional)   # 还剩多少 USDT 要花
    total_qty = 0.0               # 累计买到的币数量
    total_cost = 0.0              # 累计花费

    for _, row in asks.iterrows():
        price, qty = row["price"], row["qty"]
        cost = price * qty        # 这一档全吃要花多少 USDT
        if cost <= remaining:
            total_qty += qty      # 整档吃掉
            total_cost += cost
            remaining -= cost
        else:
            partial = remaining / price   # 只吃一部分
            total_qty += partial
            total_cost += remaining
            remaining = 0
            break

    if remaining > 0:
        print(f"    ⚠ 订单簿不够深，还剩 {remaining:.0f} USDT 没买成")

    avg_price = total_cost / total_qty
    return avg_price, total_qty


def analyze(symbol):
    # 对一个币做完整分析：价差 + 失衡 + 市价买入滑点。
    d = fetch_depth(symbol, limit=20)
    df = depth_to_frame(d)
    m = spread_metrics(df)
    imb = orderbook_imbalance(df, levels=5)
    avg_price, total_qty = simulate_market_buy(df, 100_000)
    slippage_bps = (avg_price - m["mid"]) / m["mid"] * 10000

    print(f"\n{symbol}:")
    print(f"  中间价 {m['mid']}, 价差 {m['spread_bps']:.2f} bps, 失衡 {imb:.4f}")
    print(f"  市价买入 10 万 USDT → 平均成交价 {avg_price:.4f}, "
          f"滑点 {slippage_bps:.2f} bps, 买到 {total_qty:.6f}")
