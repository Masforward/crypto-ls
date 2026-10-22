"""蜡烛图可视化（课程之外，仅需 matplotlib）。"""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 让中文标题能正常显示（Windows 自带微软雅黑/黑体）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


def plot_candlestick(df, n=None, up_color="red", down_color="green", title=None):
    """画单币蜡烛图。

    df : 长表，需含 symbol, open_time, open, high, low, close（单个 symbol）
    n  : 只画最近 n 根（默认全部）
    up_color / down_color : 涨/跌颜色（默认红涨绿跌，改成 green/red 即绿涨红跌）
    返回 (fig, ax)
    """
    d = df.copy().reset_index(drop=True)
    if n is not None:
        d = d.tail(n)

    x = mdates.date2num(d["open_time"])   # 时间转成 matplotlib 的数值坐标
    up = d["close"] >= d["open"]          # 涨（含平盘）

    fig, ax = plt.subplots(figsize=(12, 6))

    # 影线：high-low 的竖线（一次画完，向量化）
    ax.vlines(x, d["low"], d["high"], color="gray", linewidth=0.7)

    # 实体宽度 = 相邻两根时间差（天）的 60%
    width = (x[1] - x[0]) * 0.6 if len(x) >= 2 else 0.02

    # 涨：实体从 open 画到 close
    ax.bar(x[up], (d["close"] - d["open"])[up], bottom=d["open"][up],
           color=up_color, width=width, edgecolor=up_color)
    # 跌：实体从 close 画到 open
    down = ~up
    ax.bar(x[down], (d["open"] - d["close"])[down], bottom=d["close"][down],
           color=down_color, width=width, edgecolor=down_color)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate()
    ax.set_title(title or f"{d['symbol'].iloc[0]} 蜡烛图")
    ax.set_ylabel("价格")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig, ax
