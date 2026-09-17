"""五个业务模块。

模块划分（**只有这五个**，生产相关功能归属 planning）：
- system       系统与基础信息管理
- sales        销售管理
- planning     计划管理（MPS / MRP / 生产作业计划）
- procurement  采购管理
- inventory    库存管理

隔离铁律：禁止一个模块直接 import 另一个模块的 service / repository / models。
"""
