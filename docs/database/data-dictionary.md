# BH-ERP 数据字典（Data Dictionary）

> 本文档定义 BH-ERP 的**命名规范、键与关系规则、统一数据类型、约束原则、审计与追踪、
> 状态机、全部枚举值**，并给出每个约定在代码中的**落地位置**。
>
> - 事实来源：`backend/app/core/mixins.py`、`backend/app/shared/enums.py`、
>   `backend/app/modules/<module>/models.py`（`CHECK` 约束）、
>   `backend/app/modules/<module>/service.py`（错误码与状态机）
> - 规范依据：`docs/requirements/BH-ERP-完整开发规格.md` §18 ~ §25
> - 字段级清单见 [`physical-data-model.md`](./physical-data-model.md)
> - 实例统计：**52 张表 / 640 个字段 / 95 个外键 / 93 个 `CHECK` 约束**
>
> 本文只描述**代码里真实存在**的约定；凡规格中要求但当前未落地的项，均在文末
> 「八、尚未落地的约定」中显式说明。

## 一、命名规范（规格 §18）

### 1.1 库名

数据库名固定为 `bh_erp`，由 `backend/app/core/config.py` 的 `DB_NAME` 提供，
连接串由 `Settings.database_url` 拼装为 `mysql+pymysql://...`。

### 1.2 表名

- 全部为 `snake_case`，**必须带模块前缀**（无前缀的表一律视为违规）：

| 前缀 | 模块 | 表数 | 说明 |
| --- | --- | --- | --- |
| `sys_` | system | 15 | 组织、人员、用户、权限、字典、物料、BOM、工艺路线、日志 |
| `sal_` | sales | 8 | 客户、预测、订单、发货、退货（各含头/行） |
| `pln_` | planning | 10 | 需求、MPS、MRP、生产作业计划、派工、领料、完工 |
| `pur_` | procurement | 9 | 供应商、供应商-物料、采购计划、采购订单、到货、评价 |
| `inv_` | inventory | 10 | 仓库、库位、结存、流水、订货点、补库需求、移库、盘点 |

- 头/行表命名：`<entity>`（头）+ `<entity>_item`（行），如 `sal_order` / `sal_order_item`。
- 全库共 **52** 张表，`assert` 方式可在 `physical-data-model.md` 核对。

### 1.3 字段名

| 语义 | 命名 | 实例 |
| --- | --- | --- |
| 主键 | `id` | 所有表的 `id` |
| 外键 | `<entity>_id` | `material_id`、`customer_id`、`supplier_id` |
| 业务编码 | `<entity>_code` | `material_code`、`supplier_code`、`warehouse_code` |
| 业务单号 | `<entity>_no` | `order_no`、`plan_no`、`receipt_no`、`transaction_no` |
| 创建/更新时间 | `created_at` / `updated_at` | 见 `AuditMixin` |
| 创建/更新人 | `created_by` / `updated_by` | 见 `AuditMixin` |
| 状态 | `status` | 所有单据与基础数据 |
| 数量 | `<业务>_qty` / `quantity` | `planned_qty`、`received_qty`、`request_qty` |
| 金额 | `*_amount` / `*_price` | `total_amount`、`supply_price` |
| 比例 | `*_rate` | `scrap_rate` |
| 是否/日期 | `*_date` | `order_date`、`requirement_date` |

代码中**不存在**第二套命名风格（无驼峰表名、无 `is_xxx` 布尔前缀、无拼音命名）。

## 二、主键设计（规格 §19）

- 所有业务表统一 `id BIGINT PRIMARY KEY AUTO_INCREMENT`，由
  `mixins.BigIntPk = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]` 落地。
- 主键**仅作数据库内部唯一标识**，业务编码不得作主键。
- 业务编码为 `UNIQUE NOT NULL`，实际落地为列级 `unique=True` 或组合 `UniqueConstraint`，
  代码校验错误码见第五节。

配套的 `UniqueConstraint`（共 **42** 个，下表按模块汇总）：

| 表 | 唯一约束 | 字段 |
| --- | --- | --- |
| `sys_material` | `（自动命名）` | `material_code` |
| `sys_bom` | `uq_sys_bom_material_version` | `material_id, bom_version` |
| `sys_bom_item` | `uq_sys_bom_item` | `bom_id, material_id` |
| `sys_user` | `（自动命名）` | `username` |
| `sys_user` | `（自动命名）` | `personnel_id`（**FK + UNIQUE = 1:1**，见第四节） |
| `sys_personnel` | `（自动命名）` | `employee_no` |
| `sys_organization` | `（自动命名）` | `org_code` |
| `sys_role` | `（自动命名）` | `role_code` |
| `sys_permission` | `（自动命名）` | `perm_code` |
| `sys_dictionary` | `（自动命名）` | `dict_code` |
| `sys_dictionary_item` | `uq_sys_dictionary_item` | `dict_id, item_code` |
| `sys_user_role` | `uq_sys_user_role` | `user_id, role_id` |
| `sys_role_permission` | `uq_sys_role_permission` | `role_id, permission_id` |
| `sys_routing` | `uq_sys_routing_material_version` | `material_id, routing_version` |
| `sys_routing_operation` | `uq_sys_routing_operation_seq` | `routing_id, sequence_no` |
| `sal_customer` | `（自动命名）` | `customer_code` |
| `sal_order` | `（自动命名）` | `order_no` |
| `sal_order_item` | `uq_sal_order_item_line` | `order_id, line_no` |
| `sal_shipment` | `（自动命名）` | `shipment_no` |
| `sal_return` | `（自动命名）` | `return_no` |
| `sal_forecast` | `（自动命名）` | `forecast_no` |
| `pln_demand` | `（自动命名）` | `demand_no` |
| `pln_mps` | `（自动命名）` | `mps_no` |
| `pln_mrp_run` | `（自动命名）` | `run_no` |
| `pln_production_plan` | `（自动命名）` | `plan_no` |
| `pln_dispatch_order` | `（自动命名）` | `dispatch_no` |
| `pln_material_requisition` | `（自动命名）` | `req_no` |
| `pln_completion_report` | `（自动命名）` | `report_no` |
| `pur_supplier` | `（自动命名）` | `supplier_code` |
| `pur_supplier_material` | `uq_pur_supplier_material` | `supplier_id, material_id` |
| `pur_purchase_plan` | `（自动命名）` | `plan_no` |
| `pur_order` | `（自动命名）` | `order_no` |
| `pur_order_item` | `uq_pur_order_item_line` | `order_id, line_no` |
| `pur_receipt` | `（自动命名）` | `receipt_no` |
| `inv_warehouse` | `（自动命名）` | `warehouse_code` |
| `inv_location` | `uq_inv_location` | `warehouse_id, location_code` |
| `inv_balance` | `uq_inv_balance_bucket` | `warehouse_id, location_id, material_id` |
| `inv_transaction` | `（自动命名）` | `transaction_no` |
| `inv_transfer` | `（自动命名）` | `transfer_no` |
| `inv_stocktake` | `（自动命名）` | `stocktake_no` |
| `inv_replenishment_request` | `（自动命名）` | `request_no` |
| `inv_reorder_rule` | `uq_inv_reorder_rule` | `material_id, warehouse_id` |

> 「（自动命名）」表示代码里写的是 `unique=True` / `UniqueConstraint(...)` 未显式给名字，
> 由数据库自动命名；显式命名的约束名可在 `physical-data-model.md` 中逐表查看。

## 三、外键设计（规格 §20）

- 所有外键**引用对方表的 `id`**，类型 `BIGINT`（`mixins.BigIntFk`），不使用业务编码做外键。
- 跨模块历史业务外键默认 `ON DELETE RESTRICT`；头行子表允许 `ON DELETE CASCADE`。
- 实测分布（95 条外键）：

| `ON DELETE` | 条数 | 典型场景 |
| --- | --- | --- |
| `RESTRICT` | 见 [`full-er-diagram.md`](./full-er-diagram.md) 第四节 | 单据行 → 物料 / 客户 / 供应商 / 仓库等主数据 |
| `CASCADE` | 同上 | 单据行 → 本模块单头；仓库 → 库位；MRP 结果 → MRP 批次 |

- 已被业务引用的基础数据**不物理删除**，改为 `status = 'INACTIVE'`（见
  `shared/enums.py::RecordStatus`，以及各模块 `*_status` 接口）。
- **跨模块物理外键只有一类**：指向 `sys_material.id`（37 条）。其余跨模块关系一律走
  `contract.py` 接口，不建物理外键。

### 3.1 多态引用（不建物理外键的 `*_id`）

以下字段是按 `source_type` 分派目标的**多态引用**，只建索引、不建外键，
因此**不会**出现在 ER 图的连线上：

| 表 | 字段 | 类型 | 指向 |
| --- | --- | --- | --- |
| `inv_transaction` | `source_reference_id` | `BIGINT` | 来源单据（由 `source_module` + `source_type` 决定） |
| `inv_replenishment_request` | `handled_ref_id` | `BIGINT` | 受理单据（采购计划行 / 生产作业计划） |
| `pln_demand` | `source_reference_id` | `INTEGER` | `sal_order` / `inv_replenishment_request` 等 |
| `pln_production_plan` | `source_reference_id` | `INTEGER` | `pln_mrp_result` / `inv_replenishment_request` 等 |
| `pur_purchase_plan_item` | `source_reference_id` | `INTEGER` | `pln_mrp_result` / `inv_replenishment_request` |
| `sys_operation_log` | `target_id` | `BIGINT` | 被操作对象（由 `target_type` 决定表名） |
| `sys_operation_log` | `operator_id` | `BIGINT` | `sys_user.id`（弱引用） |
| `inv_transaction` | `operator_id` | `BIGINT` | `sys_user.id`（弱引用） |
| `sys_organization` | `manager_id` | `BIGINT` | `sys_personnel.id`（延迟引用，避免建表循环） |
| 所有 `AuditMixin` 表 | `created_by` / `updated_by` | `BIGINT` | `sys_user.id`（弱引用，见 `mixins.AuditMixin` 注释） |

> **已知不一致（如实记录）**：`pln_demand`、`pln_production_plan`、`pur_purchase_plan_item`
> 的 `source_reference_id` 落地为 `INTEGER`，而 `inv_transaction` 的同名字段为 `BIGINT`。
> 这三处均非 PK/FK，故不受 §22「PK/FK 用 BIGINT」约束，但同名字段类型不统一，
> 属于可收敛项（见文末「八」）。

## 四、关系规则（规格 §21）

| 关系 | 落地方式 | 本库实例 |
| --- | --- | --- |
| 1:1 | `FK + UNIQUE` | **1 个实例**：`sys_user.personnel_id → sys_personnel.id`（外键 + 单列唯一，可空；列注释即「关联员工ID（1:1，可为空）」）。全库仅此一处 |
| 1:N | 外键放在 N 端 | 95 条外键中 **94 条**为 1:N，如 `sal_order 1:N sal_order_item`（`sal_order_item.order_id`）、`sys_material 1:N sys_bom`（`sys_bom.material_id`） |
| N:M | 必须用关联表 | `sys_user_role`（用户 N:M 角色）、`sys_role_permission`、`pur_supplier_material`（供应商 N:M 物料） |

禁止把多个 ID 塞进一个 `VARCHAR` 字段——全库无此写法。

## 五、统一数据类型（规格 §22）

| 语义 | 物理类型 | 代码别名（`app/core/mixins.py`） |
| --- | --- | --- |
| PK / FK | `BIGINT` | `BigIntPk` / `BigIntFk` |
| 业务编码 / 单号 | `VARCHAR(50)` | `CodeStr` |
| 名称 | `VARCHAR(100)` | `NameStr` |
| 状态 / 枚举 | `VARCHAR(20)` | `StatusStr` |
| 数量 | `DECIMAL(18,4)` | `Quantity` |
| 金额 | `DECIMAL(18,2)` | `Money` |
| 比例（损耗率） | `DECIMAL(8,4)` | `Ratio` |
| 业务日期 | `DATE` | SQLAlchemy `Date` |
| 时间戳 | `DATETIME` | SQLAlchemy `DateTime` |
| 长描述 | `TEXT` / `VARCHAR(200)` / `VARCHAR(500)` | 备注类字段 |

- **禁止用 `FLOAT` 存数量与金额**：全库 640 个字段中没有任何浮点类型。
- 备注类字段用语不统一（`TEXT` 与 `VARCHAR(200)` 并存），如 `inv_stocktake_item.remark`
  为 `VARCHAR(200)`，其余多为 `TEXT`；两者均在 §22 允许范围内（「长描述: VARCHAR(500) / TEXT」）。

## 六、约束（规格 §23）

- 全库 **93** 个 `CHECK` 约束，分三类：

| 类别 | 示例 | 说明 |
| --- | --- | --- |
| 枚举合法性 | `ck_sys_material_type`：`material_type IN ('RAW','PURCHASED','SEMI','FINISHED')` | 所有状态/类型字段都有 `IN (...)` 约束，与 `shared/enums.py` 一一对应 |
| 非负性 | `ck_inv_balance_qty`：`quantity >= 0` | 数量、金额、评分、提前期等 |
| 正值性 | `ck_inv_repl_qty`：`request_qty > 0` | 单据行数量必须为正 |
| 区间 | `ck_pur_eval_quality`：`quality_score >= 0 AND quality_score <= 100` | 评分 0~100 |
| 比例区间 | `ck_sys_bom_item_scrap`：`scrap_rate >= 0 AND scrap_rate < 1` | 损耗率 |

- **例外**：`inv_transaction.quantity_change` 同时允许正数与负数（入库为正、出库为负），
  因此**没有** `>= 0` 约束；相应的非负保证由结存表承担
  （`ck_inv_balance_qty: quantity >= 0`、`ck_inv_balance_locked: locked_quantity >= 0`）。
- 状态禁止用 `0/1/2/3` 魔法数字：全库状态列均为 `VARCHAR(20)` + `CHECK`。

## 七、审计与追踪（规格 §24）

### 7.1 审计列

`AuditMixin`（= `TimestampMixin` + 操作人）提供 4 列，落在 **49** 张表上：
`sys_user_role`、`sys_role_permission` 为纯关联表（仅 `id` + 两个外键），
`sys_operation_log` 为只追加的日志表（仅保留 `created_at`，注释为「发生时间」），
这三张表未使用该 Mixin。

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `created_at` | `DATETIME` | 否 | `datetime.now`（应用侧） | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `datetime.now` + `onupdate` | 更新时间 |
| `created_by` | `BIGINT` | 是 | — | 创建人ID（指向 `sys_user.id`，不建外键） |
| `updated_by` | `BIGINT` | 是 | — | 更新人ID（同上） |

### 7.2 操作日志

重要业务动作写入 `sys_operation_log`，由 system 模块 `contract.log_operation(...)` 统一提供，
其他模块只允许通过该契约调用。日志字段包含 `module / action / target_type / target_id /
operator_id / detail`（`target_id` 为多态引用，无物理外键）。

### 7.3 库存可追溯（强制）

任何库存变动都必须能回答「来自哪张单据」：

| 列 | 说明 |
| --- | --- |
| `source_module` | 来源模块（`system` / `sales` / `planning` / `procurement` / `inventory`） |
| `source_type` | 来源业务类型，取值见 `InventorySourceType` |
| `source_reference_id` | 来源单据主键（多态引用） |
| `source_no` | 来源单号（冗余，便于查询） |

并且：**改库存必须同时写 `inv_transaction` 流水和更新 `inv_balance` 结存**，
二者在同一事务内完成；库存变动统一经 `inventory.contract.increase_stock / decrease_stock`
（禁止其他模块直接写 `inv_balance`）。

## 八、状态机（规格 §25）

### 8.1 基础状态枚举

`shared/enums.py::DocStatus` 定义 6 个基础状态，各业务表**取适合自己的子集**，
并由 `CHECK` 约束限定：

| 值 | 含义 |
| --- | --- |
| `DRAFT` | 草稿，可自由修改与删除 |
| `CONFIRMED` | 已确认，业务数据锁定 |
| `RELEASED` | 已下达 |
| `IN_PROGRESS` | 执行中 |
| `COMPLETED` | 已完成（终态，不可修改） |
| `CANCELLED` | 已取消（终态） |

### 8.2 各表实际允许的状态（来自 `CHECK` 约束）

| 表 | 允许状态 |
| --- | --- |
| `sys_material`、`sys_bom`、`sys_organization`、`sys_personnel`、`sys_user`、`sys_role`、`sys_permission`、`sys_dictionary`、`sys_dictionary_item`、`sys_routing`、`sal_customer`、`pur_supplier`、`inv_warehouse`、`inv_location`、`inv_reorder_rule` | `ACTIVE`、`INACTIVE` |
| `sal_forecast` | `DRAFT`、`CONFIRMED`、`COMPLETED`、`CANCELLED` |
| `sal_order` | `DRAFT`、`CONFIRMED`、`RELEASED`、`IN_PROGRESS`、`COMPLETED`、`CANCELLED` |
| `sal_shipment`、`sal_return` | `DRAFT`、`CONFIRMED`、`COMPLETED`、`CANCELLED` |
| `pln_demand` | `DRAFT`、`CONFIRMED`、`RELEASED`、`COMPLETED`、`CANCELLED` |
| `pln_mps`、`pln_mps_item`、`pln_production_plan`、`pln_dispatch_order`、`pln_material_requisition` | `DRAFT`、`CONFIRMED`、`RELEASED`、`IN_PROGRESS`、`COMPLETED`、`CANCELLED` |
| `pln_mrp_run` | `DRAFT`、`IN_PROGRESS`、`COMPLETED`、`CANCELLED` |
| `pln_mrp_result` | `DRAFT`、`CONFIRMED`、`RELEASED`、`COMPLETED`、`CANCELLED` |
| `pln_completion_report` | `DRAFT`、`CONFIRMED`、`COMPLETED`、`CANCELLED` |
| `pur_purchase_plan`、`pur_purchase_plan_item` | `DRAFT`、`CONFIRMED`、`RELEASED`、`COMPLETED`、`CANCELLED` |
| `pur_order` | `DRAFT`、`CONFIRMED`、`RELEASED`、`IN_PROGRESS`、`COMPLETED`、`CANCELLED` |
| `pur_receipt` | `DRAFT`、`CONFIRMED`、`COMPLETED`、`CANCELLED` |
| `inv_transfer`、`inv_stocktake` | `DRAFT`、`CONFIRMED`、`COMPLETED`、`CANCELLED` |
| `inv_replenishment_request` | `DRAFT`、`CONFIRMED`、`RELEASED`、`COMPLETED`、`CANCELLED` |

### 8.3 状态流转规则（来自各模块 `service.py` 的 `*_TRANSITIONS` 字典）

| 单据 | 状态机 | 代码位置 |
| --- | --- | --- |
| 主单据（MPS / 生产作业计划 / 派工单 / 领料单） | `DRAFT→CONFIRMED→RELEASED→IN_PROGRESS→COMPLETED`，`DRAFT/CONFIRMED/RELEASED/IN_PROGRESS→CANCELLED` | `planning/service.py::_MAIN_TRANSITIONS` |
| 需求 `pln_demand` | `DRAFT→CONFIRMED`；`CONFIRMED→RELEASED/COMPLETED`；`RELEASED→COMPLETED`；可 `CANCELLED` | `planning/service.py::_DEMAND_TRANSITIONS` |
| 销售订单 `sal_order` | `DRAFT→CONFIRMED`；`CONFIRMED→IN_PROGRESS`；`IN_PROGRESS→COMPLETED`；`DRAFT/CONFIRMED→CANCELLED`（`IN_PROGRESS` **不可取消**） | `sales/service.py::_ORDER_TRANSITIONS` |
| 采购计划 `pur_purchase_plan` | `DRAFT→CONFIRMED→RELEASED→COMPLETED`，可 `CANCELLED` | `procurement/service.py::_PLAN_TRANSITIONS` |
| 采购订单 `pur_order` | `DRAFT→CONFIRMED→RELEASED→IN_PROGRESS→COMPLETED`；`DRAFT/CONFIRMED/RELEASED→CANCELLED` | `procurement/service.py::_ORDER_TRANSITIONS` |

### 8.4 关键校验（不只是 CRUD）

| 动作 | 真实校验 |
| --- | --- |
| 确认发货 | 订单状态必须 ∈ `{CONFIRMED, IN_PROGRESS}`；发货数量 ≤ 未发数量（错误码 `2003`）；调用 `inventory.decrease_stock`（库存不足 → `5001`） |
| 确认退货 | 退货单客户必须与原订单一致（`2004`）；调用 `inventory.increase_stock` |
| 确认到货 | 采购订单状态 ∈ `{CONFIRMED, RELEASED, IN_PROGRESS}`；到货数量 ≤ 未到货数量（`4004`）；调用 `inventory.increase_stock` |
| 确认领料 | 调用 `inventory.decrease_stock`（库存不足 → `5001`） |
| 确认完工 | 调用 `inventory.increase_stock` |
| 确认盘点 | 差异通过 `ADJUST` 流水调整；调整后为负 → `5006` |
| 确认补库需求 | `REORDER` → `procurement.contract`；`PRODUCTION` → `planning.contract` |
| 确认 MPS 导入 / 物料导入 / BOM 导入 / 期初库存导入 | 先 `preview` 校验、再 `confirm` 落库；校验失败 → `3007` / `1011` / `1012` |

## 九、枚举值全集

### 9.1 跨模块共享枚举（`backend/app/shared/enums.py`）

| 枚举 | 值 | 含义 | 落地位置 |
| --- | --- | --- | --- |
| `ModuleName` | `system` / `sales` / `planning` / `procurement` / `inventory` | 五个模块标识 | `source_module`（`inv_transaction`）、操作日志 `module` |
| `ModuleStatus` | `up` / `down` | 模块健康状态 | 各模块 `/health` |
| `AppStatus` | `ok` / `degraded` | 应用级状态 | `/health` |
| `RecordStatus` | `ACTIVE` / `INACTIVE` | 基础数据启用状态 | `sys_*`、`sal_customer`、`pur_supplier`、`inv_warehouse`、`inv_location`、`inv_reorder_rule` 的 `status` |
| `MaterialType` | `RAW` / `PURCHASED` / `SEMI` / `FINISHED` | 原材料 / 采购件 / 半成品 / 成品 | `sys_material.material_type` |
| `SupplyType` | `MAKE` / `BUY` | 自制 / 采购，决定 MRP 分流 | `sys_material.supply_type`、`pln_mrp_result.supply_type` |
| `DocStatus` | `DRAFT` / `CONFIRMED` / `RELEASED` / `IN_PROGRESS` / `COMPLETED` / `CANCELLED` | 单据基础状态机 | 各单据 `status` |
| `InventoryTxnType` | `IN` / `OUT` / `TRANSFER_IN` / `TRANSFER_OUT` / `ADJUST` | 入库 / 出库 / 移库入 / 移库出 / 盘点调整 | `inv_transaction.transaction_type` |
| `InventorySourceType` | `PURCHASE_RECEIPT` / `PRODUCTION_COMPLETION` / `MATERIAL_REQUISITION` / `SALES_SHIPMENT` / `SALES_RETURN` / `TRANSFER` / `STOCKTAKE` / `MANUAL` | 库存流水来源业务 | `inv_transaction.source_type` |
| `ReplenishmentSource` | `REORDER` / `PRODUCTION` | 订货点补货 / 生产补库 | `inv_replenishment_request.source_type` |
| `MrpSourceType` | `SALES` / `STOCKFILL` / `MPS` | 需求来源：销售 / 补库 / 主生产计划 | `pln_demand.source_type` |

### 9.2 模块内业务枚举（未进 `shared/enums.py`，仅单模块使用）

| 归属 | 字段 | 值 | 含义 | 代码位置 |
| --- | --- | --- | --- | --- |
| system | `sys_organization.org_type` | `COMPANY` / `FACTORY` / `DEPARTMENT` / `WORKSHOP` / `WAREHOUSE` | 公司 / 工厂 / 部门 / 车间 / 仓库 | `system/service.py::_ORG_TYPES` + `ck_sys_organization_type` |
| system | `sys_permission.perm_type` | `MENU` / `PAGE` / `ACTION` | 菜单 / 页面 / 操作权限点 | `system/service.py::_PERM_TYPES` + `ck_sys_permission_type` |
| sales | `sal_return_item.quality_status` | `QUALIFIED` / `DEFECTIVE` / `SCRAP` | 合格 / 不良 / 报废 | `sales/service.py::_QUALITY_STATUSES` + `ck_sal_return_item_quality` |
| planning | `pln_production_plan.source_type` | `MRP` / `REPLENISHMENT` / `MANUAL` | 来源：MRP / 补库 / 手工 | `ck_pln_production_plan_source` |
| procurement | `pur_purchase_plan_item.source_type` | `MRP` / `REORDER` / `MANUAL` | 来源：MRP / 补库 / 手工 | `procurement/service.py::_PLAN_SOURCE_TYPES` + `ck_pur_plan_item_source` |

> `inv_replenishment_request.status` 与 `pur_receipt` / `sal_shipment` / `sal_return` /
> `pln_completion_report` / `inv_transfer` / `inv_stocktake` 等「确认即生效」的单据都只使用
> `DRAFT / CONFIRMED / COMPLETED / CANCELLED` 四态子集，不使用 `RELEASED`、`IN_PROGRESS`。

## 十、业务编码 / 单号生成规则

| 模块 | 对象 | 规则 | 代码位置 |
| --- | --- | --- | --- |
| system | BOM / 工艺路线 | `BOM` + 6 位序号、`RT` + 6 位序号 | `system/service.py`（`repo.next_no`，`system/repository.py::next_no`） |
| sales | 销售订单 / 发货单 / 退货单 / 预测单 | `SO`+`yyyyMMdd`、`SH`+`yyyyMMdd`、`RT`+`yyyyMMdd`、`FC`+`yyyyMMdd`，各补 4 位序号 | `sales/service.py::_order_no/_shipment_no/_return_no`、`创建预测` (`FC{date.today():%Y%m%d}`, `sales/repository.py::next_no`) |
| planning | 需求 / MPS / MRP批次 / 生产作业计划 / 派工单 / 领料单 / 完工报告 | `DEM` / `MPS` / `MRP` / `PLN` / `DSP` / `REQ` / `CRP` + 6 位序号 | `planning/service.py::_unique_no`、`planning/repository.py::next_no` |
| procurement | 采购计划 / 采购订单 / 到货单 | `PP`+`yyyyMMdd`、`PO`+`yyyyMMdd`、`PR`+`yyyyMMdd`，补 4 位序号 | `procurement/service.py`（`procurement/repository.py::next_no`） |
| inventory | 库存流水 / 移库单 / 盘点单 / 补库需求 | `INV`/`TRF`/`STK`/`RPL` + `yyyyMMdd` + 4 位序号 | `inventory/repository.py::next_txn_no`、`_next_doc_no` |

> 物料编码（`sys_material.material_code`）与人员工号（`sys_personnel.employee_no`）
> **不由系统生成**，来自课程数据导入或人工录入，仅做唯一性校验。

## 十一、尚未落地的约定（显式说明）

为避免「文档写一套、代码实现另一套」，以下项目前**没有**实现，特此列明：

1. **`source_reference_id` 类型不统一**：见第三节「已知不一致」；
   `pln_demand` / `pln_production_plan` / `pur_purchase_plan_item` 用 `INTEGER`，
   `inv_transaction` 用 `BIGINT`。
2. **`sys_bom.bom_code`、`sys_routing.routing_code` 没有唯一约束**：
   §19 要求业务编码 `UNIQUE NOT NULL`，这两列实为 `NOT NULL` 但**未加唯一约束**；
   代码侧也只校验了 BOM/工艺的「物料 + 版本」唯一（错误码 `1002` / `1007`），
   没有校验 `bom_code` / `routing_code` 自身唯一。数据库与代码均无冲突拦截。
3. **注释类字段类型不统一**：`TEXT` 与 `VARCHAR(200)` 并存。
4. **序列号生成是演示级实现**：`next_no` 采用「计数 + 1」，
   高并发下会有单号冲突（`inv_transaction` 已做保存点重试一次），生产环境应换独立序列。
5. **登录是简化版**：`POST /api/v1/system/auth/login` 为演示级登录，
   未实现真正的令牌体系（`sys_user.password_hash` 字段已存在）。
6. **`Base.metadata` 与迁移的漂移检查**：约定用 `alembic check`，
   但仓库中**未提供**自动化 CI 脚本来强制校验（见
   [`../development/database-migration-guide.md`](../development/database-migration-guide.md)）。