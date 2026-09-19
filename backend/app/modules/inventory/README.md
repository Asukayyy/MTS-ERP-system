# Inventory Module（库存管理）

> 状态：**已实现**（后端 36 个路径；库存变动一律「写流水 + 更新结存」）

## 模块职责

管理仓库、库位、库存结存与库存流水，维护实时库存状态，并向 planning（MRP 可用量）、
sales（发货 / 退货）、procurement（到货入库）、planning（领料 / 完工）提供库存能力。

**库存铁律**：任何库存变动必须在同一事务内同时写入 `inv_transaction` 流水并更新
`inv_balance` 结存；禁止绕过流水直接改结存；禁止出现负库存。

## 已实现功能

| 功能 | 说明 |
| --- | --- |
| 仓库 / 库位 | 增删改查、状态流转；库位被结存引用时禁止删除（`5007`） |
| 库存结存 | `/balances` 分页查询、`/balances/available` 可用量查询 |
| 库存流水 | `/transactions` 按类型 / 来源 / 仓库 / 日期区间查询 |
| 入出库 | `/stock/increase`、`/stock/decrease`（`SELECT ... FOR UPDATE` + 事务内复校，不足抛 `5001`） |
| 移库 | 头 + 明细，确认时写 `TRANSFER_OUT` + `TRANSFER_IN` 两条流水 |
| 盘点 | 头 + 明细，确认时按差异写 `ADJUST` 流水 |
| 订货点 | `/reorder-rules` 维护 + `/reorder-rules/suggestions` 补货建议 |
| 补库需求 | `/replenishment-requests`，`generate-from-reorder-rules` 批量生成，确认时按供需分流到 procurement / planning |
| 课程期初库存导入 | `/import/initial-stock/{preview,confirm}` 两段式导入 |
| 报表与统计 | 库存汇总 / 低库存 / 流水汇总报表 + `/stats` |

## 输入

- 采购到货信息（来自 procurement 模块，经 `increase_stock`）
- 生产领料单、完工入库单（来自 planning 模块，经 `decrease_stock` / `increase_stock`）
- 销售发货 / 退货（来自 sales 模块，经 `decrease_stock` / `increase_stock`）
- 课程期初库存 `data/seed/course_chair_case.json`

## 输出

- 实时库存结存与可用量（供 planning MRP 抵扣）
- 库存流水（审计与追溯的唯一依据）
- 补库需求（交 procurement 或 planning 执行）

## 数据表（Owner: inventory，共 10 张）

`inv_warehouse`、`inv_location`、`inv_balance`、`inv_transaction`、`inv_transfer`、
`inv_transfer_item`、`inv_stocktake`、`inv_stocktake_item`、`inv_reorder_rule`、
`inv_replenishment_request`

> 表结构详见 `docs/database/inventory-er.md`。

## 对外契约（唯一跨模块入口）

`backend/app/modules/inventory/contract.py`：

- 查询：`get_on_hand_qty` / `get_available_qty` / `get_stock_snapshot`
- 变动：`increase_stock(db, *, material_id, quantity, warehouse_id, location_id=None,
  source_module, source_type, source_reference_id=None, source_no=None,
  unit_cost=0, biz_date=None, operator_id=None, remark=None)`
- 变动：`decrease_stock(...)`（同上签名，库存不足抛 `5001`）
- 补库：`create_replenishment_request(...)` / `get_replenishment_request(db, request_id)`

契约函数**永不 `db.commit()`**，运行在调用方事务内，保证跨模块操作的原子性。

## 被谁调用

| 调用方 | 场景 |
| --- | --- |
| `sales` | 发货确认 `decrease_stock`（`SALES_SHIPMENT`）、退货确认 `increase_stock`（`SALES_RETURN`） |
| `procurement` | 到货确认 `increase_stock`（`PURCHASE_RECEIPT`） |
| `planning` | 领料确认 `decrease_stock`、完工确认 `increase_stock` |

## 主要接口分组

| 分组 | 前缀 |
| --- | --- |
| 仓库 / 库位 | `/api/v1/inventory/warehouses`、`/locations` |
| 结存 / 流水 | `/api/v1/inventory/balances`、`/transactions` |
| 入出库 | `/api/v1/inventory/stock/increase`、`/stock/decrease` |
| 移库 | `/api/v1/inventory/transfers` |
| 盘点 | `/api/v1/inventory/stocktakes` |
| 订货点 / 补库 | `/api/v1/inventory/reorder-rules`、`/replenishment-requests` |
| 课程期初库存导入 | `/api/v1/inventory/import/initial-stock/{preview,confirm}` |
| 报表 / 统计 | `/api/v1/inventory/reports/*`、`/stats`、`/health` |

完整清单见 `docs/api/api-contract.md`。

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/inventory/router.py` |
| 后端模型 | `backend/app/modules/inventory/models.py` |
| 数据访问 | `backend/app/modules/inventory/repository.py` |
| 业务规则 | `backend/app/modules/inventory/service.py` |
| 跨模块契约 | `backend/app/modules/inventory/contract.py` |
| 后端测试 | `backend/tests/test_inventory.py` |
| 前端接口 | `frontend/src/api/inventory/` |
| 前端页面 | `frontend/src/views/inventory/` |

## API 前缀

- 后端：`/api/v1/inventory`
- 前端路由：`/inventory`
- 业务错误码区段：`5000~5999`

| 码 | 含义 |
| --- | --- |
| 5000 | 入参 / 状态非法 |
| 5001 | 库存不足 |
| 5002 | 跨模块契约尚未就绪 |
| 5003 | 单据状态不允许该操作 |
| 5004 | 资源不存在 |
| 5005 | 唯一性冲突 |
| 5006 | 调整后库存会为负 |
| 5007 | 库位已被库存引用，禁止删除 |