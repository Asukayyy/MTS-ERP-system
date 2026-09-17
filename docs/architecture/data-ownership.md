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
6. 表名使用小写下划线命名，建议加模块前缀以避免歧义（例如 `sales_order`、`inv_balance`）。

> **本阶段不创建任何业务表。** 下面只是归属规划，供后续开发时对照。

## 二、归属规划

### system 模块

| 表 | 说明 |
| --- | --- |
| `product` | 产品（成品 / 半成品）主数据 |
| `material` | 物料主数据 |
| `bom` / `bom_line` | BOM 头与行（转椅 BOM 为验证对象） |
| `routing` / `routing_step` | 工艺路线头与工序 |
| `organization` | 组织 / 部门 |
| `user` / `role` / `permission` | 用户、角色、权限 |
| `user_role` / `role_permission` | 关联表 |
| `dictionary` | 基础字典 |
| `operation_log` | 操作日志 |

### sales 模块

| 表 | 说明 |
| --- | --- |
| `customer` | 客户 |
| `sales_forecast` | 销售预测 |
| `sales_order` / `sales_order_line` | 销售订单头与行 |
| `shipment` | 销售发货 |

### planning 模块

| 表 | 说明 |
| --- | --- |
| `mps` / `mps_line` | 主生产计划头与行（附录 1 MPS 录入于此） |
| `mrp_result` | MRP 运算结果 |
| `planned_order` | 计划订单 |
| `production_work_plan` | 生产作业计划 |
| `dispatch_order` | 派工单 |
| `material_requisition` / `material_requisition_line` | 领料单头与行 |

### procurement 模块

| 表 | 说明 |
| --- | --- |
| `supplier` | 供应商 |
| `purchase_plan` / `purchase_plan_line` | 采购计划头与行 |
| `purchase_order` / `purchase_order_line` | 采购订单头与行 |
| `receiving` / `receiving_line` | 到货登记头与行 |

### inventory 模块

| 表 | 说明 |
| --- | --- |
| `warehouse` | 仓库 |
| `location` | 库位 |
| `inventory_balance` | 库存结存（实时库存状态） |
| `inventory_transaction` | 库存流水（出入库明细） |
| `inventory_check` / `inventory_check_line` | 库存盘点（可选） |

## 三、跨模块数据访问方式

| 场景 | 正确做法 | 错误做法 |
| --- | --- | --- |
| planning 需要销售需求 | 调用 sales 提供的 contract | 直接 `select` `sales_order` 表 |
| inventory 需要物料信息 | 调用 system 提供的 contract | 跨模块 JOIN `material` |
| sales 需要可发货量 | 调用 inventory 提供的 contract | 直接读 `inventory_balance` |

## 四、新增表的流程

1. 对照本文档确认该表的 Owner 是不是你负责的模块。
2. 不是 → **不要建这张表**，先找 Owner 模块的负责人沟通。
3. 是 → 在自己模块的 `models.py` 中定义模型（继承 `app.core.database.Base`）。
4. 生成迁移：`alembic revision --autogenerate -m "..."`（在 `backend/` 下执行）。
5. 在本文件中把新表补进对应模块的表格。
6. 迁移文件推送到 `develop` 后，其他人不得再修改该文件。

## 五、注意事项

- `product` / `material` 这类基础主数据只有 system 模块可以写，其他模块只读。
- 库存数量只由 inventory 模块维护。其他模块看到的"库存"必须来自 inventory 的接口，
  不要在自己模块里另建一份库存字段长期缓存，否则数据一定不一致。
- 单据之间的关联（如采购订单行关联 MRP 结果行）使用 **ID 引用**，不要用跨模块外键约束，
  保持模块之间在数据库层面的解耦。
