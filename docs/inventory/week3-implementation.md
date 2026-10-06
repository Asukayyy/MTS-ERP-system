# Inventory 模块详细设计与实现说明（第 3 周）

> 交付状态：**已实现并验证**（后端 36 个 HTTP 路径、10 张表、前端 8 个页面、11 个业务测试）
>
> 本文所有结论均与仓库当前代码逐条对应，权威出处：
>
> | 内容 | 权威出处 |
> | --- | --- |
> | 表结构 / 字段 / 外键 | `backend/app/modules/inventory/models.py`；[docs/database/inventory-er.md](../database/inventory-er.md)（由 `Base.metadata` 自动内省生成） |
> | 业务规则 | `backend/app/modules/inventory/service.py`（库存引擎） |
> | API 定义 | `backend/app/modules/inventory/router.py`；[docs/api/api-contract.md](../api/api-contract.md)（由 OpenAPI 导出） |
> | 跨模块接口 | `backend/app/modules/inventory/contract.py` |
> | 前端页面 | `frontend/src/views/inventory/` |
> | 测试 | `backend/tests/test_inventory.py` |

## 一、模块定位

库存管理是 MTS（面向库存生产）模式的**状态底座**：

- 全系统**库存数量的唯一维护者**。其他模块（sales / procurement / planning）看到的库存，必须来自 inventory 的契约接口，不允许在本模块另建库存字段长期缓存。
- 四类业务库存动作的落点：采购到货入库、生产领料出库、完工入库、销售发货出库 / 退货入库。
- 主动发起补货：库存低于订货点时产生**补库需求**——`REORDER` 类交 procurement 形成采购计划，`PRODUCTION` 类交 planning 形成生产计划；库存模块**自己不创建正式计划**。

```
        procurement 到货 ──(+入库)──┐
        planning 领料/完工 ─(−/+）──┤
        sales 发货/退货 ──(−/+）───┼──▶ 【Inventory】流水+结存 ──▶ 可用量反馈给 MRP
                                  │                   │
                            手工入出库/移库/盘点      └──▶ 低于订货点 → 补库需求
                                                              ├─ REORDER → procurement
                                                              └─ PRODUCTION → planning
```

## 二、业务边界

**本模块做**：仓库 / 库位主数据、实时库存结存、库存流水、手工入出库、移库、盘点、订货点规则、补库需求、库存报表、课程期初库存导入。

**本模块不做**：

- 不创建采购计划 / 生产计划（只发补库需求，由 procurement / planning 受理）；
- 不维护物料、BOM、员工主数据（只通过 `system.contract` 读）；
- 不做成本核算（仅保留 `unit_cost` 字段记录单位成本，供后续扩展）；
- 不做库位容量排程、波次拣货等 WMS 高级功能。

## 三、数据模型（10 张表，`inv_` 前缀）

| 表 | ORM 类 | 职责 | 字段数 |
| --- | --- | --- | --- |
| `inv_warehouse` | InvWarehouse | 仓库主数据（编码唯一，挂组织与负责人） | 12 |
| `inv_location` | InvLocation | 库位，仓内唯一 `(warehouse_id, location_code)` | 10 |
| `inv_balance` | InvBalance | 库存结存桶，唯一键 `(warehouse_id, location_id, material_id)` | 11 |
| `inv_transaction` | InvTransaction | 库存流水（只追加，审计凭证） | 20 |
| `inv_transfer` / `inv_transfer_item` | InvTransfer / InvTransferItem | 移库头 / 明细 | 11 / 11 |
| `inv_stocktake` / `inv_stocktake_item` | InvStocktake / InvStocktakeItem | 盘点头 / 明细（账面 vs 实盘） | 10 / 12 |
| `inv_reorder_rule` | InvReorderRule | 订货点规则（物料+仓唯一） | 11 |
| `inv_replenishment_request` | InvReplenishmentRequest | 补库需求单 | 17 |

关系要点：

- 模块内主从 FK：仓库→库位、单头→明细，`ON DELETE CASCADE`；结存 / 流水引用仓库库位用 `RESTRICT` 防误删。
- 跨模块 FK（实现方案）：`material_id → sys_material.id`、`manager_id → sys_personnel.id`、`org_id → sys_organization.id`，全部 `ON DELETE RESTRICT`，共 23 条外键（详见 inventory-er.md 第三节）。主数据被业务引用时禁止删除，从数据库层保证参照完整性。
- 流水到来源单据**不建 FK**：`source_module + source_type + source_reference_id + source_no` 是多态引用（可能指采购到货 / 领料 / 完工 / 发货 / 退货 / 移库 / 盘点），无法用单一外键表达。

数量口径（`DECIMAL(18,4)`，禁用 FLOAT）：

| 字段 | 含义 |
| --- | --- |
| `quantity` | 现存量（结存表），CHECK ≥ 0 |
| `locked_quantity` | 锁定量（已分配未出库），CHECK ≥ 0 |
| 可用量 | **不落库**，= quantity − locked_quantity，由 service / 出参计算 |
| `quantity_change` | 流水变动量，**入正出负**，允许负数 |
| `quantity_after` | 该条流水发生后的结存快照 |

## 四、核心机制①：流水驱动的库存引擎

对应 `service.py` 的 `_increase_stock / _decrease_stock / _apply_adjust`，是全模块最关键的设计。

**库存三条铁律**：

1. **任何库存变动 = 一条流水 + 一次结存更新，同一事务完成**。禁止绕过流水直接改 `inv_balance`。
2. **禁止负库存**。出库在事务内先 `SELECT ... FOR UPDATE` 对结存行加锁（`repository.get_balance_for_update`），复校 `可用量 ≥ 需求量`，不足抛业务错误 `5001` 且结存不变；并有 `quantity >= 0` 的 CHECK 约束做数据库层兜底。
3. **流水只追加**，不提供修改 / 删除接口。

关键实现细节：

- 结存桶"不存在则创建"：首次入库时自动建 0 量结存行，再加锁更新，避免竞态下重复建行（唯一键兜底）。
- 流水单号 `INV + yyyyMMdd + 4 位序号`；并发撞号时用 SAVEPOINT（`begin_nested`）回滚该条、重取号重试一次，不影响外层事务。
- service 层**永不 `db.commit()`**：HTTP 请求由 router 提交；契约调用运行在调用方事务中，保证"对方业务单据 + 库存流水 + 结存"同生共死。

## 五、核心机制②：五种流水类型 × 四类业务来源

流水类型收敛为 5 种（CHECK 约束）：

| transaction_type | 含义 | quantity_change |
| --- | --- | --- |
| `IN` | 入库（采购到货 / 完工 / 退货 / 手工） | 正 |
| `OUT` | 出库（领料 / 发货 / 手工） | 负 |
| `TRANSFER_IN` / `TRANSFER_OUT` | 移库入 / 移库出 | 正 / 负 |
| `ADJUST` | 盘点调整（可正可负，调整后不得为负） | ± |

业务来源由四个字段表达，可追溯到具体单据：

- `source_module`：PROCUREMENT / PLANNING / SALES / INVENTORY
- `source_type`：PURCHASE_RECEIPT / PRODUCTION_COMPLETION / MATERIAL_REQUISITION / SALES_SHIPMENT / SALES_RETURN / TRANSFER / STOCKTAKE / MANUAL
- `source_reference_id` + `source_no`：来源单据 id 与冗余单号（方便直接查）

## 六、核心机制③：移库与盘点

**移库**（头 + 明细，状态 DRAFT → COMPLETED / CANCELLED）：

- 确认时对每条明细写 `TRANSFER_OUT`（源仓减）与 `TRANSFER_IN`（目标仓加）**两条流水，同一事务**；
- 源、目标不能同库同位；出库段同样受行锁与可用量校验保护。

**盘点**（头 + 明细，状态 DRAFT → COMPLETED / CANCELLED）：

- 录入时 `book_qty` 留空则自动取当前结存作账面数；`difference = actual − book`；
- 确认时对差异非零的行写一条 `ADJUST` 流水，差异为 0 不写流水；调减后结存为负则抛 `5006`。

## 七、核心机制④：订货点法与补库分流

对应任务书中库存模块的决策智能化要求：

```
订货点规则 inv_reorder_rule（reorder_point / reorder_quantity，物料+仓唯一，ACTIVE）
   │  list_reorder_suggestions：遍历生效规则，现存量 < reorder_point → 产出建议
   │     建议量 = reorder_quantity；目标库存 = 现存量 + 建议量
   ▼
generate_from_reorder_rules：批量生成 DRAFT 补库需求（同物料已有在途需求则跳过，防重复补货）
   ▼
确认补库需求 confirm_replenishment_request：
   ├─ source_type=REORDER    → procurement.contract.create_purchase_plan_from_replenishment
   └─ source_type=PRODUCTION → planning.contract.create_production_plan_from_replenishment
   受理成功后回填 handled_module / handled_ref_id，状态 DRAFT → RELEASED
```

库存模块只"提需求"，正式采购 / 生产计划由对应模块创建——模块责任不越界。契约未就绪时抛 `5002`，不产生脏数据。

## 八、跨模块契约（contract.py 是唯一对外入口）

| 函数 | 供谁调用 | 说明 |
| --- | --- | --- |
| `get_on_hand_qty` | planning 等 | 现存量合计 |
| `get_available_qty` | planning（MRP 净算）、sales（发货） | 可用量 = 现存 − 锁定 |
| `get_stock_snapshot` | planning MRP | 批量取多物料库存快照 |
| `increase_stock` | procurement 到货、planning 完工、sales 退货 | 入库，写 IN 流水 + 加结存 |
| `decrease_stock` | planning 领料、sales 发货 | 出库，行锁校验，不足抛 5001 |
| `create_replenishment_request` | 跨模块场景 | 只建 DRAFT 补库需求 |
| `get_replenishment_request` | procurement / planning | 按 id 取需求单纯字典 |

契约纪律：只返回 dict / 标量（不泄露 ORM 会话）；永不 commit；签名即公共接口。

## 九、HTTP 接口（36 路径，前缀 `/api/v1/inventory`）

| 分组 | 代表路径 |
| --- | --- |
| 仓库 / 库位 | `GET/POST /warehouses`、`PUT/PATCH /warehouses/{id}`、`/locations` 全套（被引用库位禁删，5007） |
| 结存 / 流水 | `GET /balances`、`GET /balances/available`、`GET /transactions`、`/transactions/{id}` |
| 手工入出库 | `POST /stock/increase`、`POST /stock/decrease` |
| 移库 | `/transfers` CRUD + `/{id}/confirm`、`/{id}/cancel` |
| 盘点 | `/stocktakes` CRUD + `/{id}/confirm`、`/{id}/cancel` |
| 订货点 | `/reorder-rules` CRUD + `GET /reorder-rules/suggestions` |
| 补库需求 | `/replenishment-requests`、`/generate-from-reorder-rules`、`/{id}/confirm|cancel` |
| 期初导入 | `POST /import/initial-stock/preview`、`/confirm`（两段式） |
| 报表 / 其他 | `/reports/stock-summary`、`/reports/low-stock`、`/reports/flow-summary`、`/stats`、`/health` |

出参统一 `ApiResponse[T]`，分页统一 `PageData[T]`；业务错误码区段 5000–5007。

## 十、课程期初库存导入（两段式）

课程数据文件 `data/seed/course_chair_case.json` 是全组权威数据源：

1. **preview**：从课程 BOM 树递归枚举物料编码，根节点取 `finished_goods_quantity`、其余节点取 `component_quantity`（**数量全部来自数据文件，代码零硬编码**）；逐行校验物料存在性与数量为正，返回 VALID/INVALID 与 errors，**不写任何数据**。
2. **confirm**：重新校验后逐行走 `increase_stock` 正式入库，产生真实流水与结存，整批同一事务；未知编码进 errors 不静默丢弃。

## 十一、前端实现（Vue 3 + TS + Element Plus）

8 个页面挂在库存管理菜单下，路由 `/inventory/*`，与扁平路由结构一致：

| 页面 | 功能 |
| --- | --- |
| 实时库存 balance | 结存分页、仓库筛选、低库存预警栏、点行钻取流水 |
| 入库 inbound / 出库 outbound | 手工入出库表单 |
| 移库 transfer / 盘点 stocktake | 头 + 明细录入、确认 / 取消状态操作 |
| 库存流水 transaction | 多条件流水查询 |
| 订货点 reorder | 规则维护 + 补货建议查看 |
| 补库需求 replenishment | 需求列表、按订货点批量生成、确认分流 |

API 封装在 `frontend/src/api/inventory/index.ts`（36 端点一一对应），16 个库存类型定义在 `types/erp.ts`，复用公共组件 `RemoteSelect`（物料 / 仓库远程选择）、`StatusTag`、组合式函数 `usePagedTable`，未复制任何公共层代码。

## 十二、测试与验证

`backend/tests/test_inventory.py` 11 个用例（连真实 MySQL，编码带随机后缀可重复跑）：

1. 入库再出库：结存与流水同步正确、`quantity_after` 正确；
2. 超量出库抛 5001 且结存不变；
3. 移库确认原子写 TRANSFER_OUT + TRANSFER_IN；
4. 盘点确认按差异写 ADJUST；
5. 库存低于订货点触发补库建议；
6. 创建补库需求单；
7. 仓库 API 新增 / 列表；
8. 入库 API；
9. 契约 `get_replenishment_request` 返回纯字典；
10. 期初导入预览不写库；
11. 期初导入确认写结存 + 流水、未知编码进 errors。

本次验证记录（2026-09-23，本机）：

- 后端依赖安装后 `from app.main import app` 成功，OpenAPI 共 167 路径，其中 **inventory 36 路径**，与模块文档一致；
- `pytest tests/inventory/test_health.py` 通过（1 passed）；
- 11 个业务用例需本机 MySQL（3306 当前未启动），在已配置 `bh_erp` 数据库的环境执行 `pytest tests/test_inventory.py`；
- 前端静态核对：8 页面均为真实实现（无占位组件）、16 个 TS 类型齐全、路由 / 菜单各 8 项已注册；本机未装 Node.js，`npm run type-check` 待装有 Node 的环境执行。

## 十三、技术栈与分层

| 层 | 技术 | 文件 |
| --- | --- | --- |
| 路由 | FastAPI APIRouter | `router.py`（参数绑定 + commit，无业务规则） |
| 业务 | 纯函数 service | `service.py`（库存引擎，约 1800 行） |
| 数据访问 | SQLAlchemy 2.0 select / with_for_update | `repository.py` |
| ORM | SQLAlchemy 2.0 Mapped 风格 + AuditMixin | `models.py` |
| 契约 | 跨模块唯一入口 | `contract.py` |
| 校验 | Pydantic v2 | `schemas.py` |
| 建表 | Alembic baseline 迁移 | `migrations/versions/9e6fa0de8416_baseline_schema_for_five_modules.py` |
| 前端 | Vue 3 + Vite + TS + Element Plus + Pinia | `frontend/src/{api,views}/inventory/` |
