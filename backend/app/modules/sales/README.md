# Sales Module（销售管理）

> 状态：**已实现**（后端 24 个路径；实现详见 `service.py`）

## 模块职责

管理客户、销售预测、销售订单与销售发货 / 退货，向 planning 模块提供销售需求，
并由本模块驱动 inventory 完成发货出库与退货入库，形成销售闭环。

## 已实现功能

| 功能 | 说明 |
| --- | --- |
| 客户管理 | 增删改查、状态流转、按关键字检索 |
| 销售预测 | 预测录入 / 修改 / 状态流转，按月份区间查询 |
| 销售订单 | 头 + 明细，状态机 `DRAFT → CONFIRMED → IN_PROGRESS → COMPLETED`（可 `CANCELLED`） |
| 销售发货 | 新建 / 确认 / 取消；确认时调用库存契约出库并回写 `delivered_qty` |
| 销售退货 | 新建 / 确认 / 取消；确认时调用库存契约入库，行级带质量状态 `QUALIFIED/DEFECTIVE/SCRAP` |
| 销售产品查询 | `/products` 直接取 `system.contract.get_finished_materials`，只列 FINISHED + ACTIVE |
| 报表与统计 | 订单状态 / 发货 / 退货 / 销量报表 + `/stats` |

## 输入

- 成品物料主数据（来自 system 模块，经 `system.contract`）
- 客户基础信息（本模块自持）

## 输出

- 销售需求 / 销售预测（供 planning MRP）
- 销售订单、发货单、退货单
- 出库 / 入库指令（经 `inventory.contract` 执行）

## 数据表（Owner: sales，共 8 张）

`sal_customer`、`sal_forecast`、`sal_order`、`sal_order_item`、`sal_shipment`、
`sal_shipment_item`、`sal_return`、`sal_return_item`

> 表结构详见 `docs/database/sales-er.md`。

## 对外契约（唯一跨模块入口）

`backend/app/modules/sales/contract.py`：

- `get_open_order_demand(db, on_date=None)` → 未交付的订单需求，供 planning 汇总需求
- `get_confirmed_forecast_demand(db, month_from=None, month_to=None)` → 已确认预测需求
- `get_open_order_qty(db, material_id)` → 某物料未交付订单量
- `get_customer_name(db, customer_id)` → 客户名称

## 依赖的其它模块契约

| 依赖 | 用途 |
| --- | --- |
| `system.contract.get_finished_materials` | 销售产品下拉 |
| `system.contract.log_operation` | 写操作日志（同事务） |
| `inventory.contract.decrease_stock` | 发货确认出库（`SALES_SHIPMENT`） |
| `inventory.contract.increase_stock` | 退货确认入库（`SALES_RETURN`） |

## 主要接口分组

| 分组 | 前缀 |
| --- | --- |
| 客户 | `/api/v1/sales/customers` |
| 预测 | `/api/v1/sales/forecasts` |
| 订单 | `/api/v1/sales/orders` |
| 发货 | `/api/v1/sales/shipments`（`/{id}/confirm`、`/{id}/cancel`） |
| 退货 | `/api/v1/sales/returns`（`/{id}/confirm`、`/{id}/cancel`） |
| 产品 | `/api/v1/sales/products` |
| 报表 / 统计 | `/api/v1/sales/reports/*`、`/stats`、`/health` |

完整清单见 `docs/api/api-contract.md`。

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/sales/router.py` |
| 后端模型 | `backend/app/modules/sales/models.py` |
| 数据访问 | `backend/app/modules/sales/repository.py` |
| 业务规则 | `backend/app/modules/sales/service.py` |
| 跨模块契约 | `backend/app/modules/sales/contract.py` |
| 后端测试 | `backend/tests/test_sales.py` |
| 前端接口 | `frontend/src/api/sales/` |
| 前端页面 | `frontend/src/views/sales/` |

## API 前缀

- 后端：`/api/v1/sales`
- 前端路由：`/sales`
- 业务错误码区段：`2000~2999`

| 码 | 含义 |
| --- | --- |
| 2000 | 入参 / 状态非法 |
| 2001 | 唯一性冲突（如客户编码重复） |
| 2002 | 已完结 / 已取消单据不可修改 |
| 2003 | 发货数量超过未发数量 |
| 2004 | 退货单与原订单客户不一致 |
| 2005 | 资源不存在 |
| 2006 | 单据状态不允许该操作 |