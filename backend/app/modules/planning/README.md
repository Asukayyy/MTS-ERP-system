# Planning Module（计划管理）

> 状态：**已实现**（后端 62 个操作；含真实多层 BOM 展开 MRP 引擎）
> 本课程设计中**生产相关功能全部归属本模块**，不设独立的 production 模块。

## 模块职责

负责需求汇总、MPS、MRP 与生产作业计划。MRP 结果分流后：MAKE 件由本模块生成生产计划，
BUY 件通过契约交给 procurement 生成采购计划。

**主链路（唯一）**：销售订单 + 补库申请 → 统一需求 `pln_demand`（销售订单记 `SALES`、
补库申请记 `STOCKFILL`）→ `/mps/from-demands` 汇总生成 MPS → `/mrp/run`（仅以 MPS 为输入）
→ MRP 结果分流。销售预测（`FORECAST`）单独留存，**不参与 MPS 汇总**；MPS 的手工新增
与课程案例导入仅作为补充录入手段，不再作为 MRP 的需求旁路。

## 已实现功能

| 功能 | 说明 |
| --- | --- |
| 需求管理 | `pln_demand` 维护；`/demands/from-sales` 拉取销售订单需求（`SALES`）、`/demands/from-forecast` 拉取已确认销售预测（`FORECAST`，**不参与 MPS 汇总**）；`/demands/from-replenishment` 接补库需求（**仅转计划 `PRODUCTION`**，记 `STOCKFILL`；转采购 `REORDER` 由采购模块受理） |
| 主生产计划 MPS | 头 + 明细增删改查、状态流转（确认后只读）；`/mps/from-demands` **由统一需求汇总生成 MPS**（按「物料 + 需求月份」聚合已确认的销售订单 `SALES` + 补库申请 `STOCKFILL`，需求置 `RELEASED` 并在 MPS 行记录来源需求 ID）；`/mps/import/{preview,confirm}` 课程数据两段式导入 |
| MRP 运算 | `/mrp/run` 触发，**只接受 `mps_id`**（需求必须先汇总为 MPS，不接受需求 ID 或销售订单直算）；多层 BFS 展开、毛需求 / 净需求 / 建议下达日期计算；每次运行独立 `pln_mrp_run`，历史不覆盖 |
| MRP 结果 | 按运行查询结果、`/mrp/runs/{id}/explain` 展示展开过程、结果状态流转 |
| 结果分流 | `/mrp/runs/{id}/create-production-plans`（MAKE→生产计划）、`/mrp/runs/{id}/create-purchase-plan`（BUY→采购计划） |
| 生产计划 | 增删改查、状态流转、`/production-plans/from-mrp` |
| 派工单 | 增删改查、状态流转；`/dispatch-orders/from-plans` 按生产计划的工艺路线**逐工序自动生成** DRAFT 单据（作业人员留空待指派），`PATCH /dispatch-orders/{id}` 人工审核调整 |
| 领料单 | 头 + 明细，确认时经 `inventory.contract.push_outbound_order` 推送**待出库单**（`MATERIAL_REQUISITION`，不改结存，仓库由库存管理指定并确认）；`/requisitions/from-plans` 按生产计划的 BOM 直接子件自动生成 DRAFT 领料单，`PATCH /requisitions/{id}` 人工审核调整（含明细整表替换） |
| 完工报告 | 头 + 明细，确认时经 `inventory.contract.push_inbound_order` 推送**待入库单**（`PRODUCTION_COMPLETION`，按合格数量，不改结存）；`/completion-reports/from-plans` 按生产计划自动生成 DRAFT 完工报告（产出物料与剩余完工数量预填，报工日期留空），`PATCH /completion-reports/{id}` 人工补填 |
| 单据删除 | 生产作业计划 / 派工单 / 领料单 / 完工报告均支持单条 `DELETE` 与批量 `POST /batch-delete`；**仅 DRAFT / CANCELLED 可删**，其余状态报 `3006`（只能取消）。已确认入库的领料单 / 完工报告写有库存流水，不可删除 |
| 统计 | `/stats` |

> **删除顺序**：`pln_dispatch_order` / `pln_material_requisition` / `pln_completion_report`
> 均以 `plan_id` 外键（RESTRICT）引用作业计划，完工报告还以 `dispatch_id` 引用派工单。
> 存在下游引用时删除请求返回 `3000` 并提示先清理，正确顺序为
> **完工报告 → 派工单 / 领料单 → 生产作业计划**；领料单删除时其明细行一并清理。

## MRP 计算规则（实现要点）

- 多层展开：`子件毛需求 = 父件下达量（净需求取整后）× 用量`（**损耗率不参与计算**）
- 净需求：`净需求 = 毛需求 + 安全库存 − 可用量`（不足取 0）
- 建议下达量：**自制件（MAKE）向上取整为整数件**，采购件（BUY）保留原精度；
  生产作业计划的 `planned_qty` 取整数下达量，保证不出现小数件
- 需求时间：`子件需求日期 = 父件需求日期 − lead_time_offset`
- 建议下达日期：`需求日期 − lead_time_days`
- 供应分流：`supply_type == MAKE` → 生产计划；`BUY` → 采购计划
- 可用库存按批次只抵扣一次（`remaining_available` 映射），避免同一批库存被重复使用
- BOM 存在循环引用时抛 `3001`

## 输入

- 销售需求 / 销售订单（来自 sales 模块，经 `sales.contract`）
- BOM、物料、提前期主数据（来自 system 模块，经 `system.contract`）
- 实时库存与可用量（来自 inventory 模块，经 `inventory.contract`）
- 补库需求（来自 inventory 模块，经 `inventory.contract.get_replenishment_request`；**只取转计划 `source_type=PRODUCTION`**）

## 输出

- MRP 结果
- 采购需求（交 procurement 模块，经 `procurement.contract.create_purchase_plan_from_mrp`）
- 生产作业计划 / 派工单 / 领料单 / 完工报告（领料与完工经 `inventory.contract` 执行）

> 列表 / 详情出参除保留 `*_id` 外，同时返回可直接展示的业务标识：
> `material_code` / `material_name`、`plan_no`（作业计划编号）、`dispatch_no`、
> `mps_no`、`warehouse_code` / `warehouse_name`、`worker_name`、
> `source_demand_nos`（MPS 行来源需求单号），均由 service 层批量补齐，不做跨模块 JOIN。

## 数据表（Owner: planning，共 10 张）

`pln_demand`、`pln_mps`、`pln_mps_item`、`pln_mrp_run`、`pln_mrp_result`、
`pln_production_plan`、`pln_dispatch_order`、`pln_material_requisition`、
`pln_material_requisition_item`、`pln_completion_report`

> 表结构详见 `docs/database/planning-er.md` 与 `docs/database/full-er-diagram.md`。

## 对外契约（唯一跨模块入口）

`backend/app/modules/planning/contract.py`：

- `create_production_plan_from_replenishment(db, request_id)` → `{"plan_id", "plan_no"}`
- `create_sales_demand_from_order(db, ...)` → 销售订单确认时登记 `SALES` 需求（`CONFIRMED`，数量为订单未交付总量）
- `cancel_sales_demands_for_order(db, order_id)` → 订单取消时作废未进入 MPS 的销售计划需求
- `create_production_plan_from_mrp_result(db, mrp_result_id)` → 由 MRP 结果直接建生产计划
- `get_mrp_results(db, result_ids)` → 供 procurement 从 MRP BUY 结果生成采购计划
- `get_open_production_qty(db, material_id)` → 在制量

## 依赖的其它模块契约

| 依赖 | 用途 |
| --- | --- |
| `system.contract.get_active_bom_children` | MRP 逐层展开、按计划生成领料单 |
| `system.contract.get_active_routing_operations` | 按计划生成派工单（读生效工艺路线工序） |
| `system.contract.get_material` / `log_operation` | 提前期与供应类型、操作日志 |
| `sales.contract.get_open_order_demand` / `get_confirmed_forecast_demand` | 需求汇总 |
| `inventory.contract.get_stock_snapshot` | 可用库存快照 |
| `inventory.contract.push_outbound_order` / `push_inbound_order` | 领料推送待出库单 / 完工推送待入库单 |
| `inventory.contract.cancel_pending_inout_orders` | 领料 / 完工取消时撤销尚未确认的出入库单 |
| `inventory.contract.get_replenishment_request` | 补库需求转生产计划 |

## 主要接口分组

| 分组 | 前缀 |
| --- | --- |
| 需求 | `/api/v1/planning/demands` |
| MPS | `/api/v1/planning/mps` |
| MRP | `/api/v1/planning/mrp/run`、`/mrp/runs`、`/mrp/results` |
| 生产计划 | `/api/v1/planning/production-plans`（含 `POST /batch-delete`） |
| 派工单 | `/api/v1/planning/dispatch-orders`（含 `POST /from-plans`、`PATCH /{id}`、`POST /batch-delete`） |
| 领料单 | `/api/v1/planning/requisitions`（含 `POST /from-plans`、`PATCH /{id}`、`POST /batch-delete`） |
| 完工报告 | `/api/v1/planning/completion-reports`（含 `POST /from-plans`、`PATCH /{id}`、`POST /batch-delete`） |
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