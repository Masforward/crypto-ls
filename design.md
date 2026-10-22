# 数据模块设计

## 一、函数签名（只写签名，覆盖四件事）

```python
# 取币种池
def get_universe(str(symbol), str(interval), int(start_time), int(period)):
    ...
    return a csv file

# 取 K 线
def get_klines(str(symbol), str(interval), int(start_time), int(period)):
    ...
    return a dataframe

# 取资金费率
def get_funding_rate(str(symbol), int(start_time), int(period)):
    ...
    return a series

# 增量更新
def update(str(symbol), int(end_time)):
    ...
    update data

## 二、设计问答

1. 返回长表还是宽表？为什么？

2. 数据存在哪里、如何分区？

3. 哪一层知道"币安"、哪一层不知道？

4. 已下架的币如何处理？
