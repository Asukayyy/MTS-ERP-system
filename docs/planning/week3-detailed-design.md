# Planning Module Detailed Design（第 3 周：详细功能设计与数据结构模型）

Status: **Delivered**（实现见 `backend/app/modules/planning/`）

> 本文档描述计划管理模块的详细设计。第 2 周的功能初步设计见
> [week2-functional-design.md](week2-functional-design.md)；跨模块接口草案见
> [interface-draft.md](interface-draft.md)。
>
> **设计与实现的一致性以代码与自动生成文档为准**：
>
> | 内容 | 权威出处 |
> | --- | --- |
> | 表结构与字段 | `docs/database/physical-data-model.md`、`docs/database/planning-er.md` |
> | API 定义 | `docs/api/api-contract.md`（由 `create_app().openapi()` 导出） |
> | 页面设计 | `frontend/src/views/planning/` |
> | MRP 算法实现 | `backend/app/modules/planning/service.py` 的 `run_mrp()` |
> | 端到端验证 | `backend/tests/test_end_to_end_chair_mts.py` |

## 一、详细功能模型

| 子功能 | 实现入口 | 说明 |
| --- | --- | --- |
| 统一需求 | `pln_demand` | 手工维护 + `/demands/from-sales`（拉销售订单/预测）+ `/demands/from-replenishment`（接补库需求） |
| 主生产计划 MPS | `pln_mps` / `pln_mps_item` | 头 + 明细增删改查；确认后只读；`/mps/import/{preview,confirm}` 导入课程数据 |
| MRP 运算 | `pln_mrp_run` / `pln_mrp_result` | 多层 BFS 展开；每次运算独立批次，历史不覆盖 |
| MRP 解释 | `GET /mrp/runs/{run_id}/explain` | 按物料展示父件、层级、可用量消耗与净需求推导过程 |
| 结果分流 | `create_production_plans_from_run` / `create_purchase_plan_from_run` | MAKE → 生产计划；BUY → 经 `procurement.contract` 建采购计划 |
| 生产作业计划 | `pln_production_plan` | 可由 MRP 结果直接生成（`/production-plans/from-mrp`） |
| 派工单 | `pln_dispatch_order` | 挂生产计划，状态流转 |
| 领料单 | `pln_material_requisition`(+`_item`) | 确认时经 `inventory.contract.decrease_stock` 出库 |
| 完工报告 | `pln_completion_report` | 确认时经 `inventory.contract.increase_stock` 入库 |

## 二、状态机

主状态机（MPS / 生产计划 / 派工单共用）：

```
DRAFT ──▶ CONFIRMED ──▶ RELEASED ──▶ IN_PROGRESS ──▶ COMPLETED
  │            │              │              │
  └────────────┴──────────────┴──────────────┴──▶ CANCELLED

COMPLETED / CANCELLED 为终态，不可再流转
```

需求状态机（`pln_demand`）：

```
DRAFT ──▶ CONFIRMED ──▶ RELEASED ──▶ COMPLETED
  │            │              │
  └────────────┴──────────────┴──▶ CANCELLED
CONFIRMED 亦可直接 ──▶ COMPLETED
```

流转非法时抛 `3006`；已确认 / 已下达的 MPS 不可修改，抛 `3002`。

## 三、MRP 处理逻辑

实现见 `service.py::run_mrp()`，与代码逐条对应：

1. **第 0 层毛需求**来自三处：MPS 行（`planned_qty` / `end_date`）、指定 `pln_demand`
   （状态 `CONFIRMED` / `RELEASED`）、可选销售订单需求（`include_sales_demand`）。
2. **逐层展开（广度优先）**：每层先净算，再用**父件净需求**（不是毛需求）展开下一层：

   ```
   子件毛需求 = 父件净需求 × 用量 × (1 + 损耗率)
   子件需求日期 = 父件需求日期 − lead_time_offset
   ```

   无生效 BOM 的物料为叶子节点，停止展开。同层内同一物料若有多个父件：
   **毛需求求和、需求日期取最早、父件取首次出现者**。
   分支祖先路径上重现物料即判定 BOM 循环，抛 `3001`。
3. **净算**：可用量取 `inventory.contract.get_stock_snapshot`，安全库存与提前期取
   `system.contract.get_materials`：

   ```
   净需求 = max(毛需求 + 安全库存 − 可用库存, 0)
   建议下达量 = 净需求
   建议下达日期 = 需求日期 − 提前期天数
   ```

   供应类型取物料的 `supply_type`（`MAKE` / `BUY`）。
4. **可用库存只在本批次内消耗一次**：维护 `remaining_available[material_id]`，
   每次净算消耗 `min(剩余可用, 毛需求 + 安全库存)`，剩余量供本批次后续出现的同一物料继续使用，
   **因此同一物料出现两次不会被重复抵扣库存**。
5. **落库**：写入一个 `pln_mrp_run`（`IN_PROGRESS` → `COMPLETED`）及其全部结果行；
   每次运算都是新批次，历史结果不被覆盖。

MRP 结果字段：`gross_requirement`、`on_hand`、`available_quantity`、`safety_stock`、
`net_requirement`、`order_qty`、`supply_type`、`lead_time_days`、`requirement_date`、
`planned_release_date`、`bom_level`、`parent_material_id`、`status`。

## 四、数据实体关系与物理模型

10 张表（Owner: planning）：`pln_demand`、`pln_mps`、`pln_mps_item`、`pln_mrp_run`、
`pln_mrp_result`、`pln_production_plan`、`pln_dispatch_order`、
`pln_material_requisition`、`pln_material_requisition_item`、`pln_completion_report`。

关键关联（**模块内 FK；跨模块一律用 ID 引用，不建外键**）：

```
pln_mps ──1:N──▶ pln_mps_item
pln_mrp_run ──1:N──▶ pln_mrp_result ──N:1──▶ (sys_material.id，仅 ID 引用)
pln_production_plan ──▶ pln_dispatch_order
                     └─▶ pln_material_requisition ──1:N──▶ pln_material_requisition_item
                     └─▶ pln_completion_report
```

E-R 图与完整物理模型见 [`../database/planning-er.md`](../database/planning-er.md)、
[`../database/full-er-diagram.md`](../database/full-er-diagram.md)。

## 五、API 详细定义

36 个路径，前缀 `/api/v1/planning`，详见
[`../api/api-contract.md`](../api/api-contract.md)。主要分组：

| 分组 | 路径 |
| --- | --- |
| 需求 | `/demands`、`/demands/from-sales`、`/demands/from-replenishment`、`/demands/{id}/status` |
| MPS | `/mps`、`/mps/{id}`、`/mps/{id}/status`、`/mps/import/preview`、`/mps/import/confirm` |
| MRP | `/mrp/run`、`/mrp/runs`、`/mrp/runs/{id}/results`、`/mrp/runs/{id}/explain`、`/mrp/runs/{id}/create-production-plans`、`/mrp/runs/{id}/create-purchase-plan`、`/mrp/results`、`/mrp/results/{id}/status` |
| 生产计划 | `/production-plans`、`/production-plans/from-mrp`、`/production-plans/{id}/status` |
| 派工单 | `/dispatch-orders`、`/dispatch-orders/{id}/status` |
| 领料单 | `/requisitions`、`/requisitions/{id}/confirm`、`/requisitions/{id}/cancel` |
| 完工报告 | `/completion-reports`、`/completion-reports/{id}/confirm`、`/completion-reports/{id}/cancel` |
| 统计 | `/stats`、`/health` |

统一响应 `{code, message, data}`，`code == 0` 为成功；错误码区段 `3000~3999`。

## 六、页面详细设计

| 页面 | 路径 | 对应前端文件 |
| --- | --- | --- |
| 需求管理 | `/planning/demand` | `frontend/src/views/planning/demand/` |
| 主生产计划 | `/planning/mps` | `frontend/src/views/planning/mps/` |
| MRP 运算 | `/planning/mrp` | `frontend/src/views/planning/mrp/` |
| 生产作业计划 | `/planning/work-plan` | `frontend/src/views/planning/work-plan/` |
| 派工单 | `/planning/dispatch` | `frontend/src/views/planning/dispatch/` |
| 领料单 | `/planning/requisition` | `frontend/src/views/planning/requisition/` |
| 完工报告 | `/planning/completion` | `frontend/src/views/planning/completion/` |

页面交互约定：列表 + 查询条件 + 分页；新增 / 编辑用弹窗；状态流转用独立的确认按钮；
MRP 页面提供「发起运算 → 查看结果 → 导出/分流」的完整链路。

## 七、模块集成 / 联调方案

**只经 `contract.py` 交互，禁止跨模块 import 对方的 service / repository / models。**

| 方向 | 契约函数 | 场景 |
| --- | --- | --- |
| 入（读 system） | `get_active_bom_children`、`get_materials` | BOM 逐层展开、安全库存与提前期 |
| 入（读 sales） | `get_open_order_demand`、`get_confirmed_forecast_demand` | 需求汇总 |
| 入（读 inventory） | `get_stock_snapshot`、`get_replenishment_request` | 可用量抵扣、补库需求转生产计划 |
| 出（调 inventory） | `decrease_stock`、`increase_stock` | 领料出库、完工入库 |
| 出（调 procurement） | `create_purchase_plan_from_mrp` | MRP BUY 结果转采购计划 |
| 出（暴露给 procurement / inventory） | `create_production_plan_from_mrp_result`、`get_mrp_results`、`get_open_production_qty` | 生产计划生成、采购计划生成、在制量查询 |

**事务约定**：`contract` 函数永不 `db.commit()`，运行在调用方事务内；
service 只做业务规则不提交；由 router 在成功时统一 `db.commit()`。
因此「领料确认 = 领料单状态 + 库存流水 + 结存」在同一事务内提交。

联调验证：`backend/tests/test_end_to_end_chair_mts.py` 以课程转椅数据跑通
「导入物料/BOM → 导入期初库存 → 建 MPS → MRP 运算 → 生成生产计划与采购计划 →
到货入库 → 完工入库 → 销售发货」全链路，逐步骤断言库存流水与结存一致。