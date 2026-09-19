# Planning 跨模块数据接口草案（Interface Draft）

> **性质说明：本文件是第 2 周的接口「需求草案」，用于记录数据级需求。**
> 正式的函数签名 / REST 路径 / 出入参结构已在实现阶段落地，见第四节与
> [../architecture/module-boundaries.md](../architecture/module-boundaries.md) 的 Contract 机制。

## 一、Planning 需要（输入侧）

| 数据 | Provider | Consumer | Purpose |
| --- | --- | --- | --- |
| 产品基本信息 | System | Planning | 识别 MPS / MRP 的计划对象（成品 / 半成品） |
| 物料信息 | System | Planning | MRP 展开；判断物料属性（自制 / 外购） |
| BOM 结构 | System | Planning | MRP 逐层展开（转椅 BOM 为验证对象） |
| 工艺路线（需要时） | System | Planning | 生产作业计划安排的参考依据 |
| 销售需求 / 销售预测 / 销售订单需求 | Sales | Planning | MPS 制定与维护的需求来源 |
| 当前库存 / 可用库存 | Inventory | Planning | MRP 净需求计算 |
| 库存状态更新（反馈） | Inventory | Planning | 库存变化后驱动计划闭环（MTS 反馈环） |

## 二、Planning 提供（输出侧）

| 数据 | Provider | Consumer | Purpose |
| --- | --- | --- | --- |
| MRP 外购物料需求（Purchase Requirement） | Planning | Procurement | 生成采购计划 / 采购订单 |
| 生产领料需求 / 领料单（Material Requisition） | Planning | Inventory | 生产领料出库 |
| 生产作业计划 | Planning | 生产执行（业务参与方） | 车间生产安排 |
| 派工单 / 派工信息 | Planning | 生产执行（业务参与方） | 车间作业任务下达 |
| 计划执行状态 / 计划业务数据（查询） | Planning | 计划管理人员及其他模块 | 综合查询与统计分析 |

## 三、落地规则（已生效）

1. 由 **Provider（Owner）模块**在自己目录内新建 `contract.py` 暴露能力；Consumer **只依赖 Contract**，不 import Owner 的 `service.py` / `repository.py` / `models.py`。
2. 禁止跨模块直读 / JOIN 其他模块的表；单据关联使用 **ID 引用**（`<entity>_id`，`BIGINT`）。
   跨模块历史业务外键默认 `ON DELETE RESTRICT`（规格 §20）；多态引用只建索引不建外键。
   基础数据被业务引用后不物理删除，改为 `status = INACTIVE`。
3. 库存数量以 inventory 的接口为准，planning 不自行缓存库存字段。
4. 每个接口的入参、出参、错误码（planning 区段 `3000~3999`）已在实现中定义，见
   [`../api/api-contract.md`](../api/api-contract.md)。

## 四、落地结果

上表数据需求已全部转为正式契约（五个模块的 `contract.py` 均已创建）：

| 数据需求 | 实际契约函数 | 所在模块 |
| --- | --- | --- |
| 物料信息 | `get_material` / `get_materials` / `get_finished_materials` | `system.contract` |
| BOM 结构 | `get_active_bom_children` / `get_active_bom` / `has_bom` | `system.contract` |
| 销售需求 / 销售订单需求 | `get_open_order_demand` / `get_confirmed_forecast_demand` | `sales.contract` |
| 当前库存 / 可用库存 | `get_stock_snapshot` / `get_available_qty` | `inventory.contract` |
| 采购需求 | `create_purchase_plan_from_mrp`（planning → procurement） | `procurement.contract` |
| 领料需求 | `decrease_stock`（planning → inventory） | `inventory.contract` |
| 完工入库 | `increase_stock`（planning → inventory） | `inventory.contract` |
| 计划数据对外查询 | `get_mrp_results` / `get_open_production_qty` / `create_production_plan_from_mrp_result` | `planning.contract` |

> 契约纪律：只返回 `dict` / 标量，不返回 ORM 对象；永不 `db.commit()`，由调用方事务统一提交。
> 登记位置：[`../architecture/module-boundaries.md`](../architecture/module-boundaries.md) 第四节。
