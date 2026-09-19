# 数据所有权规划

## 一、原则

1. **每张业务数据表必须有且只有一个 Owner 模块。**
2. Owner 模块负责该表的模型定义、迁移脚本、读写逻辑、业务规则。
3. 非 Owner 模块**不得**：
   - 直接读写该表
   - 修改该表对应的 `models.py` 与迁移脚本
   - 跨模块 JOIN 该表
4. 非 Owner 模块需要这些数据时，通过 Owner 暴露的 **Service / API Contract** 获取。
5. 五个模块共享同一个 MySQL 数据库，但**代码按模块隔离**。
6. 表名使用小写下划线命名，**统一使用模块前缀**以避免歧义。五个模块的前缀映射为：`sys_`（system）、`sal_`（sales）、`pln_`（planning）、`pur_`（procurement）、`inv_`（inventory）。Owner 模块在定义表时必须在表名本体前加上所属模块前缀。

> **五模块业务表已按本规划落地**（基线 Alembic 迁移 `9e6fa0de8416`，共 52 张业务表）。
> 下表为归属规划的最终形态；新增表请先对照本表确认 Owner。

## 二、归属规划

### system 模块

| 表 | 说明 |
| --- | --- |
| `sys_material` | 物料主数据（用 `material_type` 区分 RAW/PURCHASED/SEMI/FINISHED，无独立 product 表） |
| `sys_bom` / `sys_bom_item` | BOM 头与子项（转椅 BOM 为验证对象） |
| `sys_routing` / `sys_routing_operation` | 工艺路线头与工序 |
| `sys_organization` | 组织 / 部门 |
| `sys_personnel` | 员工（全系统唯一员工） |
| `sys_dictionary` / `sys_dictionary_item` | 基础字典与字典项 |
| `sys_user` / `sys_role` / `sys_permission` | 用户、角色、权限 |
| `sys_user_role` / `sys_role_permission` | 关联表 |
| `sys_operation_log` | 操作日志 |

### sales 模块

| 表 | 说明 |
| --- | --- |
| `sal_customer` | 客户 |
| `sal_forecast` | 销售预测 |
| `sal_order` / `sal_order_item` | 销售订单头与行 |
| `sal_shipment` / `sal_shipment_item` | 销售发货头与行 |
| `sal_return` / `sal_return_item` | 销售退货头与行 |

### planning 模块

| 表 | 说明 |
| --- | --- |
| `pln_demand` | 统一需求入口 |
| `pln_mps` / `pln_mps_item` | 主生产计划头与行（附录 1 MPS 录入于此） |
| `pln_mrp_run` | MRP 运算批次 |
| `pln_mrp_result` | MRP 运算结果 |
| `pln_production_plan` | 生产计划 |
| `pln_dispatch_order` | 派工单 |
| `pln_material_requisition` / `pln_material_requisition_item` | 领料单头与行 |
| `pln_completion_report` | 完工报告 |

### procurement 模块

| 表 | 说明 |
| --- | --- |
| `pur_supplier` | 供应商 |
| `pur_supplier_material` | 供应商-物料供应关系 |
| `pur_purchase_plan` / `pur_purchase_plan_item` | 采购计划头与行 |
| `pur_order` / `pur_order_item` | 采购订单头与行 |
| `pur_receipt` / `pur_receipt_item` | 到货登记头与行 |
| `pur_supplier_evaluation` | 供应商评价 |

### inventory 模块

| 表 | 说明 |
| --- | --- |
| `inv_warehouse` | 仓库 |
| `inv_location` | 库位 |
| `inv_balance` | 库存结存（实时库存状态） |
| `inv_transaction` | 库存流水（出入库明细） |
| `inv_replenishment_request` | 补库需求 |
| `inv_reorder_rule` | 订货点 |
| `inv_transfer` / `inv_transfer_item` | 移库头与行 |
| `inv_stocktake` / `inv_stocktake_item` | 库存盘点头与行 |

## 三、跨模块数据访问方式

| 场景 | 正确做法 | 错误做法 |
| --- | --- | --- |
| planning 需要销售需求 | 调用 sales 提供的 contract | 直接 `select` `sal_order` 表 |
| inventory 需要物料信息 | 调用 system 提供的 contract | 跨模块 JOIN `sys_material` |
| sales 需要可发货量 | 调用 inventory 提供的 contract | 直接读 `inv_balance` |

## 四、新增表的流程

1. 对照本文档确认该表的 Owner 是不是你负责的模块。
2. 不是 → **不要建这张表**，先找 Owner 模块的负责人沟通。
3. 是 → 在自己模块的 `models.py` 中定义模型（继承 `app.core.database.Base`）。
4. 生成迁移：`alembic revision --autogenerate -m "..."`（在 `backend/` 下执行）。
5. 在本文件中把新表补进对应模块的表格。
6. 迁移文件推送到 `develop` 后，其他人不得再修改该文件。

## 五、注意事项

- `sys_material` 这类基础主数据只有 system 模块可以写，其他模块只读。
- 库存数量只由 inventory 模块维护。其他模块看到的"库存"必须来自 inventory 的接口，
  不要在自己模块里另建一份库存字段长期缓存，否则数据一定不一致。
- 单据之间的关联（如采购订单行关联 MRP 结果行）统一使用 **ID 引用**（`<entity>_id`，类型 `BIGINT`）。
- **跨模块历史业务外键默认使用 `ON DELETE RESTRICT`**（规格 §20）：基础数据被业务引用后
  不允许物理删除，避免历史业务记录消失；如需停用请改为 `status = INACTIVE`。
- 例外：**多态引用**（如 `inv_transaction.source_reference_id`、`pur_purchase_plan_item.source_reference_id`
  可能指向不同模块的不同单据）只建索引，**不建物理外键**。
- 模块内部头-行关系使用真实外键；头-行从属关系允许 `ON DELETE CASCADE`
  （如 `sal_order_item.order_id`），删除单据头时一并清理明细。
