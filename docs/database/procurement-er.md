# 采购管理 模块 ER 图（`pur_`）

> 自动内省 `Base.metadata` 生成；本文件只覆盖 `pur_` 前缀的 9 张表。
> 全库关系与跨模块外键见 [`full-er-diagram.md`](./full-er-diagram.md)，
> 字段完整说明见 [`physical-data-model.md`](./physical-data-model.md)。

## 一、本模块表清单

| 表名 | ORM 类 | 说明 | 字段数 |
| --- | --- | --- | --- |
| `pur_order` | `PurOrder` | 采购订单头 | 13 |
| `pur_order_item` | `PurOrderItem` | 采购订单行。`received_qty` 由到货流程回写 | 13 |
| `pur_purchase_plan` | `PurPurchasePlan` | 采购计划头：集中承载待采购需求的建议 | 9 |
| `pur_purchase_plan_item` | `PurPurchasePlanItem` | 采购计划行：来源可以是 MRP 结果或库存补库需求 | 15 |
| `pur_receipt` | `PurReceipt` | 到货登记单头。确认后必须调用 inventory 入库并生成库存流水 | 12 |
| `pur_receipt_item` | `PurReceiptItem` | 到货明细行 | 12 |
| `pur_supplier` | `PurSupplier` | 供应商主数据 | 13 |
| `pur_supplier_evaluation` | `PurSupplierEvaluation` | 供应商评价：质量 / 交期 / 价格 三类评分 | 13 |
| `pur_supplier_material` | `PurSupplierMaterial` | 供应商 N:M 物料 关联表（含供货价与供货提前期） | 12 |

## 二、ER 图（含全部字段）

```mermaid
erDiagram
    pur_order {
        BIGINT id PK "BIGINT"
        VARCHAR order_no UK "采购订单号"
        BIGINT supplier_id FK "供应商ID"
        DATE order_date "下单日期"
        DATE expected_date "预计到货日期"
        BIGINT buyer_id FK "采购员（sys_personnel.id）"
        DECIMAL total_amount "订单总金额"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    pur_order_item {
        BIGINT id PK "BIGINT"
        BIGINT order_id FK "订单头ID"
        INT line_no "行号"
        BIGINT material_id FK "物料ID"
        DECIMAL quantity "采购数量"
        DECIMAL received_qty "已到货数量"
        DECIMAL unit_price "单价"
        DECIMAL amount "金额"
        VARCHAR remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    pur_purchase_plan {
        BIGINT id PK "BIGINT"
        VARCHAR plan_no UK "采购计划编号"
        DATE plan_date "计划日期"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    pur_purchase_plan_item {
        BIGINT id PK "BIGINT"
        BIGINT plan_id FK "采购计划头ID"
        BIGINT material_id FK "物料ID"
        DECIMAL required_qty "需求数量"
        DECIMAL ordered_qty "已下单数量"
        DATE required_date "需求日期"
        VARCHAR source_type "来源类型 MRP/REORDER/MANUAL"
        INT source_reference_id "来源单据ID（多态引用）"
        BIGINT supplier_id FK "建议供应商ID"
        VARCHAR status "状态"
        VARCHAR remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    pur_receipt {
        BIGINT id PK "BIGINT"
        VARCHAR receipt_no UK "到货单号"
        BIGINT purchase_order_id FK "采购订单ID"
        BIGINT supplier_id FK "供应商ID"
        BIGINT warehouse_id FK "收货仓库ID"
        DATE receipt_date "到货日期"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    pur_receipt_item {
        BIGINT id PK "BIGINT"
        BIGINT receipt_id FK "到货单头ID"
        BIGINT order_item_id FK "采购订单行ID"
        BIGINT material_id FK "物料ID"
        BIGINT location_id FK "收货库位ID"
        DECIMAL quantity "到货数量"
        DECIMAL qualified_qty "合格数量"
        VARCHAR remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    pur_supplier {
        BIGINT id PK "BIGINT"
        VARCHAR supplier_code UK "供应商编码"
        VARCHAR supplier_name "供应商名称"
        VARCHAR contact_person "联系人"
        VARCHAR phone "联系电话"
        VARCHAR email "邮箱"
        VARCHAR address "地址"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    pur_supplier_evaluation {
        BIGINT id PK "BIGINT"
        BIGINT supplier_id FK "供应商ID"
        DATE evaluate_date "评价日期"
        DECIMAL quality_score "质量评分（0~100）"
        DECIMAL delivery_score "交期评分（0~100）"
        DECIMAL price_score "价格评分（0~100）"
        DECIMAL total_score "综合评分"
        BIGINT evaluator_id FK "评价人（sys_personnel.id）"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    pur_supplier_material {
        BIGINT id PK "BIGINT"
        BIGINT supplier_id FK "供应商ID"
        BIGINT material_id FK "物料ID"
        BOOLEAN is_primary "是否主供应商"
        DECIMAL supply_price "供货单价"
        INT lead_time_days "供货提前期（天）"
        DECIMAL min_order_qty "最小起订量"
        VARCHAR status "状态"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sys_personnel ||--o{ pur_order : "pur_order.buyer_id → sys_personnel.id (ON DELETE RESTRICT)"
    pur_supplier ||--o{ pur_order : "pur_order.supplier_id → pur_supplier.id (ON DELETE RESTRICT)"
    sys_material ||--o{ pur_order_item : "pur_order_item.material_id → sys_material.id (ON DELETE RESTRICT)"
    pur_order ||--o{ pur_order_item : "pur_order_item.order_id → pur_order.id (ON DELETE CASCADE)"
    sys_material ||--o{ pur_purchase_plan_item : "pur_purchase_plan_item.material_id → sys_material.id (ON DELETE RESTRICT)"
    pur_purchase_plan ||--o{ pur_purchase_plan_item : "pur_purchase_plan_item.plan_id → pur_purchase_plan.id (ON DELETE CASCADE)"
    pur_supplier ||--o{ pur_purchase_plan_item : "pur_purchase_plan_item.supplier_id → pur_supplier.id (ON DELETE RESTRICT)"
    pur_order ||--o{ pur_receipt : "pur_receipt.purchase_order_id → pur_order.id (ON DELETE RESTRICT)"
    pur_supplier ||--o{ pur_receipt : "pur_receipt.supplier_id → pur_supplier.id (ON DELETE RESTRICT)"
    inv_warehouse ||--o{ pur_receipt : "pur_receipt.warehouse_id → inv_warehouse.id (ON DELETE RESTRICT)"
    inv_location ||--o{ pur_receipt_item : "pur_receipt_item.location_id → inv_location.id (ON DELETE RESTRICT)"
    sys_material ||--o{ pur_receipt_item : "pur_receipt_item.material_id → sys_material.id (ON DELETE RESTRICT)"
    pur_order_item ||--o{ pur_receipt_item : "pur_receipt_item.order_item_id → pur_order_item.id (ON DELETE RESTRICT)"
    pur_receipt ||--o{ pur_receipt_item : "pur_receipt_item.receipt_id → pur_receipt.id (ON DELETE CASCADE)"
    sys_personnel ||--o{ pur_supplier_evaluation : "pur_supplier_evaluation.evaluator_id → sys_personnel.id (ON DELETE RESTRICT)"
    pur_supplier ||--o{ pur_supplier_evaluation : "pur_supplier_evaluation.supplier_id → pur_supplier.id (ON DELETE CASCADE)"
    sys_material ||--o{ pur_supplier_material : "pur_supplier_material.material_id → sys_material.id (ON DELETE RESTRICT)"
    pur_supplier ||--o{ pur_supplier_material : "pur_supplier_material.supplier_id → pur_supplier.id (ON DELETE CASCADE)"
```

## 三、外键关系明细

| 子表 | 子列 | 父表 | ON DELETE | 跨模块 |
| --- | --- | --- | --- | --- |
| `pur_order` | `buyer_id` | `sys_personnel` | RESTRICT | 是 |
| `pur_order` | `supplier_id` | `pur_supplier` | RESTRICT | 否 |
| `pur_order_item` | `material_id` | `sys_material` | RESTRICT | 是 |
| `pur_order_item` | `order_id` | `pur_order` | CASCADE | 否 |
| `pur_purchase_plan_item` | `material_id` | `sys_material` | RESTRICT | 是 |
| `pur_purchase_plan_item` | `plan_id` | `pur_purchase_plan` | CASCADE | 否 |
| `pur_purchase_plan_item` | `supplier_id` | `pur_supplier` | RESTRICT | 否 |
| `pur_receipt` | `purchase_order_id` | `pur_order` | RESTRICT | 否 |
| `pur_receipt` | `supplier_id` | `pur_supplier` | RESTRICT | 否 |
| `pur_receipt` | `warehouse_id` | `inv_warehouse` | RESTRICT | 是 |
| `pur_receipt_item` | `location_id` | `inv_location` | RESTRICT | 是 |
| `pur_receipt_item` | `material_id` | `sys_material` | RESTRICT | 是 |
| `pur_receipt_item` | `order_item_id` | `pur_order_item` | RESTRICT | 否 |
| `pur_receipt_item` | `receipt_id` | `pur_receipt` | CASCADE | 否 |
| `pur_supplier_evaluation` | `evaluator_id` | `sys_personnel` | RESTRICT | 是 |
| `pur_supplier_evaluation` | `supplier_id` | `pur_supplier` | CASCADE | 否 |
| `pur_supplier_material` | `material_id` | `sys_material` | RESTRICT | 是 |
| `pur_supplier_material` | `supplier_id` | `pur_supplier` | CASCADE | 否 |
