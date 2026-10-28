"""批量回填：把全币种的历史 5 分钟 K 线从 vision + REST 落盘到按月 Parquet。"""
from .config import data_dir as _data_dir
import os

import pandas as pd
import requests

from .klines import _fetch_raw
from .store import write_monthly_klines
from .vision import download_daily, download_monthly


def _month_range(start, end):
    #生成 [start, end] 之间的 (year, month) 列表，按月份递增。start/end 都是 pd.Timestamp（UTC）。返回如 [(2025,1), (2025,2), ...]。
    months = []
    y, m = start.year, start.month
    ey, em = end.year, end.month
    while (y, m) <= (ey, em):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def backfill_month(symbol, interval, year, month, data_dir=None):
    #用 vision 月度包回填某币某月的 K 线。vision 404（该月没有包，即币未上市）→ 返回 False 表示无数据；
    #成功写盘 → 返回 True。
    try:
        df = download_monthly(symbol, interval, year, month)
    except requests.HTTPError:
        return False
    path, n_new, n_dup = write_monthly_klines(df, symbol, interval, year, month, data_dir)
    dup = f"，已有 {n_dup} 行" if n_dup else ""
    print(f"{symbol} {year}-{month:02d}: {path}（新增 {n_new} 行{dup}）")
    return True


def _rest_day(symbol, interval, year, month, day):
    #REST 拉某天（UTC 00:00 到次日 00:00）的原始 K 线（12 列）。并没有次日00：00。
    day_start = pd.Timestamp(f"{year}-{month:02d}-{day:02d}", tz="UTC")
    day_end = day_start + pd.Timedelta(days=1)
    start_ms = int(day_start.timestamp() * 1000)
    end_ms = int(day_end.timestamp() * 1000) - 1   # -1ms：endTime 是 inclusive，避免多拉次日第一根
    return _fetch_raw(symbol, interval, start_ms, end_ms)


def _day_complete(symbol, interval, year, month, day, data_dir):
    """检查某天是否已完整（该月文件里该天的应有根数都在）。"""
    from .store import _um_klines_path
    path = _um_klines_path(data_dir, symbol, interval, year, month)
    if not os.path.exists(path):
        return False
    df = pd.read_parquet(path, columns=["open_time"])
    day_start = pd.Timestamp(year, month, day, tz="UTC")
    day_end = day_start + pd.Timedelta(days=1)
    n = ((df["open_time"] >= day_start) & (df["open_time"] < day_end)).sum()
    expected = int(pd.Timedelta(days=1) / pd.Timedelta(interval))
    return n >= expected


def backfill_day(symbol, interval, year, month, day, data_dir=None):
    # 回填某币某天：先试 vision 日度包，404 用 REST 兜底；两者都失败则跳过。
    # 该天已完整则直接跳过（避免重复下载日度包）。返回来源或 "skip"/None。
    if _day_complete(symbol, interval, year, month, day, data_dir):
        return "skip"
    try:
        df = download_daily(symbol, interval, year, month, day)
        source = "vision"
    except requests.HTTPError:
        try:
            df = _rest_day(symbol, interval, year, month, day)
            source = "rest"
        except requests.HTTPError as e:
            print(f"  ⚠ 跳过 {symbol} {year}-{month:02d}-{day:02d}：vision 404 且 REST 失败（HTTP {e.response.status_code}）")
            return None
    if not df.empty:
        path, n_new, n_dup = write_monthly_klines(df, symbol, interval, year, month, data_dir)
        dup = f"，已有 {n_dup} 行" if n_dup else ""
        print(f"{symbol} {year}-{month:02d}-{day:02d} ({source}): {path}（新增 {n_new} 行{dup}）")
    return source


def backfill(symbols, interval, start, data_dir=None):
    if data_dir is None:
        data_dir = _data_dir()
    # 最终的回填函数，注意now_day不包含今天。
    # 每次回填完一个币后，会自动续写增量更新报告，防断网。
    # 如果中途程序退出，再次下载会读coverage_5m.parquet查询质量，跳过逐行核对。
    if isinstance(symbols, str):
        symbols = [symbols]
    start = pd.Timestamp(start)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    now = pd.Timestamp.now(tz="UTC")

    # 完整历史月的终点 = 上个月最后一天
    last_full = pd.Timestamp(now.year, now.month, 1, tz="UTC") - pd.Timedelta(days=1)

    # 开头查已有报告（每个币回填完就增量更新，所以报告是最新的）
    from .meta import _meta_path, _update_coverage_symbol
    complete = set()
    cov_path = _meta_path(data_dir, "coverage_5m")
    if os.path.exists(cov_path):
        cov = pd.read_parquet(cov_path)
        complete = set(zip(cov.loc[cov["gaps"] == 0, "symbol"],
                           cov.loc[cov["gaps"] == 0, "month"]))

    # 读币种清单拿上市时间（回填完更新该币报告时，算 expected 用）
    onboard_map = {}
    symbols_path = _meta_path(data_dir, "symbols")
    if os.path.exists(symbols_path):
        symbols_meta = pd.read_parquet(symbols_path)
        onboard_map = dict(zip(symbols_meta["symbol"], symbols_meta["onboard_date"]))

    for symbol in symbols:
        onboard = onboard_map.get(symbol, pd.Timestamp(start))
        # ① 完整历史月：coverage 显示完整则跳过，缺失才下载月度包
        for year, month in _month_range(start, last_full):
            ym = f"{year}-{month:02d}"
            if (symbol, ym) in complete:
                print(f"  ✓ 跳过 {symbol} {ym}（已完整）")
                continue
            backfill_month(symbol, interval, year, month, data_dir)

        # ② 当前月已结束的日子（1 号到昨天）：vision 日度包，404 用 REST 兜底
        for day in range(1, now.day):
            backfill_day(symbol, interval, now.year, now.month, day, data_dir)

        # ③ 回填完该币，增量更新它的报告（崩溃安全：断了重跑能跳过已完成的币）
        _update_coverage_symbol(symbol, onboard, interval, data_dir)


def update_klines(symbols=None, start="2025-01-01", interval="5m", data_dir=None):
    """增量补齐本地 K 线（唯一联网的更新函数），返回更新报告。

    symbols：None = 全部（读 symbols.parquet）；或指定币种。
    从本地水位线（最后采集时间）逐天补到昨天，今天用 REST 并剔除未收盘。
    """
    if data_dir is None:
        data_dir = _data_dir()
    from .meta import _meta_path, _update_coverage_symbol
    from .store import write_monthly_klines

    if symbols is None:
        symbols = pd.read_parquet(_meta_path(data_dir, "symbols"))["symbol"].tolist()
    elif isinstance(symbols, str):
        symbols = [symbols]

    # 读币种清单拿上市时间（更新报告算 expected 用）
    onboard_map = {}
    symbols_path = _meta_path(data_dir, "symbols")
    if os.path.exists(symbols_path):
        symbols_meta = pd.read_parquet(symbols_path)
        onboard_map = dict(zip(symbols_meta["symbol"], symbols_meta["onboard_date"]))

    now = pd.Timestamp.now(tz="UTC")
    step = pd.Timedelta(interval)
    report = []

    for symbol in symbols:
        sym_dir = os.path.join(data_dir, "binance", "um", "klines", interval, symbol)
        files = sorted(f for f in os.listdir(sym_dir) if f.endswith(".parquet")) if os.path.isdir(sym_dir) else []
        if files:
            last_df = pd.read_parquet(os.path.join(sym_dir, files[-1]))
            watermark = last_df["open_time"].max() + step
        else:
            watermark = pd.Timestamp(start)
            if watermark.tzinfo is None:
                watermark = watermark.tz_localize("UTC")

        # 从 watermark 所在天到昨天，逐天 backfill_day（vision 日度包，404 REST 兜底）
        day = watermark.floor("1D")
        while day < now.floor("1D"):
            src = backfill_day(symbol, interval, day.year, day.month, day.day, data_dir)
            d = day.strftime("%Y-%m-%d")
            if src == "skip":
                print(f"  ✓ {symbol} {d}：已完整，跳过")
            elif src in ("vision", "rest"):
                print(f"  {symbol} {d}：{src} 更新")
            else:
                print(f"  ⚠ {symbol} {d}：无数据（vision 404 且 REST 失败）")
            day += pd.Timedelta(days=1)

        # 今天：REST 拉，剔除未收盘（open_time 是毫秒 int，用毫秒比较）
        today = now.floor("1D")
        today_df = _rest_day(symbol, interval, today.year, today.month, today.day)
        step_ms = int(step.total_seconds() * 1000)
        now_ms = int(now.timestamp() * 1000)
        today_df = today_df[today_df["open_time"] + step_ms <= now_ms]
        if not today_df.empty:
            _, n_added, _ = write_monthly_klines(today_df, symbol, interval, today.year, today.month, data_dir)
            print(f"  {symbol} {today.strftime('%Y-%m-%d')}：今天 REST 新增 {n_added} 行")
        else:
            print(f"  {symbol} {today.strftime('%Y-%m-%d')}：今天无已收盘数据")

        # 更新该币的报告（保证 quality_report 读到的报告最新）
        onboard = onboard_map.get(symbol, pd.Timestamp(start))
        _update_coverage_symbol(symbol, onboard, interval, data_dir)

        report.append({"symbol": symbol, "watermark": watermark, "updated_to": now})

    return pd.DataFrame(report)
