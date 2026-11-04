import time

import pandas as pd
import requests

BASE = "https://fapi.binance.com"
WEIGHT_BUDGET = 2000

_time_offset_ms = 0  # 币安服务器时间 − 本地时钟的偏移（毫秒）；未校准为 0


def request(path, params=None, max_retries=3):
    #输入后续网址，参数，请求次数，返回回复
    url = f"{BASE}{path}"

    for _ in range(max_retries):
        resp = requests.get(url, params=params, timeout=30)

        if resp.status_code == 418:
            raise RuntimeError("IP 被封禁 (418)，立即停止")

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            continue

        if resp.status_code != 200:
            resp.raise_for_status()

        used = int(resp.headers.get("X-MBX-USED-WEIGHT-1M", 0))
        if used > WEIGHT_BUDGET:
            time.sleep(60)  # 主动限速：等下一分钟窗口重置

        return resp

    raise RuntimeError("重试次数用尽")


def calibrate_time():
    """调 /fapi/v1/time 校准本地时钟与币安服务器时钟的偏移（毫秒）。"""
    global _time_offset_ms
    resp = request("/fapi/v1/time")
    server_ms = resp.json()["serverTime"]
    local_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    _time_offset_ms = server_ms - local_ms
    print(f"币安服务器时间偏差：{_time_offset_ms:+.0f} 毫秒")
    return _time_offset_ms


def server_now():
    """返回币安服务器当前时间（UTC Timestamp）。未校准过则退化成本地时钟。"""
    return pd.Timestamp.now(tz="UTC") + pd.Timedelta(milliseconds=_time_offset_ms)
