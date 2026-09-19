# 销售管理 模块 ER 图（`sal_`）

> 自动内省 `Base.metadata` 生成；本文件只覆盖 `sal_` 前缀的 8 张表。
> 全库关系与跨模块外键见 [`full-er-diagram.md`](./full-er-diagram.md)，
> 字段完整说明见 [`physical-data-model.md`](./physical-data-model.md)。

## 一、本模块表清单

| 表名 | ORM 类 | 说明 | 字段数 |
| --- | --- | --- | --- |
| `sal_customer` | `SalCustomer` | 客户主数据 | 14 |
| `sal_forecast` | `SalForecast` | 销售预测：按月对某物料的预测量，是 Planning 的需求来源之一 | 12 |
| `sal_order` | `SalOrder` | 销售订单头 | 13 |
| `sal_order_item` | `SalOrderItem` | 销售订单行。`delivered_qty` 由发货流程回写 | 13 |
| `sal_return` | `SalReturn` | 销售退货单头。确认退货时调用 inventory 接口入库 | 12 |
| `sal_return_item` | `SalReturnItem` | 退货明细行 | 13 |
| `sal_shipment` | `SalShipment` | 销售发货单头。确认发货时调用 inventory 接口出库 | 11 |
| `sal_shipment_item` | `SalShipmentItem` | 发货明细行 | 12 |

## 二、ER 图（含全部字段）

```mermaid
erDiagram
    sal_customer {
        BIGINT id PK "BIGINT"
        VARCHAR customer_code UK "客户编码"
        VARCHAR customer_name "客户名称"
        VARCHAR contact_person "联系人"
        VARCHAR phone "联系电话"
        VARCHAR email "邮箱"
        VARCHAR address "地址"
        DECIMAL credit_limit "信用额度"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sal_forecast {
        BIGINT id PK "BIGINT"
        VARCHAR forecast_no UK "预测单号"
        BIGINT customer_id FK "客户ID"
        BIGINT material_id FK "物料ID"
        VARCHAR forecast_month "预测月份（YYYY-MM）"
        DECIMAL forecast_qty "预测数量"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sal_order {
        BIGINT id PK "BIGINT"
        VARCHAR order_no UK "销售订单号"
        BIGINT customer_id FK "客户ID"
        DATE order_date "订单日期"
        DATE delivery_date "要求交货日期"
        BIGINT salesperson_id FK "销售员（sys_personnel.id）"
        DECIMAL total_amount "订单总金额"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sal_order_item {
        BIGINT id PK "BIGINT"
        BIGINT order_id FK "订单头ID"
        INT line_no "行号"
        BIGINT material_id FK "物料ID"
        DECIMAL quantity "订单数量"
        DECIMAL delivered_qty "已发货数量"
        DECIMAL unit_price "单价"
        DECIMAL amount "金额"
        VARCHAR remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sal_return {
        BIGINT id PK "BIGINT"
        VARCHAR return_no UK "退货单号"
        BIGINT order_id FK "原销售订单ID"
        BIGINT customer_id FK "客户ID"
        DATE return_date "退货日期"
        VARCHAR reason "退货原因"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sal_return_item {
        BIGINT id PK "BIGINT"
        BIGINT return_id FK "退货单头ID"
        BIGINT material_id FK "物料ID"
        BIGINT warehouse_id FK "退回仓库ID"
        BIGINT location_id FK "退回库位ID"
        DECIMAL quantity "退货数量"
        VARCHAR quality_status "质量状态 QUALIFIED/DEFECTIVE/SCRAP"
        VARCHAR reason "行退货原因"
        VARCHAR remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sal_shipment {
        BIGINT id PK "BIGINT"
        VARCHAR shipment_no UK "发货单号"
        BIGINT order_id FK "销售订单ID"
        BIGINT customer_id FK "客户ID"
        DATE shipment_date "发货日期"
        VARCHAR status "状态"
        TEXT remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sal_shipment_item {
        BIGINT id PK "BIGINT"
        BIGINT shipment_id FK "发货单头ID"
        BIGINT order_item_id FK "销售订单行ID"
        BIGINT material_id FK "物料ID"
        BIGINT warehouse_id FK "发货仓库ID"
        BIGINT location_id FK "发货库位ID"
        DECIMAL quantity "发货数量"
        VARCHAR remark "备注"
        BIGINT created_by "创建人ID（sys_user.id）"
        BIGINT updated_by "更新人ID（sys_user.id）"
        DATETIME created_at "创建时间"
        DATETIME updated_at "更新时间"
    }
    sal_customer ||--o{ sal_forecast : "sal_forecast.customer_id → sal_customer.id (ON DELETE RESTRICT)"
    sys_material ||--o{ sal_forecast : "sal_forecast.material_id → sys_material.id (ON DELETE RESTRICT)"
    sal_customer ||--o{ sal_order : "sal_order.customer_id → sal_customer.id (ON DELETE RESTRICT)"
    sys_personnel ||--o{ sal_order : "sal_order.salesperson_id → sys_personnel.id (ON DELETE RESTRICT)"
    sys_material ||--o{ sal_order_item : "sal_order_item.material_id → sys_material.id (ON DELETE RESTRICT)"
    sal_order ||--o{ sal_order_item : "sal_order_item.order_id → sal_order.id (ON DELETE CASCADE)"
    sal_customer ||--o{ sal_return : "sal_return.customer_id → sal_customer.id (ON DELETE RESTRICT)"
    sal_order ||--o{ sal_return : "sal_return.order_id → sal_order.id (ON DELETE RESTRICT)"
    inv_location ||--o{ sal_return_item : "sal_return_item.location_id → inv_location.id (ON DELETE RESTRICT)"
    sys_material ||--o{ sal_return_item : "sal_return_item.material_id → sys_material.id (ON DELETE RESTRICT)"
    sal_return ||--o{ sal_return_item : "sal_return_item.return_id → sal_return.id (ON DELETE CASCADE)"
    inv_warehouse ||--o{ sal_return_item : "sal_return_item.warehouse_id → inv_warehouse.id (ON DELETE RESTRICT)"
    sal_customer ||--o{ sal_shipment : "sal_shipment.customer_id → sal_customer.id (ON DELETE RESTRICT)"
    sal_order ||--o{ sal_shipment : "sal_shipment.order_id → sal_order.id (ON DELETE RESTRICT)"
    inv_location ||--o{ sal_shipment_item : "sal_shipment_item.location_id → inv_location.id (ON DELETE RESTRICT)"
    sys_material ||--o{ sal_shipment_item : "sal_shipment_item.material_id → sys_material.id (ON DELETE RESTRICT)"
    sal_order_item ||--o{ sal_shipment_item : "sal_shipment_item.order_item_id → sal_order_item.id (ON DELETE RESTRICT)"
    sal_shipment ||--o{ sal_shipment_item : "sal_shipment_item.shipment_id → sal_shipment.id (ON DELETE CASCADE)"
    inv_warehouse ||--o{ sal_shipment_item : "sal_shipment_item.warehouse_id → inv_warehouse.id (ON DELETE RESTRICT)"
```

## 三、外键关系明细

| 子表 | 子列 | 父表 | ON DELETE | 跨模块 |
| --- | --- | --- | --- | --- |
| `sal_forecast` | `customer_id` | `sal_customer` | RESTRICT | 否 |
| `sal_forecast` | `material_id` | `sys_material` | RESTRICT | 是 |
| `sal_order` | `customer_id` | `sal_customer` | RESTRICT | 否 |
| `sal_order` | `salesperson_id` | `sys_personnel` | RESTRICT | 是 |
| `sal_order_item` | `material_id` | `sys_material` | RESTRICT | 是 |
| `sal_order_item` | `order_id` | `sal_order` | CASCADE | 否 |
| `sal_return` | `customer_id` | `sal_customer` | RESTRICT | 否 |
| `sal_return` | `order_id` | `sal_order` | RESTRICT | 否 |
| `sal_return_item` | `location_id` | `inv_location` | RESTRICT | 是 |
| `sal_return_item` | `material_id` | `sys_material` | RESTRICT | 是 |
| `sal_return_item` | `return_id` | `sal_return` | CASCADE | 否 |
| `sal_return_item` | `warehouse_id` | `inv_warehouse` | RESTRICT | 是 |
| `sal_shipment` | `customer_id` | `sal_customer` | RESTRICT | 否 |
| `sal_shipment` | `order_id` | `sal_order` | RESTRICT | 否 |
| `sal_shipment_item` | `location_id` | `inv_location` | RESTRICT | 是 |
| `sal_shipment_item` | `material_id` | `sys_material` | RESTRICT | 是 |
| `sal_shipment_item` | `order_item_id` | `sal_order_item` | RESTRICT | 否 |
| `sal_shipment_item` | `shipment_id` | `sal_shipment` | CASCADE | 否 |
| `sal_shipment_item` | `warehouse_id` | `inv_warehouse` | RESTRICT | 是 |
