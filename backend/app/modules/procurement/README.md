# Procurement Module（采购管理）

> 状态：**已实现**（后端 27 个路径；实现详见 `service.py`）

## 模块职责

接收 planning 模块产生的 MRP 采购需求（BUY 件）与 inventory 的补库需求，完成供应商选择、
采购下单、到货登记与供应商评价；到货确认时经库存契约完成入库。

## 已实现功能

| 功能 | 说明 |
| --- | --- |
| 供应商管理 | 增删改查、状态流转 |
| 供应商-物料关系 | 供应关系与价格 / 提前期维护，重复关系抛 `4002` |
| 采购计划 | 头 + 明细；来源可为 MRP 结果或补库需求 |
| 采购订单 | `/orders/from-plan` 从采购计划生成；状态流转 |
| 到货登记 | 新建 / 确认 / 取消；确认时经 `inventory.contract.increase_stock` 入库（`PURCHASE_RECEIPT`） |
| 供应商评价 | 交付 / 质量 / 服务三项评分取简单平均（4 位小数），可按供应商查询 |
| 报表与统计 | 订单 / 计划 / 到货 / 待交 / 供应商评价报表 + `/stats` |

## 输入

- MRP 采购需求（来自 planning 模块，经 `planning.contract.get_mrp_results`）
- 补库需求（来自 inventory 模块，经 `inventory.contract.get_replenishment_request`）
- 物料主数据（来自 system 模块，经 `system.contract`）

## 输出

- 采购计划、采购订单
- 到货信息（经 `inventory.contract.increase_stock` 完成入库）

## 数据表（Owner: procurement，共 9 张）

`pur_supplier`、`pur_supplier_material`、`pur_purchase_plan`、`pur_purchase_plan_item`、
`pur_order`、`pur_order_item`、`pur_receipt`、`pur_receipt_item`、`pur_supplier_evaluation`

> 表结构详见 `docs/database/procurement-er.md`。

## 对外契约（唯一跨模块入口）

`backend/app/modules/procurement/contract.py`：

- `create_purchase_plan_from_mrp(db, mrp_result_ids)` → 由 MRP BUY 结果生成采购计划
- `create_purchase_plan_from_replenishment(db, request_id)` → 由补库需求生成采购计划
- `get_pending_receipt_qty(db, material_id)` → 某物料在途 / 未到货量（供 planning 抵扣）

> 幂等约定：同一来源若已存在未终结的采购计划，则复用并补充明细行，不重复建头。

## 依赖的其它模块契约

| 依赖 | 用途 |
| --- | --- |
| `system.contract.get_material` / `search_materials` / `log_operation` | 物料校验、日志 |
| `planning.contract.get_mrp_results` | MRP BUY 结果转采购计划 |
| `inventory.contract.get_replenishment_request` | 补库需求转采购计划 |
| `inventory.contract.increase_stock` | 到货确认入库 |

## 主要接口分组

| 分组 | 前缀 |
| --- | --- |
| 供应商 | `/api/v1/procurement/suppliers` |
| 供应商-物料 | `/api/v1/procurement/supplier-materials`、`/materials` |
| 采购计划 | `/api/v1/procurement/purchase-plans` |
| 采购订单 | `/api/v1/procurement/orders`、`/orders/from-plan` |
| 到货 | `/api/v1/procurement/receipts`（`/{id}/confirm`、`/{id}/cancel`） |
| 评价 | `/api/v1/procurement/evaluations`、`/evaluations/supplier/{supplier_id}` |
| 报表 / 统计 | `/api/v1/procurement/reports/*`、`/stats`、`/health` |

完整清单见 `docs/api/api-contract.md`。

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/procurement/router.py` |
| 后端模型 | `backend/app/modules/procurement/models.py` |
| 数据访问 | `backend/app/modules/procurement/repository.py` |
| 业务规则 | `backend/app/modules/procurement/service.py` |
| 跨模块契约 | `backend/app/modules/procurement/contract.py` |
| 后端测试 | `backend/tests/test_procurement.py` |
| 前端接口 | `frontend/src/api/procurement/` |
| 前端页面 | `frontend/src/views/procurement/` |

## API 前缀

- 后端：`/api/v1/procurement`
- 前端路由：`/procurement`
- 业务错误码区段：`4000~4999`

| 码 | 含义 |
| --- | --- |
| 4000 | 入参 / 状态非法 |
| 4001 | 供应商编码重复 |
| 4002 | 供应商-物料关系重复 |
| 4003 | 已确认 / 已下达 / 已完结单据不可修改 |
| 4004 | 到货数量超过未到货数量 |
| 4005 | 资源不存在 |
| 4006 | 单据状态不允许该流转 |
| 4007 | 跨模块契约尚未就绪 |