# BH-ERP 物理数据模型（Physical Data Model）

> **生成方式**：本文档由脚本内省**真实 SQLAlchemy 元数据**
> （`app.core.database.Base.metadata`，运行时已导入 5 个模块的 `models.py`）后自动生成，
> 字段名、类型、可空性、默认值、主键、外键、`ON DELETE` 行为、唯一约束、`CHECK` 约束、
> 索引全部**逐字取自代码**，不存在手工誊写造成的偏差。
>
> - 唯一事实来源：`backend/app/modules/<module>/models.py`
> - 建库迁移（基线）：`backend/migrations/versions/9e6fa0de8416_baseline_schema_for_five_modules.py`
> - 增量迁移：`backend/migrations/versions/f5e52ee720d6_add_lead_time_offset_return_quality_.py`
> - 内省范围统计：**52 张表 / 640 个字段 / 95 个外键 / 93 个 CHECK 约束**
>
> 若本文档与代码不一致，**以代码为准**，并请按 `docs/development/database-migration-guide.md`
> 的流程修正迁移后重新生成本文档。

## 一、类型与审计列约定

所有列类型来自 `backend/app/core/mixins.py` 中的类型别名，业务表**统一复用**，不单独定义：

| 逻辑类型 | 物理类型 | 代码定义（`app/core/mixins.py`） | 用途 |
| --- | --- | --- | --- |
| 主键 | `BIGINT` | `BigIntPk`（`primary_key=True, autoincrement=True`） | 所有业务表的 `id` |
| 外键 | `BIGINT` | `BigIntFk` | 统一指向对方表的 `id` |
| 业务编码/单号 | `VARCHAR(50)` | `CodeStr` | `*_code` / `*_no` |
| 名称 | `VARCHAR(100)` | `NameStr` | `*_name` |
| 状态/枚举 | `VARCHAR(20)` | `StatusStr` | `status`、`*_type` |
| 数量 | `DECIMAL(18,4)` | `Quantity` | 所有数量字段 |
| 金额 | `DECIMAL(18,2)` | `Money` | 所有金额字段 |
| 比例 | `DECIMAL(8,4)` | `Ratio` | 损耗率等 |
| 业务日期 | `DATE` | SQLAlchemy `Date` | 单据日期 |
| 时间戳 | `DATETIME` | SQLAlchemy `DateTime` | 审计时间 |

**审计列**（`AuditMixin` = `TimestampMixin` + 操作人）：

| 列名 | 类型 | 可空 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `created_at` | `DATETIME` | 否 | 应用侧 `datetime.now()` | 创建时间 |
| `updated_at` | `DATETIME` | 否 | 应用侧 `datetime.now()`，并在 UPDATE 时自动刷新 | 更新时间 |
| `created_by` | `BIGINT` | 是 | — | 创建人ID，**指向 `sys_user.id` 但不建外键**（框架层解耦） |
| `updated_by` | `BIGINT` | 是 | — | 更新人ID，同上 |

> 注：`sys_user_role`、`sys_role_permission` 关联表未继承审计 Mixin，列较少。

## 二、表清单

| 模块 | 前缀 | 表数 | 表名 |
| --- | --- | --- | --- |
| 系统基础数据（system） | `sys_` | 15 | `sys_bom`、`sys_bom_item`、`sys_dictionary`、`sys_dictionary_item`、`sys_material`、`sys_operation_log`、`sys_organization`、`sys_permission`、`sys_personnel`、`sys_role`、`sys_role_permission`、`sys_routing`、`sys_routing_operation`、`sys_user`、`sys_user_role` |
| 销售管理（sales） | `sal_` | 8 | `sal_customer`、`sal_forecast`、`sal_order`、`sal_order_item`、`sal_return`、`sal_return_item`、`sal_shipment`、`sal_shipment_item` |
| 计划管理（planning） | `pln_` | 10 | `pln_completion_report`、`pln_demand`、`pln_dispatch_order`、`pln_material_requisition`、`pln_material_requisition_item`、`pln_mps`、`pln_mps_item`、`pln_mrp_result`、`pln_mrp_run`、`pln_production_plan` |
| 采购管理（procurement） | `pur_` | 9 | `pur_order`、`pur_order_item`、`pur_purchase_plan`、`pur_purchase_plan_item`、`pur_receipt`、`pur_receipt_item`、`pur_supplier`、`pur_supplier_evaluation`、`pur_supplier_material` |
| 库存管理（inventory） | `inv_` | 10 | `inv_balance`、`inv_location`、`inv_reorder_rule`、`inv_replenishment_request`、`inv_stocktake`、`inv_stocktake_item`、`inv_transaction`、`inv_transfer`、`inv_transfer_item`、`inv_warehouse` |
| **合计** | — | **52** | — |

各表字段数与外键数：

| 表名 | ORM 类 | 说明 | 字段数 | 外键数 | 主键 |
| --- | --- | --- | --- | --- | --- |
| `inv_balance` | `InvBalance` | 库存结存：某仓库/库位下某物料的当前数量 | 11 | 3 | `id` |
| `inv_location` | `InvLocation` | 库位（仓库下的具体存放位置） | 10 | 1 | `id` |
| `inv_reorder_rule` | `InvReorderRule` | 订货点规则：库存低于 `reorder_point` 时触发补库建议 | 11 | 2 | `id` |
| `inv_replenishment_request` | `InvReplenishmentRequest` | 补库需求单 | 17 | 2 | `id` |
| `inv_stocktake` | `InvStocktake` | 库存盘点单头 | 10 | 1 | `id` |
| `inv_stocktake_item` | `InvStocktakeItem` | 盘点明细行：账面数 vs 实盘数，差异通过 `ADJUST` 流水调整 | 12 | 3 | `id` |
| `inv_transaction` | `InvTransaction` | 库存流水（出入库明细）—— 库存变动的唯一入口与审计凭证 | 20 | 3 | `id` |
| `inv_transfer` | `InvTransfer` | 移库单头：仓库/库位之间的库存移动 | 11 | 2 | `id` |
| `inv_transfer_item` | `InvTransferItem` | 移库明细行 | 11 | 4 | `id` |
| `inv_warehouse` | `InvWarehouse` | 仓库 | 12 | 2 | `id` |
| `pln_completion_report` | `PlnCompletionReport` | 完工报告：生产完工报工（确认后走 inventory 入库，增加半成品/成品库存） | 17 | 5 | `id` |
| `pln_demand` | `PlnDemand` | 统一需求入口：合并销售需求 / 库存补库需求 / MPS 需求 | 14 | 1 | `id` |
| `pln_dispatch_order` | `PlnDispatchOrder` | 派工单：把作业计划下达到具体工序 / 作业人员 | 15 | 2 | `id` |
| `pln_material_requisition` | `PlnMaterialRequisition` | 领料单头：生产领料的申请与执行（执行时走 inventory 出库） | 11 | 2 | `id` |
| `pln_material_requisition_item` | `PlnMaterialRequisitionItem` | 领料单行。`issued_qty` 由实际出库回写 | 11 | 3 | `id` |
| `pln_mps` | `PlnMps` | 主生产计划头 | 13 | 0 | `id` |
| `pln_mps_item` | `PlnMpsItem` | 主生产计划行：某成品在某期间的计划生产量 | 14 | 2 | `id` |
| `pln_mrp_result` | `PlnMrpResult` | MRP 运算结果：BOM 逐层展开后的毛需求 / 可用库存 / 净需求 / 建议下达 | 21 | 3 | `id` |
| `pln_mrp_run` | `PlnMrpRun` | MRP 运算批次：一次运算的上下文与结果归属 | 11 | 1 | `id` |
| `pln_production_plan` | `PlnProductionPlan` | 车间生产作业计划：承接 MRP 自制（MAKE）需求 | 17 | 2 | `id` |
| `pur_order` | `PurOrder` | 采购订单头 | 13 | 2 | `id` |
| `pur_order_item` | `PurOrderItem` | 采购订单行。`received_qty` 由到货流程回写 | 13 | 2 | `id` |
| `pur_purchase_plan` | `PurPurchasePlan` | 采购计划头：集中承载待采购需求的建议 | 9 | 0 | `id` |
| `pur_purchase_plan_item` | `PurPurchasePlanItem` | 采购计划行：来源可以是 MRP 结果或库存补库需求 | 15 | 3 | `id` |
| `pur_receipt` | `PurReceipt` | 到货登记单头。确认后必须调用 inventory 入库并生成库存流水 | 12 | 3 | `id` |
| `pur_receipt_item` | `PurReceiptItem` | 到货明细行 | 12 | 4 | `id` |
| `pur_supplier` | `PurSupplier` | 供应商主数据 | 13 | 0 | `id` |
| `pur_supplier_evaluation` | `PurSupplierEvaluation` | 供应商评价：质量 / 交期 / 价格 三类评分 | 13 | 2 | `id` |
| `pur_supplier_material` | `PurSupplierMaterial` | 供应商 N:M 物料 关联表（含供货价与供货提前期） | 12 | 2 | `id` |
| `sal_customer` | `SalCustomer` | 客户主数据 | 14 | 0 | `id` |
| `sal_forecast` | `SalForecast` | 销售预测：按月对某物料的预测量，是 Planning 的需求来源之一 | 12 | 2 | `id` |
| `sal_order` | `SalOrder` | 销售订单头 | 13 | 2 | `id` |
| `sal_order_item` | `SalOrderItem` | 销售订单行。`delivered_qty` 由发货流程回写 | 13 | 2 | `id` |
| `sal_return` | `SalReturn` | 销售退货单头。确认退货时调用 inventory 接口入库 | 12 | 2 | `id` |
| `sal_return_item` | `SalReturnItem` | 退货明细行 | 13 | 4 | `id` |
| `sal_shipment` | `SalShipment` | 销售发货单头。确认发货时调用 inventory 接口出库 | 11 | 2 | `id` |
| `sal_shipment_item` | `SalShipmentItem` | 发货明细行 | 12 | 5 | `id` |
| `sys_bom` | `SysBom` | BOM 头：某物料在某个版本下的组成关系。`(material_id, bom_version)` 唯一 | 13 | 1 | `id` |
| `sys_bom_item` | `SysBomItem` | BOM 子项：母件 → 子件，含数量与损耗率（支持多层展开） | 12 | 2 | `id` |
| `sys_dictionary` | `SysDictionary` | 数据字典（计量单位、物料分类等基础枚举的可维护来源） | 9 | 0 | `id` |
| `sys_dictionary_item` | `SysDictionaryItem` | 字典项 | 11 | 1 | `id` |
| `sys_material` | `SysMaterial` | **全系统唯一物料主表** | 17 | 0 | `id` |
| `sys_operation_log` | `SysOperationLog` | 操作日志：记录关键业务动作，便于审计追踪 | 8 | 0 | `id` |
| `sys_organization` | `SysOrganization` | 组织 / 部门（树形，`parent_id` 自引用） | 12 | 1 | `id` |
| `sys_permission` | `SysPermission` | 权限点：菜单 / 页面 / 关键操作（树形） | 13 | 1 | `id` |
| `sys_personnel` | `SysPersonnel` | 企业员工（全系统唯一人员表） | 14 | 1 | `id` |
| `sys_role` | `SysRole` | 角色（规格 §30：System Administrator / Sales User / Planner / Buyer / Warehouse User） | 9 | 0 | `id` |
| `sys_role_permission` | `SysRolePermission` | 角色 N:M 权限 关联表 | 3 | 2 | `id` |
| `sys_routing` | `SysRouting` | 工艺路线头：某自制件的加工工序集合 | 10 | 1 | `id` |
| `sys_routing_operation` | `SysRoutingOperation` | 工艺路线工序行 | 13 | 1 | `id` |
| `sys_user` | `SysUser` | 软件登录账号（与 Personnel 分离：一个 Personnel 可有 0 或 1 个 User） | 12 | 1 | `id` |
| `sys_user_role` | `SysUserRole` | 用户 N:M 角色 关联表（规格 §21，禁止把多个 ID 塞进 VARCHAR） | 3 | 2 | `id` |

## 三、逐表字段说明

### 3.1 系统基础数据 模块（`sys_`，共 15 张表）

#### `sys_bom` — BOM 头：某物料在某个版本下的组成关系。`(material_id, bom_version)` 唯一

- ORM 类：`SysBom`（`backend/app/modules/system/models.py`）
- 字段数：13；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `bom_code` | `VARCHAR(50)` | 否 | — | — | BOM编码 |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 母件物料ID（sys_material.id） |
| `bom_version` | `VARCHAR(20)` | 否 | `'V1.0'` | — | BOM版本 |
| `effective_date` | `DATE` | 是 | — | — | 生效日期 |
| `expiry_date` | `DATE` | 是 | — | — | 失效日期 |
| `is_active` | `BOOLEAN` | 否 | `true` | — | 是否当前激活版本 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_sys_bom_material_version` | `material_id,bom_version` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sys_bom_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_bom_material_id` | `material_id` | 否 |

#### `sys_bom_item` — BOM 子项：母件 → 子件，含数量与损耗率（支持多层展开）

- ORM 类：`SysBomItem`（`backend/app/modules/system/models.py`）
- 字段数：12；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `bom_id` | `BIGINT` | 否 | — | FK → `sys_bom.id` | BOM头ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 子件物料ID（sys_material.id） |
| `quantity` | `DECIMAL(18, 4)` | 否 | `1` | — | 单位用量 |
| `lead_time_offset` | `INTEGER` | 否 | `0` | — | 提前期偏置（天，相对父件需求时间的提前量） |
| `scrap_rate` | `DECIMAL(8, 4)` | 否 | `0` | — | 损耗率（0~1） |
| `sequence_no` | `INTEGER` | 否 | `1` | — | 序号 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_sys_bom_item` | `bom_id,material_id` |
| 外键 | `（自动命名）` | `bom_id` → `sys_bom.id`（ON DELETE CASCADE） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sys_bom_item_lead_offset` | `lead_time_offset >= 0` |
| 检查 | `ck_sys_bom_item_qty` | `quantity > 0` |
| 检查 | `ck_sys_bom_item_scrap` | `scrap_rate >= 0 AND scrap_rate < 1` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_bom_item_bom_id` | `bom_id` | 否 |
| `ix_sys_bom_item_material_id` | `material_id` | 否 |

#### `sys_dictionary` — 数据字典（计量单位、物料分类等基础枚举的可维护来源）

- ORM 类：`SysDictionary`（`backend/app/modules/system/models.py`）
- 字段数：9；外键：0

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `dict_code` | `VARCHAR(50)` | 否 | — | UK | 字典编码 |
| `dict_name` | `VARCHAR(100)` | 否 | — | — | 字典名称 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `dict_code` |
| 检查 | `ck_sys_dictionary_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**：除主键 / 唯一约束自动创建的索引外无额外索引。

#### `sys_dictionary_item` — 字典项

- ORM 类：`SysDictionaryItem`（`backend/app/modules/system/models.py`）
- 字段数：11；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `dict_id` | `BIGINT` | 否 | — | FK → `sys_dictionary.id` | 字典ID |
| `item_code` | `VARCHAR(50)` | 否 | — | — | 字典项编码 |
| `item_name` | `VARCHAR(100)` | 否 | — | — | 字典项名称 |
| `item_value` | `VARCHAR(200)` | 是 | — | — | 字典项值 |
| `sort_no` | `INTEGER` | 否 | `0` | — | 排序号 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_sys_dictionary_item` | `dict_id,item_code` |
| 外键 | `（自动命名）` | `dict_id` → `sys_dictionary.id`（ON DELETE CASCADE） |
| 检查 | `ck_sys_dictionary_item_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_dictionary_item_dict_id` | `dict_id` | 否 |

#### `sys_material` — **全系统唯一物料主表**

- ORM 类：`SysMaterial`（`backend/app/modules/system/models.py`）
- 字段数：17；外键：0

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `material_code` | `VARCHAR(50)` | 否 | — | UK | 物料编码 |
| `material_name` | `VARCHAR(100)` | 否 | — | — | 物料名称 |
| `material_type` | `VARCHAR(20)` | 否 | — | — | 物料类型 RAW/PURCHASED/SEMI/FINISHED |
| `supply_type` | `VARCHAR(20)` | 否 | — | — | 供应类型 MAKE/BUY |
| `unit_code` | `VARCHAR(20)` | 否 | `'PCS'` | — | 计量单位 |
| `specification` | `VARCHAR(200)` | 是 | — | — | 规格型号 |
| `material_group` | `VARCHAR(50)` | 是 | — | — | 物料分组 |
| `lead_time_days` | `INTEGER` | 否 | `0` | — | 提前期（天） |
| `safety_stock` | `DECIMAL(18, 4)` | 否 | `0` | — | 安全库存 |
| `standard_cost` | `DECIMAL(18, 2)` | 否 | `0` | — | 标准成本 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `material_code` |
| 检查 | `ck_sys_material_lead_time` | `lead_time_days >= 0` |
| 检查 | `ck_sys_material_safety_stock` | `safety_stock >= 0` |
| 检查 | `ck_sys_material_status` | `status IN ('ACTIVE','INACTIVE')` |
| 检查 | `ck_sys_material_supply_type` | `supply_type IN ('MAKE','BUY')` |
| 检查 | `ck_sys_material_type` | `material_type IN ('RAW','PURCHASED','SEMI','FINISHED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_material_material_type` | `material_type` | 否 |
| `ix_sys_material_supply_type` | `supply_type` | 否 |

#### `sys_operation_log` — 操作日志：记录关键业务动作，便于审计追踪

- ORM 类：`SysOperationLog`（`backend/app/modules/system/models.py`）
- 字段数：8；外键：0

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `module` | `VARCHAR(20)` | 否 | — | — | 模块标识 |
| `action` | `VARCHAR(50)` | 否 | — | — | 动作（CREATE/CONFIRM/...） |
| `target_type` | `VARCHAR(50)` | 否 | — | — | 目标对象类型（表名） |
| `target_id` | `BIGINT` | 是 | — | — | 目标对象ID |
| `operator_id` | `BIGINT` | 是 | — | — | 操作人ID（sys_user.id） |
| `detail` | `TEXT` | 是 | — | — | 详情 |
| `created_at` | `DATETIME` | 否 | `now()` | — | 发生时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_operation_log_module` | `module` | 否 |

#### `sys_organization` — 组织 / 部门（树形，`parent_id` 自引用）

- ORM 类：`SysOrganization`（`backend/app/modules/system/models.py`）
- 字段数：12；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `org_code` | `VARCHAR(50)` | 否 | — | UK | 组织编码 |
| `org_name` | `VARCHAR(100)` | 否 | — | — | 组织名称 |
| `parent_id` | `BIGINT` | 是 | — | FK → `sys_organization.id` | 上级组织ID |
| `org_type` | `VARCHAR(20)` | 否 | `'DEPARTMENT'` | — | 组织类型 |
| `manager_id` | `BIGINT` | 是 | — | — | 负责人ID（sys_personnel.id，延迟引用避免建表循环） |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `org_code` |
| 外键 | `（自动命名）` | `parent_id` → `sys_organization.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sys_organization_status` | `status IN ('ACTIVE','INACTIVE')` |
| 检查 | `ck_sys_organization_type` | `org_type IN ('COMPANY','FACTORY','DEPARTMENT','WORKSHOP','WAREHOUSE')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_organization_parent_id` | `parent_id` | 否 |

#### `sys_permission` — 权限点：菜单 / 页面 / 关键操作（树形）

- ORM 类：`SysPermission`（`backend/app/modules/system/models.py`）
- 字段数：13；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `perm_code` | `VARCHAR(50)` | 否 | — | UK | 权限编码 |
| `perm_name` | `VARCHAR(100)` | 否 | — | — | 权限名称 |
| `perm_type` | `VARCHAR(20)` | 否 | — | — | 权限类型 |
| `parent_id` | `BIGINT` | 是 | — | FK → `sys_permission.id` | 上级权限ID |
| `path` | `VARCHAR(200)` | 是 | — | — | 前端路由/接口路径 |
| `module` | `VARCHAR(20)` | 是 | — | — | 所属模块 |
| `sort_no` | `INTEGER` | 否 | `0` | — | 排序号 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `perm_code` |
| 外键 | `（自动命名）` | `parent_id` → `sys_permission.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sys_permission_status` | `status IN ('ACTIVE','INACTIVE')` |
| 检查 | `ck_sys_permission_type` | `perm_type IN ('MENU','PAGE','ACTION')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_permission_parent_id` | `parent_id` | 否 |

#### `sys_personnel` — 企业员工（全系统唯一人员表）

- ORM 类：`SysPersonnel`（`backend/app/modules/system/models.py`）
- 字段数：14；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `employee_no` | `VARCHAR(50)` | 否 | — | UK | 员工工号 |
| `person_name` | `VARCHAR(100)` | 否 | — | — | 姓名 |
| `org_id` | `BIGINT` | 否 | — | FK → `sys_organization.id` | 所属组织ID |
| `position` | `VARCHAR(50)` | 是 | — | — | 岗位 |
| `phone` | `VARCHAR(30)` | 是 | — | — | 联系电话 |
| `email` | `VARCHAR(100)` | 是 | — | — | 邮箱 |
| `hire_date` | `DATE` | 是 | — | — | 入职日期 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `employee_no` |
| 外键 | `（自动命名）` | `org_id` → `sys_organization.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sys_personnel_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_personnel_org_id` | `org_id` | 否 |

#### `sys_role` — 角色（规格 §30：System Administrator / Sales User / Planner / Buyer / Warehouse User）

- ORM 类：`SysRole`（`backend/app/modules/system/models.py`）
- 字段数：9；外键：0

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `role_code` | `VARCHAR(50)` | 否 | — | UK | 角色编码 |
| `role_name` | `VARCHAR(100)` | 否 | — | — | 角色名称 |
| `description` | `VARCHAR(255)` | 是 | — | — | 描述 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `role_code` |
| 检查 | `ck_sys_role_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**：除主键 / 唯一约束自动创建的索引外无额外索引。

#### `sys_role_permission` — 角色 N:M 权限 关联表

- ORM 类：`SysRolePermission`（`backend/app/modules/system/models.py`）
- 字段数：3；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `role_id` | `BIGINT` | 否 | — | FK → `sys_role.id` | 角色ID |
| `permission_id` | `BIGINT` | 否 | — | FK → `sys_permission.id` | 权限ID |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_sys_role_permission` | `role_id,permission_id` |
| 外键 | `（自动命名）` | `permission_id` → `sys_permission.id`（ON DELETE CASCADE） |
| 外键 | `（自动命名）` | `role_id` → `sys_role.id`（ON DELETE CASCADE） |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_role_permission_permission_id` | `permission_id` | 否 |
| `ix_sys_role_permission_role_id` | `role_id` | 否 |

#### `sys_routing` — 工艺路线头：某自制件的加工工序集合

- ORM 类：`SysRouting`（`backend/app/modules/system/models.py`）
- 字段数：10；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `routing_code` | `VARCHAR(50)` | 否 | — | — | 工艺路线编码 |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 自制件物料ID（sys_material.id） |
| `routing_version` | `VARCHAR(20)` | 否 | `'V1.0'` | — | 工艺版本 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_sys_routing_material_version` | `material_id,routing_version` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sys_routing_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_routing_material_id` | `material_id` | 否 |

#### `sys_routing_operation` — 工艺路线工序行

- ORM 类：`SysRoutingOperation`（`backend/app/modules/system/models.py`）
- 字段数：13；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `routing_id` | `BIGINT` | 否 | — | FK → `sys_routing.id` | 工艺路线ID |
| `sequence_no` | `INTEGER` | 否 | — | — | 工序顺序号 |
| `operation_code` | `VARCHAR(50)` | 否 | — | — | 工序编码 |
| `operation_name` | `VARCHAR(100)` | 否 | — | — | 工序名称 |
| `work_center` | `VARCHAR(50)` | 是 | — | — | 工作中心 |
| `setup_time` | `DECIMAL(18, 4)` | 否 | `0` | — | 准备工时（分钟） |
| `run_time` | `DECIMAL(18, 4)` | 否 | `0` | — | 单件加工工时（分钟） |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_sys_routing_operation_seq` | `routing_id,sequence_no` |
| 外键 | `（自动命名）` | `routing_id` → `sys_routing.id`（ON DELETE CASCADE） |
| 检查 | `ck_sys_routing_op_run` | `run_time >= 0` |
| 检查 | `ck_sys_routing_op_setup` | `setup_time >= 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_routing_operation_routing_id` | `routing_id` | 否 |

#### `sys_user` — 软件登录账号（与 Personnel 分离：一个 Personnel 可有 0 或 1 个 User）

- ORM 类：`SysUser`（`backend/app/modules/system/models.py`）
- 字段数：12；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `username` | `VARCHAR(50)` | 否 | — | UK | 登录名 |
| `password_hash` | `VARCHAR(255)` | 否 | — | — | 密码哈希 |
| `display_name` | `VARCHAR(100)` | 否 | — | — | 显示名 |
| `personnel_id` | `BIGINT` | 是 | — | UK、FK → `sys_personnel.id` | 关联员工ID（1:1，可为空） |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `last_login_at` | `DATETIME` | 是 | — | — | 最近登录时间 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `personnel_id` |
| 唯一 | `（自动命名）` | `username` |
| 外键 | `（自动命名）` | `personnel_id` → `sys_personnel.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sys_user_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**：除主键 / 唯一约束自动创建的索引外无额外索引。

#### `sys_user_role` — 用户 N:M 角色 关联表（规格 §21，禁止把多个 ID 塞进 VARCHAR）

- ORM 类：`SysUserRole`（`backend/app/modules/system/models.py`）
- 字段数：3；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `user_id` | `BIGINT` | 否 | — | FK → `sys_user.id` | 用户ID |
| `role_id` | `BIGINT` | 否 | — | FK → `sys_role.id` | 角色ID |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_sys_user_role` | `user_id,role_id` |
| 外键 | `（自动命名）` | `role_id` → `sys_role.id`（ON DELETE CASCADE） |
| 外键 | `（自动命名）` | `user_id` → `sys_user.id`（ON DELETE CASCADE） |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sys_user_role_role_id` | `role_id` | 否 |
| `ix_sys_user_role_user_id` | `user_id` | 否 |


### 3.2 销售管理 模块（`sal_`，共 8 张表）

#### `sal_customer` — 客户主数据

- ORM 类：`SalCustomer`（`backend/app/modules/sales/models.py`）
- 字段数：14；外键：0

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `customer_code` | `VARCHAR(50)` | 否 | — | UK | 客户编码 |
| `customer_name` | `VARCHAR(100)` | 否 | — | — | 客户名称 |
| `contact_person` | `VARCHAR(50)` | 是 | — | — | 联系人 |
| `phone` | `VARCHAR(30)` | 是 | — | — | 联系电话 |
| `email` | `VARCHAR(100)` | 是 | — | — | 邮箱 |
| `address` | `VARCHAR(200)` | 是 | — | — | 地址 |
| `credit_limit` | `DECIMAL(18, 2)` | 否 | `0` | — | 信用额度 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `customer_code` |
| 检查 | `ck_sal_customer_credit` | `credit_limit >= 0` |
| 检查 | `ck_sal_customer_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**：除主键 / 唯一约束自动创建的索引外无额外索引。

#### `sal_forecast` — 销售预测：按月对某物料的预测量，是 Planning 的需求来源之一

- ORM 类：`SalForecast`（`backend/app/modules/sales/models.py`）
- 字段数：12；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `forecast_no` | `VARCHAR(50)` | 否 | — | UK | 预测单号 |
| `customer_id` | `BIGINT` | 是 | — | FK → `sal_customer.id` | 客户ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `forecast_month` | `VARCHAR(7)` | 否 | — | — | 预测月份（YYYY-MM） |
| `forecast_qty` | `DECIMAL(18, 4)` | 否 | — | — | 预测数量 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `forecast_no` |
| 外键 | `（自动命名）` | `customer_id` → `sal_customer.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sal_forecast_qty` | `forecast_qty >= 0` |
| 检查 | `ck_sal_forecast_status` | `status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sal_forecast_customer_id` | `customer_id` | 否 |
| `ix_sal_forecast_material_id` | `material_id` | 否 |
| `ix_sal_forecast_status` | `status` | 否 |

#### `sal_order` — 销售订单头

- ORM 类：`SalOrder`（`backend/app/modules/sales/models.py`）
- 字段数：13；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `order_no` | `VARCHAR(50)` | 否 | — | UK | 销售订单号 |
| `customer_id` | `BIGINT` | 否 | — | FK → `sal_customer.id` | 客户ID |
| `order_date` | `DATE` | 否 | — | — | 订单日期 |
| `delivery_date` | `DATE` | 否 | — | — | 要求交货日期 |
| `salesperson_id` | `BIGINT` | 是 | — | FK → `sys_personnel.id` | 销售员（sys_personnel.id） |
| `total_amount` | `DECIMAL(18, 2)` | 否 | `0` | — | 订单总金额 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `order_no` |
| 外键 | `（自动命名）` | `customer_id` → `sal_customer.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `salesperson_id` → `sys_personnel.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sal_order_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sal_order_customer_id` | `customer_id` | 否 |
| `ix_sal_order_salesperson_id` | `salesperson_id` | 否 |
| `ix_sal_order_status` | `status` | 否 |

#### `sal_order_item` — 销售订单行。`delivered_qty` 由发货流程回写

- ORM 类：`SalOrderItem`（`backend/app/modules/sales/models.py`）
- 字段数：13；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `order_id` | `BIGINT` | 否 | — | FK → `sal_order.id` | 订单头ID |
| `line_no` | `INTEGER` | 否 | `1` | — | 行号 |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `quantity` | `DECIMAL(18, 4)` | 否 | — | — | 订单数量 |
| `delivered_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 已发货数量 |
| `unit_price` | `DECIMAL(18, 2)` | 否 | `0` | — | 单价 |
| `amount` | `DECIMAL(18, 2)` | 否 | `0` | — | 金额 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_sal_order_item_line` | `order_id,line_no` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `order_id` → `sal_order.id`（ON DELETE CASCADE） |
| 检查 | `ck_sal_order_item_delivered` | `delivered_qty >= 0` |
| 检查 | `ck_sal_order_item_qty` | `quantity > 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sal_order_item_material_id` | `material_id` | 否 |
| `ix_sal_order_item_order_id` | `order_id` | 否 |

#### `sal_return` — 销售退货单头。确认退货时调用 inventory 接口入库

- ORM 类：`SalReturn`（`backend/app/modules/sales/models.py`）
- 字段数：12；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `return_no` | `VARCHAR(50)` | 否 | — | UK | 退货单号 |
| `order_id` | `BIGINT` | 是 | — | FK → `sal_order.id` | 原销售订单ID |
| `customer_id` | `BIGINT` | 否 | — | FK → `sal_customer.id` | 客户ID |
| `return_date` | `DATE` | 否 | — | — | 退货日期 |
| `reason` | `VARCHAR(200)` | 是 | — | — | 退货原因 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `return_no` |
| 外键 | `（自动命名）` | `customer_id` → `sal_customer.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `order_id` → `sal_order.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sal_return_status` | `status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sal_return_customer_id` | `customer_id` | 否 |
| `ix_sal_return_order_id` | `order_id` | 否 |
| `ix_sal_return_status` | `status` | 否 |

#### `sal_return_item` — 退货明细行

- ORM 类：`SalReturnItem`（`backend/app/modules/sales/models.py`）
- 字段数：13；外键：4

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `return_id` | `BIGINT` | 否 | — | FK → `sal_return.id` | 退货单头ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 退回仓库ID |
| `location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 退回库位ID |
| `quantity` | `DECIMAL(18, 4)` | 否 | — | — | 退货数量 |
| `quality_status` | `VARCHAR(20)` | 否 | `'QUALIFIED'` | — | 质量状态 QUALIFIED/DEFECTIVE/SCRAP |
| `reason` | `VARCHAR(200)` | 是 | — | — | 行退货原因 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `return_id` → `sal_return.id`（ON DELETE CASCADE） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sal_return_item_qty` | `quantity > 0` |
| 检查 | `ck_sal_return_item_quality` | `quality_status IN ('QUALIFIED','DEFECTIVE','SCRAP')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sal_return_item_material_id` | `material_id` | 否 |
| `ix_sal_return_item_return_id` | `return_id` | 否 |

#### `sal_shipment` — 销售发货单头。确认发货时调用 inventory 接口出库

- ORM 类：`SalShipment`（`backend/app/modules/sales/models.py`）
- 字段数：11；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `shipment_no` | `VARCHAR(50)` | 否 | — | UK | 发货单号 |
| `order_id` | `BIGINT` | 否 | — | FK → `sal_order.id` | 销售订单ID |
| `customer_id` | `BIGINT` | 否 | — | FK → `sal_customer.id` | 客户ID |
| `shipment_date` | `DATE` | 否 | — | — | 发货日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `shipment_no` |
| 外键 | `（自动命名）` | `customer_id` → `sal_customer.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `order_id` → `sal_order.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sal_shipment_status` | `status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sal_shipment_customer_id` | `customer_id` | 否 |
| `ix_sal_shipment_order_id` | `order_id` | 否 |
| `ix_sal_shipment_status` | `status` | 否 |

#### `sal_shipment_item` — 发货明细行

- ORM 类：`SalShipmentItem`（`backend/app/modules/sales/models.py`）
- 字段数：12；外键：5

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `shipment_id` | `BIGINT` | 否 | — | FK → `sal_shipment.id` | 发货单头ID |
| `order_item_id` | `BIGINT` | 否 | — | FK → `sal_order_item.id` | 销售订单行ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 发货仓库ID |
| `location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 发货库位ID |
| `quantity` | `DECIMAL(18, 4)` | 否 | — | — | 发货数量 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `order_item_id` → `sal_order_item.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `shipment_id` → `sal_shipment.id`（ON DELETE CASCADE） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_sal_shipment_item_qty` | `quantity > 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_sal_shipment_item_material_id` | `material_id` | 否 |
| `ix_sal_shipment_item_order_item_id` | `order_item_id` | 否 |
| `ix_sal_shipment_item_shipment_id` | `shipment_id` | 否 |


### 3.3 计划管理 模块（`pln_`，共 10 张表）

#### `pln_completion_report` — 完工报告：生产完工报工（确认后走 inventory 入库，增加半成品/成品库存）

- ORM 类：`PlnCompletionReport`（`backend/app/modules/planning/models.py`）
- 字段数：17；外键：5

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `report_no` | `VARCHAR(50)` | 否 | — | UK | 完工报告单号 |
| `plan_id` | `BIGINT` | 是 | — | FK → `pln_production_plan.id` | 生产作业计划ID |
| `dispatch_id` | `BIGINT` | 是 | — | FK → `pln_dispatch_order.id` | 派工单ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 产出物料ID |
| `completed_qty` | `DECIMAL(18, 4)` | 否 | — | — | 完工数量 |
| `qualified_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 合格数量（入库数量） |
| `scrap_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 报废数量 |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 入库仓库ID |
| `location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 入库库位ID |
| `report_date` | `DATE` | 否 | — | — | 报工日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `report_no` |
| 外键 | `（自动命名）` | `dispatch_id` → `pln_dispatch_order.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `plan_id` → `pln_production_plan.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pln_completion_qty` | `completed_qty > 0` |
| 检查 | `ck_pln_completion_qualified` | `qualified_qty >= 0` |
| 检查 | `ck_pln_completion_scrap` | `scrap_qty >= 0` |
| 检查 | `ck_pln_completion_status` | `status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_completion_report_material_id` | `material_id` | 否 |
| `ix_pln_completion_report_plan_id` | `plan_id` | 否 |
| `ix_pln_completion_report_status` | `status` | 否 |

#### `pln_demand` — 统一需求入口：合并销售需求 / 库存补库需求 / MPS 需求

- ORM 类：`PlnDemand`（`backend/app/modules/planning/models.py`）
- 字段数：14；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `demand_no` | `VARCHAR(50)` | 否 | — | UK | 需求单号 |
| `source_type` | `VARCHAR(20)` | 否 | — | — | 需求来源 SALES/STOCKFILL/MPS |
| `source_reference_id` | `INTEGER` | 是 | — | — | 来源单据ID（跨模块多态引用） |
| `source_no` | `VARCHAR(50)` | 是 | — | — | 来源单号 |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `quantity` | `DECIMAL(18, 4)` | 否 | — | — | 需求数量 |
| `due_date` | `DATE` | 否 | — | — | 需求日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `demand_no` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pln_demand_qty` | `quantity > 0` |
| 检查 | `ck_pln_demand_source` | `source_type IN ('SALES','STOCKFILL','MPS')` |
| 检查 | `ck_pln_demand_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_demand_due_date` | `due_date` | 否 |
| `ix_pln_demand_material_id` | `material_id` | 否 |
| `ix_pln_demand_source_reference_id` | `source_reference_id` | 否 |
| `ix_pln_demand_source_type` | `source_type` | 否 |
| `ix_pln_demand_status` | `status` | 否 |

#### `pln_dispatch_order` — 派工单：把作业计划下达到具体工序 / 作业人员

- ORM 类：`PlnDispatchOrder`（`backend/app/modules/planning/models.py`）
- 字段数：15；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `dispatch_no` | `VARCHAR(50)` | 否 | — | UK | 派工单号 |
| `plan_id` | `BIGINT` | 是 | — | FK → `pln_production_plan.id` | 生产作业计划ID |
| `operation` | `VARCHAR(60)` | 是 | — | — | 工序 |
| `planned_qty` | `DECIMAL(18, 4)` | 否 | — | — | 派工数量 |
| `completed_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 完成数量 |
| `worker_id` | `BIGINT` | 是 | — | FK → `sys_personnel.id` | 作业人员（sys_personnel.id） |
| `planned_start` | `DATE` | 否 | — | — | 计划开始日期 |
| `planned_end` | `DATE` | 否 | — | — | 计划结束日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `dispatch_no` |
| 外键 | `（自动命名）` | `plan_id` → `pln_production_plan.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `worker_id` → `sys_personnel.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pln_dispatch_completed` | `completed_qty >= 0` |
| 检查 | `ck_pln_dispatch_qty` | `planned_qty > 0` |
| 检查 | `ck_pln_dispatch_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_dispatch_order_plan_id` | `plan_id` | 否 |
| `ix_pln_dispatch_order_status` | `status` | 否 |
| `ix_pln_dispatch_order_worker_id` | `worker_id` | 否 |

#### `pln_material_requisition` — 领料单头：生产领料的申请与执行（执行时走 inventory 出库）

- ORM 类：`PlnMaterialRequisition`（`backend/app/modules/planning/models.py`）
- 字段数：11；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `req_no` | `VARCHAR(50)` | 否 | — | UK | 领料单号 |
| `plan_id` | `BIGINT` | 是 | — | FK → `pln_production_plan.id` | 生产作业计划ID |
| `warehouse_id` | `BIGINT` | 是 | — | FK → `inv_warehouse.id` | 领料仓库ID |
| `req_date` | `DATE` | 否 | — | — | 领料日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `req_no` |
| 外键 | `（自动命名）` | `plan_id` → `pln_production_plan.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pln_requisition_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_material_requisition_plan_id` | `plan_id` | 否 |
| `ix_pln_material_requisition_status` | `status` | 否 |

#### `pln_material_requisition_item` — 领料单行。`issued_qty` 由实际出库回写

- ORM 类：`PlnMaterialRequisitionItem`（`backend/app/modules/planning/models.py`）
- 字段数：11；外键：3

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `requisition_id` | `BIGINT` | 否 | — | FK → `pln_material_requisition.id` | 领料单头ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `required_qty` | `DECIMAL(18, 4)` | 否 | — | — | 需求数量 |
| `issued_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 已领数量 |
| `location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 领料库位ID |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `requisition_id` → `pln_material_requisition.id`（ON DELETE CASCADE） |
| 检查 | `ck_pln_req_item_issued` | `issued_qty >= 0` |
| 检查 | `ck_pln_req_item_required` | `required_qty > 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_material_requisition_item_material_id` | `material_id` | 否 |
| `ix_pln_material_requisition_item_requisition_id` | `requisition_id` | 否 |

#### `pln_mps` — 主生产计划头

- ORM 类：`PlnMps`（`backend/app/modules/planning/models.py`）
- 字段数：13；外键：0

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `mps_no` | `VARCHAR(50)` | 否 | — | UK | MPS编号 |
| `mps_name` | `VARCHAR(100)` | 是 | — | — | 计划名称 |
| `program_no` | `VARCHAR(50)` | 是 | — | — | 计划编号/产线 |
| `plan_year` | `INTEGER` | 否 | — | — | 计划年度 |
| `start_date` | `DATE` | 否 | — | — | 计划开始日期 |
| `end_date` | `DATE` | 否 | — | — | 计划结束日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `mps_no` |
| 检查 | `ck_pln_mps_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_mps_status` | `status` | 否 |

#### `pln_mps_item` — 主生产计划行：某成品在某期间的计划生产量

- ORM 类：`PlnMpsItem`（`backend/app/modules/planning/models.py`）
- 字段数：14；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `mps_id` | `BIGINT` | 否 | — | FK → `pln_mps.id` | MPS头ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 产成品物料ID |
| `period_label` | `VARCHAR(20)` | 是 | — | — | 计划期间标签（如 2026-01） |
| `planned_qty` | `DECIMAL(18, 4)` | 否 | — | — | 计划生产数量 |
| `finished_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 已完成数量 |
| `start_date` | `DATE` | 否 | — | — | 计划开始日期 |
| `end_date` | `DATE` | 否 | — | — | 计划完成日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `mps_id` → `pln_mps.id`（ON DELETE CASCADE） |
| 检查 | `ck_pln_mps_item_finished` | `finished_qty >= 0` |
| 检查 | `ck_pln_mps_item_qty` | `planned_qty > 0` |
| 检查 | `ck_pln_mps_item_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_mps_item_material_id` | `material_id` | 否 |
| `ix_pln_mps_item_mps_id` | `mps_id` | 否 |

#### `pln_mrp_result` — MRP 运算结果：BOM 逐层展开后的毛需求 / 可用库存 / 净需求 / 建议下达

- ORM 类：`PlnMrpResult`（`backend/app/modules/planning/models.py`）
- 字段数：21；外键：3

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `run_id` | `BIGINT` | 否 | — | FK → `pln_mrp_run.id` | 运算批次ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `parent_material_id` | `BIGINT` | 是 | — | FK → `sys_material.id` | 父件物料ID（BOM 展开时记录来源母件） |
| `bom_level` | `INTEGER` | 否 | `0` | — | BOM层级（成品=0） |
| `gross_requirement` | `DECIMAL(18, 4)` | 否 | `0` | — | 毛需求 |
| `on_hand` | `DECIMAL(18, 4)` | 否 | `0` | — | 库存量（来自 inventory 快照） |
| `available_quantity` | `DECIMAL(18, 4)` | 否 | `0` | — | 可用库存（库存 - 锁定量） |
| `safety_stock` | `DECIMAL(18, 4)` | 否 | `0` | — | 安全库存 |
| `net_requirement` | `DECIMAL(18, 4)` | 否 | `0` | — | 净需求 = max(毛需求+安全库存-可用库存, 0) |
| `order_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 建议下达数量 |
| `supply_type` | `VARCHAR(20)` | 否 | — | — | 供应类型 MAKE/BUY |
| `lead_time_days` | `INTEGER` | 否 | `0` | — | 提前期（天） |
| `requirement_date` | `DATE` | 否 | — | — | 需求日期 |
| `planned_release_date` | `DATE` | 是 | — | — | 建议下达日期（需求日期 - 提前期） |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `parent_material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `run_id` → `pln_mrp_run.id`（ON DELETE CASCADE） |
| 检查 | `ck_pln_mrp_result_gross` | `gross_requirement >= 0` |
| 检查 | `ck_pln_mrp_result_level` | `bom_level >= 0` |
| 检查 | `ck_pln_mrp_result_net` | `net_requirement >= 0` |
| 检查 | `ck_pln_mrp_result_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')` |
| 检查 | `ck_pln_mrp_result_supply` | `supply_type IN ('MAKE','BUY')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_mrp_result_material_id` | `material_id` | 否 |
| `ix_pln_mrp_result_parent_material_id` | `parent_material_id` | 否 |
| `ix_pln_mrp_result_run_id` | `run_id` | 否 |
| `ix_pln_mrp_result_status` | `status` | 否 |
| `ix_pln_mrp_result_supply_type` | `supply_type` | 否 |

#### `pln_mrp_run` — MRP 运算批次：一次运算的上下文与结果归属

- ORM 类：`PlnMrpRun`（`backend/app/modules/planning/models.py`）
- 字段数：11；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `run_no` | `VARCHAR(50)` | 否 | — | UK | 运算批次号 |
| `mps_id` | `BIGINT` | 是 | — | FK → `pln_mps.id` | MPS头ID |
| `run_at` | `DATETIME` | 否 | `now()` | — | 运算时间 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `material_count` | `INTEGER` | 否 | `0` | — | 涉及物料数 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `run_no` |
| 外键 | `（自动命名）` | `mps_id` → `pln_mps.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pln_mrp_run_status` | `status IN ('DRAFT','IN_PROGRESS','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_mrp_run_mps_id` | `mps_id` | 否 |
| `ix_pln_mrp_run_status` | `status` | 否 |

#### `pln_production_plan` — 车间生产作业计划：承接 MRP 自制（MAKE）需求

- ORM 类：`PlnProductionPlan`（`backend/app/modules/planning/models.py`）
- 字段数：17；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `plan_no` | `VARCHAR(50)` | 否 | — | UK | 作业计划编号 |
| `mrp_result_id` | `BIGINT` | 是 | — | FK → `pln_mrp_result.id` | MRP结果ID |
| `source_type` | `VARCHAR(20)` | 否 | `'MRP'` | — | 来源 MRP/REPLENISHMENT/MANUAL |
| `source_reference_id` | `INTEGER` | 是 | — | — | 来源单据ID（多态引用） |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 自制件物料ID |
| `planned_qty` | `DECIMAL(18, 4)` | 否 | — | — | 计划生产数量 |
| `completed_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 已完工数量 |
| `plan_date` | `DATE` | 否 | — | — | 计划日期 |
| `start_date` | `DATE` | 否 | — | — | 计划开始日期 |
| `end_date` | `DATE` | 否 | — | — | 计划完成日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `plan_no` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `mrp_result_id` → `pln_mrp_result.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pln_production_plan_completed` | `completed_qty >= 0` |
| 检查 | `ck_pln_production_plan_qty` | `planned_qty > 0` |
| 检查 | `ck_pln_production_plan_source` | `source_type IN ('MRP','REPLENISHMENT','MANUAL')` |
| 检查 | `ck_pln_production_plan_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pln_production_plan_material_id` | `material_id` | 否 |
| `ix_pln_production_plan_mrp_result_id` | `mrp_result_id` | 否 |
| `ix_pln_production_plan_status` | `status` | 否 |


### 3.4 采购管理 模块（`pur_`，共 9 张表）

#### `pur_order` — 采购订单头

- ORM 类：`PurOrder`（`backend/app/modules/procurement/models.py`）
- 字段数：13；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `order_no` | `VARCHAR(50)` | 否 | — | UK | 采购订单号 |
| `supplier_id` | `BIGINT` | 否 | — | FK → `pur_supplier.id` | 供应商ID |
| `order_date` | `DATE` | 否 | — | — | 下单日期 |
| `expected_date` | `DATE` | 否 | — | — | 预计到货日期 |
| `buyer_id` | `BIGINT` | 是 | — | FK → `sys_personnel.id` | 采购员（sys_personnel.id） |
| `total_amount` | `DECIMAL(18, 2)` | 否 | `0` | — | 订单总金额 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `order_no` |
| 外键 | `（自动命名）` | `buyer_id` → `sys_personnel.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `supplier_id` → `pur_supplier.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pur_order_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','IN_PROGRESS','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pur_order_buyer_id` | `buyer_id` | 否 |
| `ix_pur_order_status` | `status` | 否 |
| `ix_pur_order_supplier_id` | `supplier_id` | 否 |

#### `pur_order_item` — 采购订单行。`received_qty` 由到货流程回写

- ORM 类：`PurOrderItem`（`backend/app/modules/procurement/models.py`）
- 字段数：13；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `order_id` | `BIGINT` | 否 | — | FK → `pur_order.id` | 订单头ID |
| `line_no` | `INTEGER` | 否 | `1` | — | 行号 |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `quantity` | `DECIMAL(18, 4)` | 否 | — | — | 采购数量 |
| `received_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 已到货数量 |
| `unit_price` | `DECIMAL(18, 2)` | 否 | `0` | — | 单价 |
| `amount` | `DECIMAL(18, 2)` | 否 | `0` | — | 金额 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_pur_order_item_line` | `order_id,line_no` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `order_id` → `pur_order.id`（ON DELETE CASCADE） |
| 检查 | `ck_pur_order_item_qty` | `quantity > 0` |
| 检查 | `ck_pur_order_item_received` | `received_qty >= 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pur_order_item_material_id` | `material_id` | 否 |
| `ix_pur_order_item_order_id` | `order_id` | 否 |

#### `pur_purchase_plan` — 采购计划头：集中承载待采购需求的建议

- ORM 类：`PurPurchasePlan`（`backend/app/modules/procurement/models.py`）
- 字段数：9；外键：0

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `plan_no` | `VARCHAR(50)` | 否 | — | UK | 采购计划编号 |
| `plan_date` | `DATE` | 否 | — | — | 计划日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `plan_no` |
| 检查 | `ck_pur_purchase_plan_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pur_purchase_plan_status` | `status` | 否 |

#### `pur_purchase_plan_item` — 采购计划行：来源可以是 MRP 结果或库存补库需求

- ORM 类：`PurPurchasePlanItem`（`backend/app/modules/procurement/models.py`）
- 字段数：15；外键：3

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `plan_id` | `BIGINT` | 否 | — | FK → `pur_purchase_plan.id` | 采购计划头ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `required_qty` | `DECIMAL(18, 4)` | 否 | — | — | 需求数量 |
| `ordered_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 已下单数量 |
| `required_date` | `DATE` | 否 | — | — | 需求日期 |
| `source_type` | `VARCHAR(30)` | 否 | `'MRP'` | — | 来源类型 MRP/REORDER/MANUAL |
| `source_reference_id` | `INTEGER` | 是 | — | — | 来源单据ID（多态引用） |
| `supplier_id` | `BIGINT` | 是 | — | FK → `pur_supplier.id` | 建议供应商ID |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `plan_id` → `pur_purchase_plan.id`（ON DELETE CASCADE） |
| 外键 | `（自动命名）` | `supplier_id` → `pur_supplier.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pur_plan_item_ordered` | `ordered_qty >= 0` |
| 检查 | `ck_pur_plan_item_qty` | `required_qty > 0` |
| 检查 | `ck_pur_plan_item_source` | `source_type IN ('MRP','REORDER','MANUAL')` |
| 检查 | `ck_pur_plan_item_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pur_purchase_plan_item_material_id` | `material_id` | 否 |
| `ix_pur_purchase_plan_item_plan_id` | `plan_id` | 否 |
| `ix_pur_purchase_plan_item_source_reference_id` | `source_reference_id` | 否 |
| `ix_pur_purchase_plan_item_source_type` | `source_type` | 否 |

#### `pur_receipt` — 到货登记单头。确认后必须调用 inventory 入库并生成库存流水

- ORM 类：`PurReceipt`（`backend/app/modules/procurement/models.py`）
- 字段数：12；外键：3

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `receipt_no` | `VARCHAR(50)` | 否 | — | UK | 到货单号 |
| `purchase_order_id` | `BIGINT` | 否 | — | FK → `pur_order.id` | 采购订单ID |
| `supplier_id` | `BIGINT` | 否 | — | FK → `pur_supplier.id` | 供应商ID |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 收货仓库ID |
| `receipt_date` | `DATE` | 否 | — | — | 到货日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `receipt_no` |
| 外键 | `（自动命名）` | `purchase_order_id` → `pur_order.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `supplier_id` → `pur_supplier.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_pur_receipt_status` | `status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pur_receipt_purchase_order_id` | `purchase_order_id` | 否 |
| `ix_pur_receipt_status` | `status` | 否 |
| `ix_pur_receipt_supplier_id` | `supplier_id` | 否 |

#### `pur_receipt_item` — 到货明细行

- ORM 类：`PurReceiptItem`（`backend/app/modules/procurement/models.py`）
- 字段数：12；外键：4

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `receipt_id` | `BIGINT` | 否 | — | FK → `pur_receipt.id` | 到货单头ID |
| `order_item_id` | `BIGINT` | 否 | — | FK → `pur_order_item.id` | 采购订单行ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 收货库位ID |
| `quantity` | `DECIMAL(18, 4)` | 否 | — | — | 到货数量 |
| `qualified_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 合格数量 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `order_item_id` → `pur_order_item.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `receipt_id` → `pur_receipt.id`（ON DELETE CASCADE） |
| 检查 | `ck_pur_receipt_item_qty` | `quantity > 0` |
| 检查 | `ck_pur_receipt_item_qualified` | `qualified_qty >= 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pur_receipt_item_material_id` | `material_id` | 否 |
| `ix_pur_receipt_item_order_item_id` | `order_item_id` | 否 |
| `ix_pur_receipt_item_receipt_id` | `receipt_id` | 否 |

#### `pur_supplier` — 供应商主数据

- ORM 类：`PurSupplier`（`backend/app/modules/procurement/models.py`）
- 字段数：13；外键：0

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `supplier_code` | `VARCHAR(50)` | 否 | — | UK | 供应商编码 |
| `supplier_name` | `VARCHAR(100)` | 否 | — | — | 供应商名称 |
| `contact_person` | `VARCHAR(50)` | 是 | — | — | 联系人 |
| `phone` | `VARCHAR(30)` | 是 | — | — | 联系电话 |
| `email` | `VARCHAR(100)` | 是 | — | — | 邮箱 |
| `address` | `VARCHAR(200)` | 是 | — | — | 地址 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `supplier_code` |
| 检查 | `ck_pur_supplier_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**：除主键 / 唯一约束自动创建的索引外无额外索引。

#### `pur_supplier_evaluation` — 供应商评价：质量 / 交期 / 价格 三类评分

- ORM 类：`PurSupplierEvaluation`（`backend/app/modules/procurement/models.py`）
- 字段数：13；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `supplier_id` | `BIGINT` | 否 | — | FK → `pur_supplier.id` | 供应商ID |
| `evaluate_date` | `DATE` | 否 | — | — | 评价日期 |
| `quality_score` | `DECIMAL(8, 4)` | 否 | `0` | — | 质量评分（0~100） |
| `delivery_score` | `DECIMAL(8, 4)` | 否 | `0` | — | 交期评分（0~100） |
| `price_score` | `DECIMAL(8, 4)` | 否 | `0` | — | 价格评分（0~100） |
| `total_score` | `DECIMAL(8, 4)` | 否 | `0` | — | 综合评分 |
| `evaluator_id` | `BIGINT` | 是 | — | FK → `sys_personnel.id` | 评价人（sys_personnel.id） |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `evaluator_id` → `sys_personnel.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `supplier_id` → `pur_supplier.id`（ON DELETE CASCADE） |
| 检查 | `ck_pur_eval_delivery` | `delivery_score >= 0 AND delivery_score <= 100` |
| 检查 | `ck_pur_eval_price` | `price_score >= 0 AND price_score <= 100` |
| 检查 | `ck_pur_eval_quality` | `quality_score >= 0 AND quality_score <= 100` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pur_supplier_evaluation_supplier_id` | `supplier_id` | 否 |

#### `pur_supplier_material` — 供应商 N:M 物料 关联表（含供货价与供货提前期）

- ORM 类：`PurSupplierMaterial`（`backend/app/modules/procurement/models.py`）
- 字段数：12；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `supplier_id` | `BIGINT` | 否 | — | FK → `pur_supplier.id` | 供应商ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `is_primary` | `BOOLEAN` | 否 | `false` | — | 是否主供应商 |
| `supply_price` | `DECIMAL(18, 2)` | 否 | `0` | — | 供货单价 |
| `lead_time_days` | `INTEGER` | 否 | `0` | — | 供货提前期（天） |
| `min_order_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 最小起订量 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_pur_supplier_material` | `supplier_id,material_id` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `supplier_id` → `pur_supplier.id`（ON DELETE CASCADE） |
| 检查 | `ck_pur_supplier_material_lead` | `lead_time_days >= 0` |
| 检查 | `ck_pur_supplier_material_price` | `supply_price >= 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_pur_supplier_material_material_id` | `material_id` | 否 |
| `ix_pur_supplier_material_supplier_id` | `supplier_id` | 否 |


### 3.5 库存管理 模块（`inv_`，共 10 张表）

#### `inv_balance` — 库存结存：某仓库/库位下某物料的当前数量

- ORM 类：`InvBalance`（`backend/app/modules/inventory/models.py`）
- 字段数：11；外键：3

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 仓库ID |
| `location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 库位ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `quantity` | `DECIMAL(18, 4)` | 否 | `0` | — | 库存数量 |
| `locked_quantity` | `DECIMAL(18, 4)` | 否 | `0` | — | 锁定量（已分配未出库） |
| `updated_at_txn` | `DATETIME` | 是 | — | — | 最近一次变动时间 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_inv_balance_bucket` | `warehouse_id,location_id,material_id` |
| 外键 | `（自动命名）` | `location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_inv_balance_locked` | `locked_quantity >= 0` |
| 检查 | `ck_inv_balance_qty` | `quantity >= 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_inv_balance_location_id` | `location_id` | 否 |
| `ix_inv_balance_material_id` | `material_id` | 否 |
| `ix_inv_balance_warehouse_id` | `warehouse_id` | 否 |

#### `inv_location` — 库位（仓库下的具体存放位置）

- ORM 类：`InvLocation`（`backend/app/modules/inventory/models.py`）
- 字段数：10；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `location_code` | `VARCHAR(50)` | 否 | — | — | 库位编码 |
| `location_name` | `VARCHAR(100)` | 否 | — | — | 库位名称 |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 仓库ID |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_inv_location` | `warehouse_id,location_code` |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE CASCADE） |
| 检查 | `ck_inv_location_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_inv_location_warehouse_id` | `warehouse_id` | 否 |

#### `inv_reorder_rule` — 订货点规则：库存低于 `reorder_point` 时触发补库建议

- ORM 类：`InvReorderRule`（`backend/app/modules/inventory/models.py`）
- 字段数：11；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 仓库ID |
| `reorder_point` | `DECIMAL(18, 4)` | 否 | `0` | — | 订货点 |
| `reorder_quantity` | `DECIMAL(18, 4)` | 否 | `0` | — | 建议订货量 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `uq_inv_reorder_rule` | `material_id,warehouse_id` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_inv_reorder_point` | `reorder_point >= 0` |
| 检查 | `ck_inv_reorder_qty` | `reorder_quantity >= 0` |
| 检查 | `ck_inv_reorder_rule_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_inv_reorder_rule_material_id` | `material_id` | 否 |
| `ix_inv_reorder_rule_warehouse_id` | `warehouse_id` | 否 |

#### `inv_replenishment_request` — 补库需求单

- ORM 类：`InvReplenishmentRequest`（`backend/app/modules/inventory/models.py`）
- 字段数：17；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `request_no` | `VARCHAR(50)` | 否 | — | UK | 补库需求单号 |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 仓库ID |
| `request_qty` | `DECIMAL(18, 4)` | 否 | — | — | 补库数量 |
| `current_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 触发时库存量 |
| `target_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 目标库存量 |
| `required_date` | `DATE` | 否 | — | — | 需求日期 |
| `source_type` | `VARCHAR(20)` | 否 | — | — | 来源 REORDER/PRODUCTION |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `handled_module` | `VARCHAR(20)` | 是 | — | — | 受理模块 |
| `handled_ref_id` | `BIGINT` | 是 | — | — | 受理单据ID |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `request_no` |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_inv_repl_qty` | `request_qty > 0` |
| 检查 | `ck_inv_repl_source_type` | `source_type IN ('REORDER','PRODUCTION')` |
| 检查 | `ck_inv_repl_status` | `status IN ('DRAFT','CONFIRMED','RELEASED','COMPLETED','CANCELLED')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_inv_replenishment_request_material_id` | `material_id` | 否 |
| `ix_inv_replenishment_request_source_type` | `source_type` | 否 |
| `ix_inv_replenishment_request_status` | `status` | 否 |

#### `inv_stocktake` — 库存盘点单头

- ORM 类：`InvStocktake`（`backend/app/modules/inventory/models.py`）
- 字段数：10；外键：1

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `stocktake_no` | `VARCHAR(50)` | 否 | — | UK | 盘点单号 |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 仓库ID |
| `stocktake_date` | `DATE` | 否 | — | — | 盘点日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `stocktake_no` |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_inv_stocktake_status` | `status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')` |

**索引**：除主键 / 唯一约束自动创建的索引外无额外索引。

#### `inv_stocktake_item` — 盘点明细行：账面数 vs 实盘数，差异通过 `ADJUST` 流水调整

- ORM 类：`InvStocktakeItem`（`backend/app/modules/inventory/models.py`）
- 字段数：12；外键：3

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `stocktake_id` | `BIGINT` | 否 | — | FK → `inv_stocktake.id` | 盘点单头ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 库位ID |
| `book_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 账面数量 |
| `actual_qty` | `DECIMAL(18, 4)` | 否 | `0` | — | 实盘数量 |
| `difference` | `DECIMAL(18, 4)` | 否 | `0` | — | 差异数量 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `stocktake_id` → `inv_stocktake.id`（ON DELETE CASCADE） |
| 检查 | `ck_inv_stocktake_actual` | `actual_qty >= 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_inv_stocktake_item_stocktake_id` | `stocktake_id` | 否 |

#### `inv_transaction` — 库存流水（出入库明细）—— 库存变动的唯一入口与审计凭证

- ORM 类：`InvTransaction`（`backend/app/modules/inventory/models.py`）
- 字段数：20；外键：3

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `transaction_no` | `VARCHAR(50)` | 否 | — | UK | 流水单号 |
| `transaction_type` | `VARCHAR(20)` | 否 | — | — | 类型 IN/OUT/TRANSFER_IN/TRANSFER_OUT/ADJUST |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 仓库ID |
| `location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 库位ID |
| `quantity_change` | `DECIMAL(18, 4)` | 否 | — | — | 变动数量（入库为正，出库为负） |
| `quantity_after` | `DECIMAL(18, 4)` | 否 | `0` | — | 变动后结存 |
| `unit_cost` | `DECIMAL(18, 2)` | 否 | `0` | — | 单位成本 |
| `biz_date` | `DATE` | 否 | — | — | 业务日期 |
| `source_module` | `VARCHAR(20)` | 否 | — | — | 来源模块 |
| `source_type` | `VARCHAR(30)` | 否 | — | — | 来源业务类型（PURCHASE_RECEIPT 等） |
| `source_reference_id` | `BIGINT` | 是 | — | — | 来源单据ID |
| `source_no` | `VARCHAR(50)` | 是 | — | — | 来源单号（冗余便于查询） |
| `operator_id` | `BIGINT` | 是 | — | — | 操作人ID（sys_user.id） |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `transaction_no` |
| 外键 | `（自动命名）` | `location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_inv_transaction_source_type` | `source_type IN ('PURCHASE_RECEIPT','PRODUCTION_COMPLETION','MATERIAL_REQUISITION','SALES_SHIPMENT','SALES_RETURN','TRANSFER','STOCKTAKE','MANUAL')` |
| 检查 | `ck_inv_transaction_type` | `transaction_type IN ('IN','OUT','TRANSFER_IN','TRANSFER_OUT','ADJUST')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_inv_transaction_material_id` | `material_id` | 否 |
| `ix_inv_transaction_source_reference_id` | `source_reference_id` | 否 |
| `ix_inv_transaction_transaction_type` | `transaction_type` | 否 |
| `ix_inv_transaction_warehouse_id` | `warehouse_id` | 否 |

#### `inv_transfer` — 移库单头：仓库/库位之间的库存移动

- ORM 类：`InvTransfer`（`backend/app/modules/inventory/models.py`）
- 字段数：11；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `transfer_no` | `VARCHAR(50)` | 否 | — | UK | 移库单号 |
| `from_warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 源仓库ID |
| `to_warehouse_id` | `BIGINT` | 否 | — | FK → `inv_warehouse.id` | 目标仓库ID |
| `transfer_date` | `DATE` | 否 | — | — | 移库日期 |
| `status` | `VARCHAR(20)` | 否 | `'DRAFT'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `transfer_no` |
| 外键 | `（自动命名）` | `from_warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `to_warehouse_id` → `inv_warehouse.id`（ON DELETE RESTRICT） |
| 检查 | `ck_inv_transfer_status` | `status IN ('DRAFT','CONFIRMED','COMPLETED','CANCELLED')` |

**索引**：除主键 / 唯一约束自动创建的索引外无额外索引。

#### `inv_transfer_item` — 移库明细行

- ORM 类：`InvTransferItem`（`backend/app/modules/inventory/models.py`）
- 字段数：11；外键：4

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `transfer_id` | `BIGINT` | 否 | — | FK → `inv_transfer.id` | 移库单头ID |
| `material_id` | `BIGINT` | 否 | — | FK → `sys_material.id` | 物料ID |
| `from_location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 源库位ID |
| `to_location_id` | `BIGINT` | 是 | — | FK → `inv_location.id` | 目标库位ID |
| `quantity` | `DECIMAL(18, 4)` | 否 | — | — | 移库数量 |
| `remark` | `VARCHAR(200)` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 外键 | `（自动命名）` | `from_location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `material_id` → `sys_material.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `to_location_id` → `inv_location.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `transfer_id` → `inv_transfer.id`（ON DELETE CASCADE） |
| 检查 | `ck_inv_transfer_item_qty` | `quantity > 0` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_inv_transfer_item_transfer_id` | `transfer_id` | 否 |

#### `inv_warehouse` — 仓库

- ORM 类：`InvWarehouse`（`backend/app/modules/inventory/models.py`）
- 字段数：12；外键：2

| 字段 | 类型 | 可空 | 默认值 | 键 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | 否 | — | PK | — |
| `warehouse_code` | `VARCHAR(50)` | 否 | — | UK | 仓库编码 |
| `warehouse_name` | `VARCHAR(100)` | 否 | — | — | 仓库名称 |
| `org_id` | `BIGINT` | 是 | — | FK → `sys_organization.id` | 所属组织ID |
| `manager_id` | `BIGINT` | 是 | — | FK → `sys_personnel.id` | 仓库负责人（sys_personnel.id） |
| `address` | `VARCHAR(200)` | 是 | — | — | 地址 |
| `status` | `VARCHAR(20)` | 否 | `'ACTIVE'` | — | 状态 |
| `remark` | `TEXT` | 是 | — | — | 备注 |
| `created_by` | `BIGINT` | 是 | — | — | 创建人ID（sys_user.id） |
| `updated_by` | `BIGINT` | 是 | — | — | 更新人ID（sys_user.id） |
| `created_at` | `DATETIME` | 否 | `now()` | — | 创建时间 |
| `updated_at` | `DATETIME` | 否 | `now()`<br>ON UPDATE `now()` | — | 更新时间 |

**约束**

| 类型 | 约束名 | 定义 |
| --- | --- | --- |
| 主键 | `（自动命名）` | `id` |
| 唯一 | `（自动命名）` | `warehouse_code` |
| 外键 | `（自动命名）` | `manager_id` → `sys_personnel.id`（ON DELETE RESTRICT） |
| 外键 | `（自动命名）` | `org_id` → `sys_organization.id`（ON DELETE RESTRICT） |
| 检查 | `ck_inv_warehouse_status` | `status IN ('ACTIVE','INACTIVE')` |

**索引**

| 索引名 | 字段 | 唯一 |
| --- | --- | --- |
| `ix_inv_warehouse_org_id` | `org_id` | 否 |
