
import hashlib
import io
import zipfile

import pandas as pd
import requests

from .klines import KLINE_COLUMNS

VISION_BASE = "https://data.binance.vision"


def _download(url):
    #下载 URL 内容，返回 bytes；非 200 抛异常。
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    return r.content


def _verify_checksum(data, url):
    #下载 .CHECKSUM，用 SHA256 校验 data，不一致抛异常。
    expected = _download(url + ".CHECKSUM").decode("utf-8").strip().split()[0]
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"CHECKSUM 校验失败：{url}")
    return actual


def _monthly_url(symbol, interval, year, month):
    #构造月度包 URL。
    ym = f"{year}-{month:02d}"
    return f"{VISION_BASE}/data/futures/um/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{ym}.zip"


def _daily_url(symbol, interval, year, month, day):
    #构造日度包 URL。
    ymd = f"{year}-{month:02d}-{day:02d}"
    return f"{VISION_BASE}/data/futures/um/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{ymd}.zip"


def _read_zip(data):
    #解压 zip，读第一个 CSV：跳过表头，用 KLINE_COLUMNS 命名。
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            return pd.read_csv(f, header=None, names=KLINE_COLUMNS, skiprows=1)


def download_monthly(symbol, interval, year, month):
    """下载 vision 月度包，校验 SHA256，解压读成 DataFrame。

    返回列 = KLINE_COLUMNS（12 列；open_time 仍为毫秒 int，类型转换交给上层）。
    """
    url = _monthly_url(symbol, interval, year, month)
    data = _download(url)
    _verify_checksum(data, url)
    return _read_zip(data)


def download_daily(symbol, interval, year, month, day):
    """下载 vision 日度包，校验 SHA256，解压读成 DataFrame。"""
    url = _daily_url(symbol, interval, year, month, day)
    data = _download(url)
    _verify_checksum(data, url)
    return _read_zip(data)
