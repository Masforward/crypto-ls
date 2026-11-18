"""账户对账：每日净值/持仓/现金三项核对，误差超限报错并指出日期和项目。"""
import pandas as pd


def reconcile(snapshots, position_snapshots, fills, close_prices, tolerance=1e-6):
    """逐日核对三项，返回错误列表（空 = 全部通过）。

    snapshots          : 账户快照表（index=时间，含 nav/cash/fee/slippage/funding）
    position_snapshots : [(时间, {symbol: 数量}), ...]，每期逐币持仓
    fills              : 成交记录表（含 time/symbol/side/qty/price/fee/slippage）
    close_prices       : 收盘价面板（算价格盈亏）
    """
    errors = []
    dates = list(snapshots.index)

    prev_nav = None
    prev_cash = None
    prev_positions = {}

    for i, t in enumerate(dates):
        row = snapshots.loc[t]
        day_fills = fills[fills["time"] == t] if len(fills) else fills
        close_t = close_prices.loc[t] if t in close_prices.index else pd.Series(dtype=float)

        # ---- ① 净值核对：期末净值 = 期初净值 + 价格盈亏 - 手续费 - 滑点 + 资金费率 ----
        price_pnl = 0.0
        if i > 0:
            prev_t = dates[i - 1]
            close_prev = close_prices.loc[prev_t] if prev_t in close_prices.index else close_t
            for s, qty in prev_positions.items():
                if s in close_t.index and s in close_prev.index \
                        and not pd.isna(close_t[s]) and not pd.isna(close_prev[s]):
                    price_pnl += qty * (close_t[s] - close_prev[s])
        expected_nav = (prev_nav if prev_nav is not None else row["nav"]) \
            + price_pnl - row["fee"] - row["slippage"] + row["funding"]
        if prev_nav is not None and abs(expected_nav - row["nav"]) > tolerance:
            errors.append(("净值", t, row["nav"], expected_nav))

        # ---- ② 持仓核对：期末持仓 = 期初持仓 + 当日成交数量 ----
        cur_positions = position_snapshots[i][1] if i < len(position_snapshots) else prev_positions
        expected_positions = dict(prev_positions)
        for _, f in day_fills.iterrows():
            expected_positions[f["symbol"]] = expected_positions.get(f["symbol"], 0.0) \
                + f["side"] * f["qty"]
        expected_positions = {s: q for s, q in expected_positions.items() if abs(q) > 1e-12}
        cur_clean = {s: q for s, q in cur_positions.items() if abs(q) > 1e-12}
        if set(expected_positions) != set(cur_clean) or any(
                abs(expected_positions[s] - cur_clean[s]) > tolerance
                for s in expected_positions):
            errors.append(("持仓", t, cur_clean, expected_positions))

        # ---- ③ 现金核对：现金变化 = 成交现金流 - 手续费 - 滑点 + 资金费率 ----
        if len(day_fills):
            cash_flow = -float((day_fills["side"] * day_fills["qty"] * day_fills["price"]).sum())
            day_fee = float(day_fills["fee"].sum())
            day_slip = float(day_fills["slippage"].sum())
        else:
            cash_flow = day_fee = day_slip = 0.0
        expected_cash_change = cash_flow - day_fee - day_slip + row["funding"]
        actual_cash_change = row["cash"] - (prev_cash if prev_cash is not None else row["cash"])
        if prev_cash is not None and abs(expected_cash_change - actual_cash_change) > tolerance:
            errors.append(("现金", t, actual_cash_change, expected_cash_change))

        prev_nav = row["nav"]
        prev_cash = row["cash"]
        prev_positions = cur_clean

    return errors
