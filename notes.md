# 第三周作业报告：全币种 5 分钟 K 线数据库

## 一、数据概况

| 项目 | 数值 |
|---|---|
| 币种数量 | 523 |
| 总行数 | 82,152,655（约 8215 万） |
| 磁盘占用 | 4.9 GB |
| 数据范围 | 2025-01-01 至今，5 分钟 K 线，USDⓈ-M 永续合约 |
| 存储格式 | Parquet，按 `data/binance/um/klines/5m/{SYMBOL}/{YYYY-MM}.parquet` 按月分文件 |

## 二、数据质量

- **时间戳对齐**：open_time 是 5 分钟整数倍；close_time = open_time + 5 分钟 − 1 毫秒；统一 UTC；只保存已收盘 K 线。
- **合法性校验**：最高价 ≥ 开盘/收盘、最低价 ≤ 开盘/收盘、价格 > 0、成交量 ≥ 0、主动买入量 ≤ 总成交量。
- **覆盖情况**：`data/binance/um/meta/coverage_5m.parquet`（每币每月应有/实有/缺口数）。
- **缺口明细**：`data/binance/um/meta/gaps_5m.parquet`（symbol、缺失起止时间、缺失根数）。

## 三、缺口分析

### 正数缺口：523 个币共 3759 根

| 类别 | 币数 | 缺口合计 | 原因 |
|---|---|---|---|
| 合约变更币的真缺口 | 8 | 约 1300 根 | CVX/SLP/CVC/LIT 等币曾做合约升级，升级当天暂停交易半天（缺 138~210 根） |
| 最新几分钟未收盘 | 515 | 约 2400 根 | `update_klines` 补齐到今天后，只剩最新几分钟尚未收盘（各 1~2 根） |

### 关于"合约变更币"（原负数 gaps 已修正）

8 个币（LITUSDT/CVXUSDT/SLPUSDT/CVCUSDT 等）的 `onboardDate` 字段标记的是**"合约变更时间"**（如 CVXUSDT 是 2025-07-23），而非"上市时间"——它们的数据其实从 2025-01 就连续存在。

已修正：`expected`（应有根数）改用**数据实际起点** `min(onboardDate, 最早 open_time)` 计算，负数 gaps 归零，合约变更当天的真缺口正确显示为正数（如 CVXUSDT 缺 138 根，正是 2025-07-23 暂停交易的半天）。

## 四、抽样对账结论

随机抽取 5 个币、每币 1 天，对比 vision 日度包与 REST 接口，结果**完全一致**：

| symbol | date | vision 行数 | REST 行数 | open_time 相同 | close 最大差异 |
|---|---|---|---|---|---|
| 牛来USDT | 2026-09-28 | 288 | 288 | ✅ | 0.0 |
| SAFEUSDT | 2025-07-26 | 288 | 288 | ✅ | 0.0 |
| 1000LUNCUSDT | 2026-06-01 | 288 | 288 | ✅ | 0.0 |
| FARTCOINUSDT | 2025-06-13 | 288 | 288 | ✅ | 0.0 |
| BARDUSDT | 2025-12-27 | 288 | 288 | ✅ | 0.0 |

**结论：vision 与 REST 数据一致（行数相同、open_time 集合相同、close 最大差异 0）。**

## 五、验收

- [x] 中断后重新运行 `update_klines`，不重复下载、结果不变（幂等 + 断点续传）。
- [x] 断网时读取函数和 pytest 测试全部可用（读取不联网）。
- [x] 全文搜索：数据层以外无 `fapi.binance.com` / `data.binance.vision` / `read_parquet`。
- [x] notebook 演示：`notebooks/demo.ipynb` 一行 `load_klines` 读 10 币一周 + 画收盘价。
