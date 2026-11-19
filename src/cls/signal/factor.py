"""信号模块：因子基类与具体因子。

因子只负责"计算原始值"：声明名字 / 频率 / 历史长度 / 预期方向，
compute 接收已经读好的日线数据（不联网、不读文件），返回标量。

compute 输入约定：
  df —— 某个币的日线 DataFrame，按 open_time 升序，最后一行是"最近已收盘的一天"（t-1）。
        列至少含 open / high / low / close / volume（可选 taker_buy_volume 等）。
  返回 —— float 标量，该币在 t 时刻的因子原始值；数据不足返回 NaN。
"""
import numpy as np
import pandas as pd


class Factor:
    """因子基类：声明名字、频率、历史长度、预期方向，compute 算原始值。"""

    name = ""            # 因子名（英文，用于分数表列名和缓存文件名）
    frequency = "1d"     # 计算频率（日线）
    history = 0          # 计算所需的历史长度（天）
    direction = +1       # 预期方向：+1 越高越看多，-1 越高越看空
    needs_market = False  # 是否需要市场（BTC）数据（如 beta、特质波动率）

    def compute(self, df, market=None):
        raise NotImplementedError


class Momentum7d(Factor):
    """7 日动量：过去 7 天收益，跳过最近 1 天（趋势延续，越高越看多）。"""

    name = "momentum_7d"
    history = 9   # close[t-9] ~ close[t-1]，共 9 天

    def compute(self, df):
        closes = df["close"].values
        if len(closes) < self.history:
            return float("nan")
        # 过去 7 天收益（t-9 → t-2），跳过最近 1 天（t-1）
        return closes[-2] / closes[-9] - 1.0


class OneDayReversal(Factor):
    """1 日反转：最近 1 天收益取负（短期过度反应后回归，越高越看多）。"""

    name = "one_day_reversal"
    history = 2   # close[t-2] ~ close[t-1]

    def compute(self, df):
        closes = df["close"].values
        if len(closes) < self.history:
            return float("nan")
        # 最近 1 天收益 = close[-1] / close[-2] - 1，取负
        return -(closes[-1] / closes[-2] - 1.0)


class Volatility7d(Factor):
    """7 日波动率：过去 7 天小时收益的标准差（低波动异象，波动越高越看空）。"""

    name = "volatility_7d"
    frequency = "1h"   # 用小时线算
    history = 169      # 7 天 × 24 小时 + 1 = 169 根，算 168 个收益
    direction = -1

    def compute(self, df):
        closes = df["close"].values
        if len(closes) < self.history:
            return float("nan")
        recent = closes[-self.history:]          # 最后 169 根小时线
        returns = recent[1:] / recent[:-1] - 1.0  # 168 个收益
        return float(np.std(returns))


class VolumeSurge(Factor):
    """成交额异动：近 1 天成交额 ÷ 过去 30 天日均成交额（关注度骤升，越高越看多）。"""

    name = "volume_surge"
    history = 31   # 近 1 天 + 过去 30 天

    def compute(self, df):
        vols = df["quote_volume"].values
        if len(vols) < self.history:
            return float("nan")
        recent = vols[-1]                       # 近 1 天成交额
        base = vols[-self.history:-1].mean()     # 过去 30 天日均成交额
        if base == 0:
            return float("nan")
        return float(recent / base)


class TakerBuyRatio(Factor):
    """主动买入占比：近 1 天主动买入额 ÷ 总成交额，减去自身 30 天均值（买方急于成交，越高越看多）。"""

    name = "taker_buy_ratio"
    history = 31

    def compute(self, df):
        taker = df["taker_buy_quote_volume"].values   # 主动买入额
        total = df["quote_volume"].values             # 总成交额
        if len(total) < self.history:
            return float("nan")
        if total[-1] == 0:
            return float("nan")
        recent_ratio = taker[-1] / total[-1]          # 近 1 天主动买入占比
        past = total[-self.history:-1]
        past_taker = taker[-self.history:-1]
        past_ratio = np.divide(past_taker, past, out=np.full_like(past, np.nan), where=past != 0)
        if np.isnan(past_ratio).all():   # 过去 30 天全无成交额，无基准可减
            return float("nan")
        return float(recent_ratio - np.nanmean(past_ratio))


class MaxDailyGain(Factor):
    """最大单日涨幅：过去 30 天单日收益的最大值（彩票偏好，暴涨后表现偏弱，越高越看空）。"""

    name = "max_daily_gain"
    history = 31   # 31 根 close 算 30 个日收益
    direction = -1

    def compute(self, df):
        closes = df["close"].values
        if len(closes) < self.history:
            return float("nan")
        recent = closes[-self.history:]          # 31 根 close
        returns = recent[1:] / recent[:-1] - 1.0  # 30 个日收益
        return float(returns.max())


class Amplitude7d(Factor):
    """振幅：过去 7 天（最高 − 最低）÷ 收盘 的平均（日内风险高被高估，越高越看空）。"""

    name = "amplitude_7d"
    history = 7
    direction = -1

    def compute(self, df):
        if len(df) < self.history:
            return float("nan")
        recent = df.iloc[-self.history:]
        amp = (recent["high"] - recent["low"]) / recent["close"]
        return float(amp.mean())


class ReturnSkew7d(Factor):
    """收益偏度：过去 7 天小时收益的偏度（右偏被高估，越高越看空）。"""

    name = "return_skew_7d"
    frequency = "1h"
    history = 169   # 7 天 × 24 小时 + 1
    direction = -1

    def compute(self, df):
        closes = df["close"].values
        if len(closes) < self.history:
            return float("nan")
        recent = closes[-self.history:]          # 169 根小时线
        returns = recent[1:] / recent[:-1] - 1.0  # 168 个收益
        return float(pd.Series(returns).skew())


class OvernightReturn(Factor):
    """隔夜收益：昨收到今开的跳空（跳空高开有惯性，越高越看多）。"""

    name = "overnight_return"
    history = 2   # 需要 close[t-2] 和 open[t-1]

    def compute(self, df):
        if len(df) < 2:
            return float("nan")
        return float(df["open"].iloc[-1] / df["close"].iloc[-2] - 1.0)


class IntradayRangePos(Factor):
    """日内收盘位置：收盘价在当天振幅区间的位置 0~1（收在高位有惯性，越高越看多）。"""

    name = "intraday_range_pos"
    history = 1

    def compute(self, df):
        last = df.iloc[-1]
        rng = last["high"] - last["low"]
        if rng == 0:
            return float("nan")
        return float((last["close"] - last["low"]) / rng)


class RealizedSkew30d(Factor):
    """已实现偏度：过去 30 天日收益的偏度（右偏=彩票特征被高估，越高越看空）。"""

    name = "realized_skew_30d"
    history = 31   # 31 根 close 算 30 个日收益
    direction = -1

    def compute(self, df):
        closes = df["close"].values
        if len(closes) < self.history:
            return float("nan")
        recent = closes[-self.history:]
        returns = recent[1:] / recent[:-1] - 1.0
        return float(pd.Series(returns).skew())


class UpDownVolRatio(Factor):
    """上下行波动比：上行收益波动 ÷ 下行收益波动（上行波动大=追涨过热，越高越看空）。"""

    name = "updown_vol_ratio"
    history = 31
    direction = -1

    def compute(self, df):
        closes = df["close"].values
        if len(closes) < self.history:
            return float("nan")
        recent = closes[-self.history:]
        returns = recent[1:] / recent[:-1] - 1.0
        up, down = returns[returns > 0], returns[returns < 0]
        if len(up) < 2 or len(down) < 2:
            return float("nan")
        down_vol = down.std()
        if down_vol == 0:
            return float("nan")
        return float(up.std() / down_vol)


class VolPriceCorr(Factor):
    """量价相关：日收益与成交额变化率的相关（量价相关高=追涨情绪过热，越高越看空）。"""

    name = "vol_price_corr"
    history = 31
    direction = -1

    def compute(self, df):
        closes = df["close"].values
        vols = df["quote_volume"].values
        if len(closes) < self.history or len(vols) < self.history:
            return float("nan")
        rc = closes[-self.history:]
        rv = vols[-self.history:]
        returns = rc[1:] / rc[:-1] - 1.0
        vol_chg = rv[1:] / rv[:-1] - 1.0
        if np.std(returns) == 0 or np.std(vol_chg) == 0:
            return float("nan")
        return float(np.corrcoef(returns, vol_chg)[0, 1])


class Amihud(Factor):
    """非流动性：|日收益| ÷ 日成交额 的均值（高非流动性=流动性溢价，越高越看多）。"""

    name = "amihud"
    history = 31

    def compute(self, df):
        closes = df["close"].values
        vols = df["quote_volume"].values
        if len(closes) < self.history:
            return float("nan")
        rc = closes[-self.history:]
        rv = vols[-self.history:]
        returns = rc[1:] / rc[:-1] - 1.0
        vols_r = rv[1:]
        ratio = np.abs(returns) / np.where(vols_r > 0, vols_r, np.nan)
        if np.isnan(ratio).all():
            return float("nan")
        return float(np.nanmean(ratio))


class BtcBeta(Factor):
    """BTC beta：日收益对 BTC 日收益的回归斜率（高 beta=跟大盘无独立 alpha，越高越看空）。"""

    name = "btc_beta"
    history = 31
    direction = -1
    needs_market = True

    def compute(self, df, market=None):
        closes = df["close"].values
        if len(closes) < self.history or market is None or len(market) < self.history:
            return float("nan")
        r = closes[-self.history:][1:] / closes[-self.history:][:-1] - 1.0
        m = market["close"].values[-self.history:][1:] / market["close"].values[-self.history:][:-1] - 1.0
        var_m = np.var(m)
        if var_m == 0:
            return float("nan")
        return float(np.cov(r, m)[0, 1] / var_m)


class IdioVol(Factor):
    """特质波动率：减去 beta×BTC 收益后的残差波动（高特质波动=彩票偏好被高估，越高越看空）。"""

    name = "idio_vol"
    history = 31
    direction = -1
    needs_market = True

    def compute(self, df, market=None):
        closes = df["close"].values
        if len(closes) < self.history or market is None or len(market) < self.history:
            return float("nan")
        r = closes[-self.history:][1:] / closes[-self.history:][:-1] - 1.0
        m = market["close"].values[-self.history:][1:] / market["close"].values[-self.history:][:-1] - 1.0
        var_m = np.var(m)
        beta = np.cov(r, m)[0, 1] / var_m if var_m > 0 else 0.0
        resid = r - beta * m
        return float(resid.std())
