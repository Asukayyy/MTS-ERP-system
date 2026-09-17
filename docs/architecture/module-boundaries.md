# 模块边界与接口方向

本文档只定义**边界与接口方向**，不实现任何跨模块调用。
五个人在动手前必须先读这一份。

## 一、总原则

1. 系统只有五个模块：`system`、`sales`、`planning`、`procurement`、`inventory`。
2. 一个模块**只负责自己的业务**，只读写自己拥有的数据表。
3. **禁止**一个模块直接 import 另一个模块的：
   - `service.py`
   - `repository.py`
   - `models.py`
4. 跨模块通信**只能**通过：
   - 已约定的 **Service Contract**（后端内部的显式接口函数），或
   - 已约定的 **API Contract**（HTTP 接口）
5. 允许所有人引用的公共内容：
   - 后端：`app.core.*`、`app.common.*`、`app.shared.*`
   - 前端：`@/utils/*`、`@/types/*`、`@/components/common/*`、`@/stores/*`、`@/layouts/*`

## 二、各模块职责与接口方向

### system（系统与基础信息管理）

**提供全局基础数据**：产品、物料、BOM、工艺路线、组织人员、基础字典、用户、角色、权限、操作日志。

| 方向 | 内容 |
| --- | --- |
| 输入 | 管理员与基础数据维护人员的人工录入 |
| 输出 | 产品、物料、BOM、工艺路线等基础主数据；用户 / 角色 / 权限等系统能力 |
| 被谁消费 | **所有模块**（只读基础主数据） |
| 消费谁 | 无 |

### sales（销售管理）

**产生销售需求和销售订单。**

| 方向 | 内容 |
| --- | --- |
| 输入 | 产品 / 物料（system）、库存可用量（inventory） |
| 输出 | 销售需求、销售预测、销售订单、发货指令 |
| 被谁消费 | planning（销售需求 → MPS）、inventory（发货指令） |
| 消费谁 | system（主数据）、inventory（可发货量） |

### planning（计划管理）

**消费销售需求与基础数据、库存状态，产出采购需求与生产作业需求。**
MPS / MRP / 生产作业计划 / 派工单 / 领料单均属本模块。

| 方向 | 内容 |
| --- | --- |
| 输入 | 销售需求（sales）、BOM / 工艺路线（system）、库存状态（inventory） |
| 输出 | MRP 结果、采购需求、生产作业计划、派工单、领料单 |
| 被谁消费 | procurement（采购需求）、inventory（领料单 / 完工入库单） |
| 消费谁 | sales、system、inventory |

### procurement（采购管理）

**消费 MRP 采购需求，产出采购订单与到货信息。**

| 方向 | 内容 |
| --- | --- |
| 输入 | MRP 采购需求（planning）、物料主数据（system）、库存状态（inventory，参考） |
| 输出 | 采购计划、采购订单、到货信息 |
| 被谁消费 | inventory（到货 → 入库）、planning（采购在途量，参考） |
| 消费谁 | planning、system、inventory |

### inventory（库存管理）

**消费各类出入库来源，产出实时库存状态。**

| 方向 | 内容 |
| --- | --- |
| 输入 | 采购到货（procurement）、生产领料（planning）、完工入库（planning）、销售发货（sales） |
| 输出 | 实时库存状态、库存流水与结存 |
| 被谁消费 | **planning（反馈给 MRP）、sales、procurement** |
| 消费谁 | system（物料 / 仓库基础数据） |

## 三、依赖方向总览

```
system  ◀────────── 所有模块（只读基础数据）

sales ──销售需求──▶ planning ──采购需求──▶ procurement
  ▲                    ▲                     │
  │                    │                     │到货
  │                    └──库存储备/在途◀──────┘
  │                                          │
  └────────────可发货量◀──── inventory ◀──────┘
                                ▲
                                │ 领料 / 完工入库
                             planning
```

**关键反馈环：** inventory 的实时库存状态必须反馈给 planning，用于 MRP 净需求计算。
这是 MTS 模式下"库存 → 计划"的闭环，也是本系统区别于纯订单式系统的核心。

## 四、后续实现跨模块调用的推荐做法

本阶段**不实现**任何跨模块调用。真正要实现时，按下面的顺序推进：

1. **先约定 Contract**：明确函数名 / 接口路径、入参、出参、错误码。
2. **由 Owner 模块实现并暴露**：Owner 在自己的模块里实现，对外暴露一个明确的入口。
3. **消费方只依赖 Contract**：不 import Owner 的内部实现文件。

后端示例（**仅示意，当前未实现**）：

```python
# planning 需要 sales 的销售需求
# ✅ 正确：通过 sales 暴露的 contract
from app.modules.sales.contract import get_sales_demand

# ❌ 错误：直接使用 sales 的内部实现
from app.modules.sales.service import SalesOrderService
from app.modules.sales.repository import SalesOrderRepository
```

> `contract.py` 目前**尚未创建**。哪个模块需要对外提供能力，由该模块负责人在自己模块目录内
> 新建 `contract.py`，并同步更新本文档。

## 五、禁止事项清单

- 禁止 import 其他模块的 `service.py` / `repository.py` / `models.py`
- 禁止跨模块直接查别人的表（跨模块 JOIN 也算）
- 禁止修改其他模块目录内的任何文件
- 禁止为了让自己的模块跑通而改动公共层（`core` / `common` / `shared` / `utils` / `types`）
  —— 确有必要时先在群里沟通
- 禁止在公共层堆业务逻辑
