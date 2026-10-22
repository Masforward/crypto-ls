import time

import requests

BASE = "https://fapi.binance.com"
WEIGHT_BUDGET = 2000


def request(path, params=None, max_retries=3):

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
