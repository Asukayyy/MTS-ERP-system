# Planning Module（计划管理）

> 状态：**已实现**（后端 36 个路径；含真实多层 BOM 展开 MRP 引擎）
> 本课程设计中**生产相关功能全部归属本模块**，不设独立的 production 模块。

## 模块职责

负责需求汇总、MPS、MRP 与生产作业计划。MRP 结果分流后：MAKE 件由本模块生成生产计划，
BUY 件通过契约交给 procurement 生成采购计划。

## 已实现功能

| 功能 | 说明 |
| --- | --- |
| 需求管理 | `pln_demand` 维护；`/demands/from-sales` 拉取销售订单与预测需求；`/demands/from-replenishment` 接补库需求 |
| 主生产计划 MPS | 头 + 明细增删改查、状态流转（确认后只读）、`/mps/import/{preview,confirm}` 课程数据两段式导入 |
| MRP 运算 | `/mrp/run` 触发；多层 BFS 展开、毛需求 / 净需求 / 建议下达日期计算；每次运行独立 `pln_mrp_run`，历史不覆盖 |
| MRP 结果 | 按运行查询结果、`/mrp/runs/{id}/explain` 展示展开过程、结果状态流转 |
| 结果分流 | `/mrp/runs/{id}/create-production-plans`（MAKE→生产计划）、`/mrp/runs/{id}/create-purchase-plan`（BUY→采购计划） |
| 生产计划 | 增删改查、状态流转、`/production-plans/from-mrp` |
| 派工单 | 增删改查、状态流转 |
| 领料单 | 头 + 明细，确认时经 `inventory.contract.decrease_stock` 出库 |
| 完工报告 | 头 + 明细，确认时经 `inventory.contract.increase_stock` 入库 |
| 统计 | `/stats` |

## MRP 计算规则（实现要点）

- 多层展开：`子件毛需求 = 父件净需求 × 用量 × (1 + 损耗率)`
- 需求时间：`子件需求日期 = 父件需求日期 − lead_time_offset`
- 净需求：`净需求 = max(毛需求 + 安全库存 − 可用库存, 0)`
- 建议下达日期：`需求日期 − lead_time_days`
- 供应分流：`supply_type == MAKE` → 生产计划；`BUY` → 采购计划
- 可用库存按批次只抵扣一次（`remaining_available` 映射），避免同一批库存被重复使用
- BOM 存在循环引用时抛 `3001`

## 输入

- 销售需求 / 销售订单（来自 sales 模块，经 `sales.contract`）
- BOM、物料、提前期主数据（来自 system 模块，经 `system.contract`）
- 实时库存与可用量（来自 inventory 模块，经 `inventory.contract`）
- 补库需求（来自 inventory 模块，经 `inventory.contract.get_replenishment_request`）

## 输出

- MRP 结果
- 采购需求（交 procurement 模块，经 `procurement.contract.create_purchase_plan_from_mrp`）
- 生产作业计划 / 派工单 / 领料单 / 完工报告（领料与完工经 `inventory.contract` 执行）

## 数据表（Owner: planning，共 10 张）

`pln_demand`、`pln_mps`、`pln_mps_item`、`pln_mrp_run`、`pln_mrp_result`、
`pln_production_plan`、`pln_dispatch_order`、`pln_material_requisition`、
`pln_material_requisition_item`、`pln_completion_report`

> 表结构详见 `docs/database/planning-er.md` 与 `docs/database/full-er-diagram.md`。

## 对外契约（唯一跨模块入口）

`backend/app/modules/planning/contract.py`：

- `create_production_plan_from_replenishment(db, request_id)` → `{"plan_id", "plan_no"}`
- `create_production_plan_from_mrp_result(db, mrp_result_id)` → 由 MRP 结果直接建生产计划
- `get_mrp_results(db, result_ids)` → 供 procurement 从 MRP BUY 结果生成采购计划
- `get_open_production_qty(db, material_id)` → 在制量

## 依赖的其它模块契约

| 依赖 | 用途 |
| --- | --- |
| `system.contract.get_active_bom_children` | MRP 逐层展开 |
| `system.contract.get_material` / `log_operation` | 提前期与供应类型、操作日志 |
| `sales.contract.get_open_order_demand` / `get_confirmed_forecast_demand` | 需求汇总 |
| `inventory.contract.get_stock_snapshot` | 可用库存快照 |
| `inventory.contract.decrease_stock` / `increase_stock` | 领料出库 / 完工入库 |
| `inventory.contract.get_replenishment_request` | 补库需求转生产计划 |

## 主要接口分组

| 分组 | 前缀 |
| --- | --- |
| 需求 | `/api/v1/planning/demands` |
| MPS | `/api/v1/planning/mps` |
| MRP | `/api/v1/planning/mrp/run`、`/mrp/runs`、`/mrp/results` |
| 生产计划 | `/api/v1/planning/production-plans` |
| 派工单 | `/api/v1/planning/dispatch-orders` |
| 领料单 | `/api/v1/planning/requisitions` |
| 完工报告 | `/api/v1/planning/completion-reports` |
| 统计 | `/api/v1/planning/stats`、`/health` |

完整清单见 `docs/api/api-contract.md`。

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/planning/router.py` |
| 后端模型 | `backend/app/modules/planning/models.py` |
| 数据访问 | `backend/app/modules/planning/repository.py` |
| 业务规则 | `backend/app/modules/planning/service.py` |
| 跨模块契约 | `backend/app/modules/planning/contract.py` |
| 后端测试 | `backend/tests/test_planning.py` |
| 前端接口 | `frontend/src/api/planning/` |
| 前端页面 | `frontend/src/views/planning/` |
| 设计与 DFD | `docs/planning/` |

## API 前缀

- 后端：`/api/v1/planning`
- 前端路由：`/planning`
- 业务错误码区段：`3000~3999`

| 码 | 含义 |
| --- | --- |
| 3000 | 入参 / 状态非法 |
| 3001 | BOM 存在循环引用 |
| 3002 | 已确认 / 已下达的 MPS 只读 |
| 3003 | 资源不存在 |
| 3004 | 唯一性冲突 |
| 3005 | 跨模块契约尚未就绪 |
| 3006 | 状态机不允许该流转 |
| 3007 | 导入数据校验失败 |