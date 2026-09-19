# 课程场景实操指南：转椅 MTS 主链路

本文按**课程验收案例（案例 2：某办公家具生产企业 —— 转椅 MTS）**，走一遍系统的完整主链路：

```
导入课程数据 → MPS 主生产计划 → MRP 物料需求运算 → 分流
   ├─ BUY 采购件 → 采购计划 → 采购订单 → 到货登记 → 入库
   └─ MAKE 自制件 → 生产作业计划 → 派工单 → 领料（出库） → 完工报告（入库）
        ↓
      销售订单 → 发货（出库） → 退货（入库）
        ↓
      订货点 / 补库需求 → 回到采购或计划
```

每一步都给出**真实的接口路径**（可在 `/docs` 中核对）与**对应的前端菜单**。

---

## 一、数据真实性声明（先看这一节）

课程原始文件提供的**只有物料名称与数量关系、以及 MPS/期初库存数字**。
系统中其余字段（编码方案、提前期、安全库存）是**系统默认值**，不是课程数据。

| 数据 | 来源 | 是否课程原始数据 |
| --- | --- | --- |
| 转椅 BOM 的**物料名称** | `data/reference/BOM例子.doc`（案例 2，内嵌 Visio 绘图对象） | ✅ 是 |
| BOM 的**数量关系**（如 1 台转椅=5 个脚轮） | 同上 | ✅ 是 |
| MPS：年计划 120000、期初库存 30000、预计期末库存 18000、1~12 月各 10000 | `data/reference/附录1：主生产计划.xls` Sheet1 | ✅ 是 |
| 期初库存：成品 30000、各级物料 3000 | 附录 1 行 7 注 | ✅ 是 |
| **物料编码**（`FG-1001` / `SF-2001..2005` / `RM-3001..3023`） | 系统自定义编号方案 | ❌ 系统默认 |
| **提前期**（成品 5 天、半成品 3 天） | 系统默认 | ❌ 系统默认 |
| **安全库存**（成品 1000、半成品 300） | 系统默认 | ❌ 系统默认 |
| **计量单位** 统一 `PCS` | 系统默认（课程未逐项标注单位） | ❌ 系统默认 |

以上逐条对应 `data/seed/course_chair_case.json` 的 `provenance` 字段，可自行核对。

> 课程数据只是**默认初始化案例**，不是硬编码。导入后它就是普通业务数据，
> 物料、BOM、数量、提前期、版本都可以在系统里自由修改。

---

## 二、案例数据一览

### 2.1 BOM 结构（3 层，29 个节点）

| 层级 | 编码 | 名称 | 类型 | 供应方式 | 相对上层数量 |
| --- | --- | --- | --- | --- | --- |
| 0 | `FG-1001` | 办公转椅 | FINISHED | MAKE | 1（成品） |
| 1 | `SF-2001` | 塑料件 | SEMI | MAKE | 1 |
| 2 | `RM-3001` | 脚轮 | PURCHASED | BUY | **5** |
| 2 | `RM-3002` | 三节杯 | PURCHASED | BUY | 1 |
| 2 | `RM-3003` | 五星脚 | PURCHASED | BUY | 1 |
| 2 | `RM-3004` | 扶手 | PURCHASED | BUY | 1 |
| 2 | `RM-3005` | 背猪腰 | PURCHASED | BUY | 1 |
| 1 | `SF-2002` | 五金件 | SEMI | MAKE | 1 |
| 2 | `RM-3006` | 猪腰铁片 | PURCHASED | BUY | 1 |
| 2 | `RM-3007` | 底盘 | PURCHASED | BUY | 1 |
| 1 | `SF-2003` | 标准件 | SEMI | MAKE | 1 |
| 2 | `RM-3008` | 底盘螺丝 | PURCHASED | BUY | **4** |
| 2 | `RM-3009` | 背螺丝 | PURCHASED | BUY | **2** |
| 1 | `SF-2004` | 其他件 | SEMI | MAKE | 1 |
| 2 | `RM-3010` | 座木板 | PURCHASED | BUY | 1 |
| 2 | `RM-3011` | 背木板 | PURCHASED | BUY | 1 |
| 2 | `RM-3012` | 座海棉 | PURCHASED | BUY | 1 |
| 2 | `RM-3013` | 背海绵 | PURCHASED | BUY | 1 |
| 2 | `RM-3014` | 背后海绵 | PURCHASED | BUY | 1 |
| 2 | `RM-3015` | 背后PVC | PURCHASED | BUY | 1 |
| 2 | `RM-3016` | 座下无纺布 | PURCHASED | BUY | 1 |
| 2 | `RM-3017` | 布 | PURCHASED | BUY | 1 |
| 2 | `RM-3018` | 胶边 | PURCHASED | BUY | 1 |
| 1 | `SF-2005` | 包装件 | SEMI | MAKE | 1 |
| 2 | `RM-3019` | 外箱 | PURCHASED | BUY | 1 |
| 2 | `RM-3020` | 护箱 | PURCHASED | BUY | 1 |
| 2 | `RM-3021` | 纸板 | PURCHASED | BUY | 1 |
| 2 | `RM-3022` | 背胶袋 | PURCHASED | BUY | 1 |
| 2 | `RM-3023` | 座胶袋 | PURCHASED | BUY | 1 |

统计（`course_chair_case.json` 的 `counts`）：**3 层 / 5 个半成品 / 23 个采购件 / 共 29 个节点**。

### 2.2 每台转椅的直接用量（纯算术，可按上表核对）

| 物料 | 数量 | 说明 |
| --- | --- | --- |
| 塑料件 `SF-2001` | 1 | → 消耗脚轮 5、三节杯 1、五星脚 1、扶手 1、背猪腰 1 |
| 五金件 `SF-2002` | 1 | → 猪腰铁片 1、底盘 1 |
| 标准件 `SF-2003` | 1 | → 底盘螺丝 4、背螺丝 2 |
| 其他件 `SF-2004` | 1 | 其下 9 个采购件各 1 |
| 包装件 `SF-2005` | 1 | 其下 5 个采购件各 1 |

> 单台转椅对采购件的**总用量**由系统在 MRP 展开时逐层累乘得出（会叠加 `scrap_rate`），
> 本文不预先给出，请在 MRP 结果页查看真实计算结果。

### 2.3 MPS（来自附录 1）

| 项 | 值 |
| --- | --- |
| 年计划产量 | 120000 |
| 期初库存（成品） | 30000 |
| 预计期末库存 | 18000 |
| 1~12 月每月计划产量 | 10000 |
| 各月预计库存 | 29000 → 28000 → … → 18000（每月递减 1000） |

### 2.4 期初库存

| 项 | 值 |
| --- | --- |
| 成品 | 30000 |
| 各级物料（每个半成品/采购件） | 3000 |

---

## 三、前置准备

1. 后端与前端已启动（见 [`../development/deployment-and-startup.md`](../development/deployment-and-startup.md)）。
2. 已执行 `alembic upgrade head` 建表。
3. 导入课程数据时，后端进程能读到仓库的 `data/seed/course_chair_case.json`
   —— 相关模块用 `Path(__file__).resolve().parents[4] / "data" / "seed" / ...` 定位，
   因此**必须按仓库目录结构运行后端**（不要单独把 `backend/` 挪走）。

---

## 四、第 1 步：导入课程数据（两段式，先预览再确认）

课程数据导入统一遵循 **preview（只校验、不落库） → confirm（真正写库）** 的模式。
`source` 参数固定传 `course_chair_case`（服务端内置数据源标识）。

| 顺序 | 接口 | 前端菜单 | 说明 |
| --- | --- | --- | --- |
| 1 | `POST /api/v1/system/import/materials/preview` | 基础信息 → 物料管理 | 预览 29 个物料，请求体 `{"source": "course_chair_case"}` |
| 2 | `POST /api/v1/system/import/materials/confirm` | 基础信息 → 物料管理 | 确认导入物料（编码 `FG/SF/RM`） |
| 3 | `POST /api/v1/system/import/bom/preview` | 基础信息 → BOM管理 | 预览多层 BOM 结构 |
| 4 | `POST /api/v1/system/import/bom/confirm` | 基础信息 → BOM管理 | 确认导入 BOM（版本 `V1.0`） |
| 5 | `POST /api/v1/planning/mps/import/preview` | 计划管理 → 主生产计划 MPS | 预览附录 1 的 12 个月计划 |
| 6 | `POST /api/v1/planning/mps/import/confirm` | 计划管理 → 主生产计划 MPS | 确认导入 MPS |
| 7 | `POST /api/v1/inventory/import/initial-stock/preview` | 库存管理 → 入库 | 预览期初库存（成品 30000、物料各 3000） |
| 8 | `POST /api/v1/inventory/import/initial-stock/confirm` | 库存管理 → 入库 | 确认导入 → **写入真实库存流水与余额** |

要点：

- 传入未在服务端注册的 `source` 会返回 system 模块错误码 **`1011`**（`CODE_UNSUPPORTED_SOURCE`）。
- 预览不落库；只有 confirm 才真正写数据。
- 期初库存导入会走正规的库存流程（写 `inv_transaction` + `inv_balance`），
  因此导入后即可在「实时库存」看到余额。

**验证**：

- `GET /api/v1/system/materials` → 应能查到 `FG-1001`、`SF-2001..2005`、`RM-3001..3023`，共 29 条。
- `GET /api/v1/system/boms/tree?material_id=<FG-1001的id>&max_level=3` → 应返回 3 层结构。
- `GET /api/v1/inventory/balances` → 成品与各级物料均应有期初余额。

---

## 五、第 2 步：MPS 主生产计划

**前端菜单**：计划管理 → 主生产计划 MPS。

1. 导入（或手工新增）后，MPS 处于 `DRAFT`（草稿）。
2. 通过 `PATCH /api/v1/planning/mps/{mps_id}/status` 把状态流转为 `CONFIRMED`。
3. `CONFIRMED` 之后 MPS **只读**：任何修改/删除都会返回 planning 模块错误码 **`3002`**（`CODE_MPS_LOCKED`）。
4. 继续流转到 `RELEASED`（已下达），MRP 就可以以它为输入。

状态流转规则（见 [`../database/data-dictionary.md`](../database/data-dictionary.md) 第八节）：

```
DRAFT → CONFIRMED → RELEASED → IN_PROGRESS → COMPLETED
             └──────────┴────────────┴──→ CANCELLED
```

---

## 六、第 3 步：MRP 物料需求运算

**前端菜单**：计划管理 → 物料需求计划 MRP。

```
POST /api/v1/planning/mrp/run
```

请求体 `MrpRunCreate` 至少提供 `mps_id` / `demand_ids` / `include_sales_demand` 之一，
否则返回 `3000`（`CODE_PARAM_INVALID`）。

系统做的事：

1. 从 MPS（或需求、销售订单）取**毛需求**。
2. 逐层展开 BOM（带 `lead_time_offset` 提前期偏置），检测循环引用（有环返回 **`3001`** `CODE_BOM_CYCLE`）。
3. 计算净需求：

```
净需求 = max( 毛需求 + 安全库存 − 可用库存 , 0 )
```

4. 子件毛需求 = 父件净需求 × 单位用量 × (1 + 报废率)
5. 子件需求日期 = 父件需求日期 − 提前期偏置；下达日期 = 需求日期 − 采购/生产提前期
6. 按物料的 `supply_type` 分流为 **MAKE（自制）** 与 **BUY（采购）**。

**查看结果**：

| 接口 | 用途 |
| --- | --- |
| `GET /api/v1/planning/mrp/runs` | 批次列表 |
| `GET /api/v1/planning/mrp/runs/{run_id}` | 批次详情（含结果） |
| `GET /api/v1/planning/mrp/runs/{run_id}/results` | 批次结果（分页，可按 `supply_type` 过滤） |
| `GET /api/v1/planning/mrp/runs/{run_id}/explain` | **计算明细（可解释性）**：逐个物料的毛需求/库存/净需求来源 |
| `GET /api/v1/planning/mrp/results` | 跨批次查询 MRP 结果 |

> 讲解答辩时可直接用 `explain` 接口举证：「这个净需求是怎么算出来的」。

**本案例的预期分流**：

- MAKE：`FG-1001`、`SF-2001`~`SF-2005`（共 6 个自制件）
- BUY：`RM-3001`~`RM-3023`（共 23 个采购件）

---

## 七、第 4 步：由 MRP 分流下达

### 7.1 BUY 侧 → 采购计划

```
POST /api/v1/planning/mrp/runs/{run_id}/create-purchase-plan
```

- 该接口会跨模块调用 `procurement.contract.create_purchase_plan_from_mrp`，
  在**采购模块**生成采购计划（`pur_purchase_plan` + `pur_purchase_plan_item`）。
- 批次中没有可下达的采购件需求时返回 `3000`。
- 契约未就绪时返回 `3005`（`CODE_CONTRACT_NOT_READY`）。

### 7.2 MAKE 侧 → 生产作业计划

```
POST /api/v1/planning/mrp/runs/{run_id}/create-production-plans
```

或按 MRP 结果逐条下达：

```
POST /api/v1/planning/production-plans/from-mrp     body: ProductionPlanFromMrpRequest
```

- 净需求为 0 的 MRP 结果不能下达（返回 `3000`）。
- 同一条 MRP 结果重复下达会返回 `3004`（`CODE_DUPLICATE`）。
- 物料不是自制件时返回 `3000`。

---

## 八、第 5 步：采购链路（BUY）

**前端菜单**：采购管理 → 采购计划 / 采购订单 / 到货管理。

| 步骤 | 接口 | 说明 |
| --- | --- | --- |
| 1 | `GET /api/v1/procurement/purchase-plans` | 查看 MRP 下达生成的采购计划（`DRAFT`） |
| 2 | `PATCH /api/v1/procurement/purchase-plans/{plan_id}/status` | `DRAFT → CONFIRMED → RELEASED → COMPLETED` |
| 3 | `POST /api/v1/procurement/orders/from-plan` | **由采购计划生成采购订单**（`OrderFromPlanRequest`） |
| 4 | `PATCH /api/v1/procurement/orders/{order_id}/status` | 采购订单流转到 `RELEASED` / `IN_PROGRESS` |
| 5 | `POST /api/v1/procurement/receipts` | 登记到货（`ReceiptCreate`），可分批 |
| 6 | `POST /api/v1/procurement/receipts/{receipt_id}/confirm` | **确认到货 → 调用库存 `increase_stock`，`source_type=PURCHASE_RECEIPT`** |

要点：

- 到货数量超过未到货数量会返回 **`4004`**（`CODE_RECEIPT_QTY_EXCEED`）。
- 已确认/已下达/已完结的单据不可修改，返回 **`4003`**（`CODE_IMMUTABLE`）。
- 确认到货后，去「库存管理 → 实时库存 / 库存流水」应能看到入库记录与余额增加。

---

## 九、第 6 步：生产链路（MAKE）

**前端菜单**：计划管理 → 生产作业计划 / 派工单 / 领料单 / 完工报告。

| 步骤 | 接口 | 说明 |
| --- | --- | --- |
| 1 | `PATCH /api/v1/planning/production-plans/{plan_id}/status` | 生产作业计划 `DRAFT → CONFIRMED` |
| 2 | `POST /api/v1/planning/dispatch-orders` | 新增派工单（`DispatchOrderCreate`），指派作业人员 |
| 3 | `POST /api/v1/planning/requisitions` | 新增领料单（`RequisitionCreate`，头 + 明细） |
| 4 | `POST /api/v1/planning/requisitions/{req_id}/confirm` | **确认领料 → 调用库存 `decrease_stock`，`source_type=MATERIAL_REQUISITION`；库存不足返回 `5001`** |
| 5 | `POST /api/v1/planning/completion-reports` | 新增完工报告（`CompletionReportCreate`：完工数、合格数、报废数） |
| 6 | `POST /api/v1/planning/completion-reports/{report_id}/confirm` | **确认完工 → 调用库存 `increase_stock`，`source_type=PRODUCTION_COMPLETION`** |

校验规则（真实存在于 service 层）：

- 合格数量不能大于完工数量；合格数量为 0 时无需入库（返回 `3000`）。
- 领料单未指定领料仓库、或没有明细时不能确认（返回 `3000`）。
- 领料出库时库存不足，由库存模块返回 **`5001`**（`CODE_STOCK_INSUFFICIENT`）——**系统不允许负库存**。

> 建议顺序：先做 5 个半成品（`SF-2001`~`SF-2005`）的领料 + 完工入库，
> 再做成品 `FG-1001` 的领料（此时半成品已有库存）+ 完工入库。
> 这样才能体现 BOM 的逐层关系。

---

## 十、第 7 步：销售链路（发货与退货）

**前端菜单**：销售管理 → 客户 / 销售订单 / 发货管理 / 退货管理。

| 步骤 | 接口 | 说明 |
| --- | --- | --- |
| 1 | `POST /api/v1/sales/customers` | 建客户（编码重复返回 `2001`） |
| 2 | `POST /api/v1/sales/orders` | 建销售订单（成品 `FG-1001`），状态 `DRAFT` |
| 3 | `PATCH /api/v1/sales/orders/{order_id}/status` | `DRAFT → CONFIRMED → IN_PROGRESS → COMPLETED` |
| 4 | `POST /api/v1/sales/shipments` | 新增发货单（可分批发货） |
| 5 | `POST /api/v1/sales/shipments/{shipment_id}/confirm` | **确认发货 → 调用库存 `decrease_stock`，`source_type=SALES_SHIPMENT`** |
| 6 | `POST /api/v1/sales/returns` | 新增退货单（`ReturnCreate`） |
| 7 | `POST /api/v1/sales/returns/{return_id}/confirm` | **确认退货 → 调用库存 `increase_stock`，`source_type=SALES_RETURN`** |

要点：

- 销售订单状态机中 `COMPLETED` 后**不能再取消**（只有 `DRAFT`/`CONFIRMED` 可取消）。
  已完结/已取消单据修改返回 **`2002`**（`CODE_IMMUTABLE`）。
- 发货数量超过未发数量返回 **`2003`**（`CODE_SHIP_QTY_EXCEED`）。
- 退货单与原订单客户不一致返回 **`2004`**（`CODE_RETURN_MISMATCH`）。
- 退货明细带 `quality_status`，取值仅 `QUALIFIED` / `DEFECTIVE` / `SCRAP`。
- 确认退货后，来料回库到「库存管理 → 实时库存」。

---

## 十一、第 8 步：库存补货（订货点 → 补库需求 → 采购/计划）

**前端菜单**：库存管理 → 订货点 / 补库需求。

| 步骤 | 接口 | 说明 |
| --- | --- | --- |
| 1 | `POST /api/v1/inventory/reorder-rules` | 为物料设订货点规则（`ReorderRuleCreate`：再订货点、安全库存、批量） |
| 2 | `GET /api/v1/inventory/reorder-rules/suggestions` | 查看**补库建议**（哪些物料低于订货点） |
| 3 | `POST /api/v1/inventory/replenishment-requests/generate-from-reorder-rules` | **按订货点批量生成补库需求** |
| 4 | `POST /api/v1/inventory/replenishment-requests/{request_id}/confirm` | 确认补库需求，按 `source_type` 分流 |
| 5 | `GET /api/v1/inventory/reports/low-stock` | 低库存/缺料报表 |

确认补库需求时的分流（真实行为）：

| `source_type` | 去向 | 契约函数 |
| --- | --- | --- |
| `REORDER` | 采购模块 → 生成采购计划 | `procurement.contract.create_purchase_plan_from_replenishment` |
| `PRODUCTION` | 计划模块 → 生成生产作业计划 | `planning.contract.create_production_plan_from_replenishment` |

契约未就绪时返回 **`5002`**（`CODE_CONTRACT_NOT_READY`）。

其他库存动作（同样属于主链路之外但常演示）：

| 动作 | 接口 | 说明 |
| --- | --- | --- |
| 手工入库 | `POST /api/v1/inventory/stock/increase` | `source_type=MANUAL` |
| 手工出库 | `POST /api/v1/inventory/stock/decrease` | 库存不足返回 `5001` |
| 移库 | `POST /api/v1/inventory/transfers` → `/{id}/confirm` | `TRANSFER_OUT` + `TRANSFER_IN` 两条流水 |
| 盘点 | `POST /api/v1/inventory/stocktakes` → `/{id}/confirm` | 差异写 `ADJUST` 流水；调整后为负返回 `5006` |

---

## 十二、库存追溯（答辩必备）

所有库存变动**只通过 `inv_transaction` + `inv_balance` 在同一事务中完成**，
且流水上记录了来源，因此任何一笔数量变化都能倒查回业务单据：

| 流水字段 | 作用 |
| --- | --- |
| `transaction_type` | `IN` / `OUT` / `TRANSFER_IN` / `TRANSFER_OUT` / `ADJUST` |
| `source_type` | `PURCHASE_RECEIPT` / `PRODUCTION_COMPLETION` / `MATERIAL_REQUISITION` / `SALES_SHIPMENT` / `SALES_RETURN` / `TRANSFER` / `STOCKTAKE` / `MANUAL` |
| `source_module` | 来源模块 |
| `source_reference_id` / `source_no` | 来源单据 ID 与单号 |

演示话术：在「库存管理 → 库存流水」里挑一条入库记录，按 `source_no`
就能查到它来自哪张到货单 / 完工报告，再往上就能追到 MRP 与 MPS。

---

## 十三、全链路验收清单

| # | 检查点 | 期望 |
| --- | --- | --- |
| 1 | 课程数据导入 | 29 个物料、1 套 3 层 BOM、12 个月 MPS、期初库存全部落库 |
| 2 | MPS 确认后可下达 | `RELEASED` 状态下可被 MRP 引用；`CONFIRMED` 后修改报 `3002` |
| 3 | MRP 运算 | 生成批次 + 结果；`explain` 能解释净需求来源 |
| 4 | MAKE/BUY 分流 | 6 个自制件 → 生产作业计划；23 个采购件 → 采购计划 |
| 5 | 采购到货入库 | 到货确认后库存增加，流水 `source_type=PURCHASE_RECEIPT` |
| 6 | 领料出库 | 领料确认后库存减少；库存不足报 `5001` |
| 7 | 完工入库 | 合格品入库，流水 `source_type=PRODUCTION_COMPLETION` |
| 8 | 销售发货出库 | 流水 `source_type=SALES_SHIPMENT`，库存同步减少 |
| 9 | 销售退货入库 | 流水 `source_type=SALES_RETURN`，库存同步增加 |
| 10 | 补库闭环 | 订货点 → 补库建议 → 补库需求 → 生成采购计划或生产计划 |
| 11 | 库存不为负 | 任何出库都不会把余额做成负数 |
| 12 | 端到端测试 | `pytest tests/test_end_to_end_chair_mts.py` 通过 |

---

## 十四、常见问题

**Q：导入报 `1011`？**
A：`source` 传错了。当前只支持 `course_chair_case`。

**Q：MRP 跑出来净需求全是 0？**
A：期初库存是按附录 1 导入的（成品 30000、各级物料各 3000），若计划量小于
「可用库存 − 安全库存」，净需求按公式就被压到 0。这是公式的正确结果，不是 bug。
可以调小期初库存或加大 MPS 计划量再跑一次。

**Q：确认到货/领料/发货时报 `5001` 或 `4004`？**
A：`5001` = 库存不足（不允许负库存）；`4004` = 到货数量超过未到货数量。
前者先补库存，后者核对采购订单的剩余未到货量。

**Q：单据改不动，报 `4003` / `2002` / `3002`？**
A：单据已进入不可修改状态（已确认/已下达/已完结）。这是状态机设计，
不是权限问题 —— 请追加新单据或先走取消。

**Q：没有登录也能调接口？**
A：是的。当前**未实现鉴权**，`POST /api/v1/system/auth/login` 是简化版登录，
所有接口不校验 `Authorization`。详见
[`../api/api-contract.md`](../api/api-contract.md) 第四节。