# 第三周作业报告：全币种 5 分钟 K 线数据库

# 数据概况

| 项目 | 数值 |
|---|---|
| 币种数量 | 523 |
| 总行数 | 82,152,655（约 8215 万） |
| 磁盘占用 | 4.9 GB |

# 缺口最多的 10 个币及原因分析

| 排名 | 币种 | 缺口数（根） | 原因分析 |
|---|---|---|---|
| 1 | LITUSDT | 215 | 合约变更当天暂停交易半天 |
| 2 | MAVIAUSDT | 209 | 合约变更当天暂停交易半天 |
| 3 | SLPUSDT | 146 | 合约变更当天暂停交易半天 |
| 4 | CVXUSDT | 143 | 合约变更当天暂停交易半天 |
| 5 | AIAUSDT | 140 | 合约变更当天暂停交易半天 |
| 6 | CTKUSDT | 128 | 合约变更当天暂停交易半天 |
| 7 | CVCUSDT | 107 | 合约变更当天暂停交易半天 |
| 8 | PUMPUSDT | 95 | 合约变更当天暂停交易半天 |
| 9 | 哈基米USDT | 6 | 最新几分钟尚未收盘 |
| 10 | 1000FLOKIUSDT | 5 | 最新几分钟尚未收盘 |

随机抽取 5 个币、每币 1 天，对比 vision 日度包与 REST 接口，结果完全一致：

| symbol | date | vision 行数 | REST 行数 | open_time 相同 | close 最大差异 |
|---|---|---|---|---|---|
| 牛来USDT | 2026-09-28 | 288 | 288 | ✅ | 0.0 |
| SAFEUSDT | 2025-07-26 | 288 | 288 | ✅ | 0.0 |
| 1000LUNCUSDT | 2026-06-01 | 288 | 288 | ✅ | 0.0 |
| FARTCOINUSDT | 2025-06-13 | 288 | 288 | ✅ | 0.0 |
| BARDUSDT | 2025-12-27 | 288 | 288 | ✅ | 0.0 |

**结论：vision 与 REST 数据一致（行数相同、open_time 集合相同、close 最大差异 0）。**

# notebook路径 

crypto-ls\notebooks\demo.ipynb

# 中断update_klines

  (.venv) PS C:\Users\26096\Desktop\crypto-ls> python -c "from src.cls.data import update_klines; r = update_klines()"                 
  BTCUSDT 2026-10-28：今天 REST 新增 1行                                                                                                                       
  ETHUSDT 2026-10-28：今天 REST 新增 1 行
  BCHUSDT 2026-10-28：今天 REST 新增 1 行
  XRPUSDT 2026-10-28：今天 REST 新增 1 行
  LTCUSDT 2026-10-28：今天 REST 新增 1 行
  TRXUSDT 2026-10-28：今天 REST 新增 1 行
  ETCUSDT 2026-10-28：今天 REST 新增 1 行
  LINKUSDT 2026-10-28：今天 REST 新增 1 行
  XLMUSDT 2026-10-28：今天 REST 新增 1 行
  ^C
  ...
  KeyboardInterrupt

  (.venv) PS C:\Users\26096\Desktop\crypto-ls> python -c "from src.cls.data import update_klines; r = update_klines()"
  BTCUSDT 2026-10-28：今天 REST 新增 0 行
  ETHUSDT 2026-10-28：今天 REST 新增 0 行
  BCHUSDT 2026-10-28：今天 REST 新增 0 行
  XRPUSDT 2026-10-28：今天 REST 新增 0 行
  LTCUSDT 2026-10-28：今天 REST 新增 0 行
  TRXUSDT 2026-10-28：今天 REST 新增 0 行
  ETCUSDT 2026-10-28：今天 REST 新增 0 行
  LINKUSDT 2026-10-28：今天 REST 新增 0 行
  XLMUSDT 2026-10-28：今天 REST 新增 0 行   # 没有重复下载
  ADAUSDT 2026-10-28：今天 REST 新增 1 行
  XMRUSDT 2026-10-28：今天 REST 新增 1 行
  DASHUSDT 2026-10-28：今天 REST 新增 1 行
  ZECUSDT 2026-10-28：今天 REST 新增 1 行
  XTZUSDT 2026-10-28：今天 REST 新增 1 行
  BNBUSDT 2026-10-28：今天 REST 新增 1 行
  ATOMUSDT 2026-10-28：今天 REST 新增 1 行
  ONTUSDT 2026-10-28：今天 REST 新增 1 行
  ...

# 断网读取函数

(.venv) PS C:\Users\26096\Desktop\crypto-ls> python -c "from src.cls.data import load_klines; print('load_klines:', load_klines('BTCUSDT','2026-10-01','2026-10-02').shape)"                                                                                                                                         load_klines: (288, 13)

(.venv) PS C:\Users\26096\Desktop\crypto-ls> python -c "from src.cls.data import load_panel; print('load_panel:', load_panel('close','BTCUSDT','2026-10-01','2026-10-02').shape)"                                                                                                                                         load_panel: (288, 1)

(.venv) PS C:\Users\26096\Desktop\crypto-ls> python -c "from src.cls.data import list_symbols; print('list_symbols 币数:', len(list_symbols()))"
list_symbols 币数: 523

(.venv) PS C:\Users\26096\Desktop\crypto-ls> python -c "from src.cls.data import quality_report; print(quality_report('BTCUSDT').to_string())"
      symbol  expected  actual  gaps  invalid
108  BTCUSDT    191636  191636     0        0
