# BH-ERP 最终验收报告

> 依据 `docs/requirements/BH-ERP-完整开发规格.md` 第四十七节要求的 A–H 结构逐项作答。
> 本报告中的**每一个数字都在本机真实环境实测得出**，核对命令一并给出，可原样复现。
>
> 环境：Windows / Python 3.12（`C:\ProgramData\anaconda3\python.exe`）/ MySQL 8.0.22 `127.0.0.1:3306`，
> 库名 `bh_erp`，Node.js + Vite 前端。
> 实测时间：2026-09-19。

---

## A. Repository（仓库与提交）

| 项 | 值 |
| --- | --- |
| 工作分支 | `feature/planning` |
| 远端 | `origin` = `https://github.com/Asukayyy/MTS-ERP-system.git` |
| 本次交付提交数 | **9 个**（1 个建库 + 5 个模块 + 1 个前端 + 1 个集成测试 + 1 个文档） |
| 强推 / 历史重写 | **无**。全程使用普通 `git push`，未使用 `--force` / `--force-with-lease`，未改写任何已推送提交 |
| 推送状态 | **PASS** —— 本报告所在提交已推送到 `origin/feature/planning` |

本次交付提交清单（按时间顺序，`git log --oneline`）：

| # | Commit | 内容 |
| --- | --- | --- |
| 1 | `299ed1e` `chore(db)` | 新增迁移：BOM 提前期偏置、退货质量状态、补库目标量 |
| 2 | `4ed0471` `feat(system)` | 基础信息：物料 / BOM / 工艺路线 / 组织 / 人员 / 字典 / RBAC / 操作日志 / 课程导入 |
| 3 | `4beea43` `feat(inventory)` | 仓库 / 库位 / 结存 / 流水 / 移库 / 盘点 / 订货点 / 补库需求 |
| 4 | `a51920c` `feat(sales)` | 客户 / 销售预测 / 销售订单 / 发货 / 退货 |
| 5 | `3347c53` `feat(planning)` | 需求 / MPS / 多层 MRP 引擎 / 生产作业计划 / 派工 / 领料 / 完工 |
| 6 | `bd0cf29` `feat(procurement)` | 供应商 / 供应商-物料 / 采购计划 / 采购订单 / 到货 / 供应商评价 |
| 7 | `f80d556` `test(integration)` | 转椅 MTS 端到端验收用例 |
| 8 | `44f37e8` `feat(web)` | 38 个真实业务页面 + 路由/菜单/API 层 |
| 9 | （本提交） `docs` | 全套文档校准 + 本验收报告 |

基线提交（本次交付之前已存在）：`62b708b` 五模块基线建表、`88e5588` 课程案例种子数据。

---

## B. Architecture（架构）

### B.1 前端

- 技术栈：Vue 3 + TypeScript + Vite + Pinia + Vue Router + Axios + Element Plus。
- 路由声明 **42** 条（`path:` 字面量）：登录 1、布局根 1、404 1、工作台 1、**模块业务页面 38**。
- 页面与路由一一对应，**不存在 mock 页面、占位组件或随机数据**；
  `views/<module>/<page>/index.vue` 直接调用 `src/api/<module>/index.ts`。
- 页面分布：system 13、sales 5、planning 7、procurement 8、inventory 8（含工作台则 38+1）。

核对命令：

```bash
cd frontend
npx vue-tsc --noEmit          # 退出码 0
npm run build                 # 构建成功
```

### B.2 后端

- 技术栈：FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic + PyMySQL。
- 入口 `backend/app/main.py` 的 `create_app()` 把五个模块路由器挂到 `/api/v1/<module>`。
- 模块内分层固定：`router.py`（定义路径 / 注入依赖 / **提交事务**）
  → `service.py`（业务规则、状态机、跨模块编排，**不 commit**）
  → `repository.py`（只写 SQL）
  → `models.py`（ORM），另有 `schemas.py`（出入参）与 `contract.py`（跨模块契约）。
- 统一响应信封 `{code, message, data}`（`code = 0` 成功），分页固定
  `{page, page_size, total, items}`（默认 `page_size = 20`，上限 200）。
- 错误码按模块分段：system `1000~1999`、sales `2000~2999`、planning `3000~3999`、
  procurement `4000~4999`、inventory `5000~5999`。

实测接口规模（`GET /openapi.json`）：

| 模块 | 前缀 | 路径数 |
| --- | --- | --- |
| system | `/api/v1/system` | 43 |
| sales | `/api/v1/sales` | 24 |
| planning | `/api/v1/planning` | 36 |
| procurement | `/api/v1/procurement` | 27 |
| inventory | `/api/v1/inventory` | 36 |
| 应用级 | `/health` | 1 |
| **合计** | | **167 路径 / 223 操作** |

### B.3 数据库

MySQL 8.x，`utf8mb4` / `utf8mb4_unicode_ci`，五个模块**共用一个库**，代码按模块隔离。

### B.4 模块组织与跨模块规则

- 每张表有且只有一个 **Owner 模块**，逐表归属见
  [`module-ownership.md`](architecture/module-ownership.md)。
- 五模块**唯一**跨模块入口是各自的 `contract.py`：
  `system` / `sales` / `planning` / `procurement` / `inventory` 均已落地。
- 强制约定（已全量检查，无违规）：
  1. 任何模块**不得** import 其他模块的 `service.py` / `repository.py` / `models.py`；
  2. `contract.py` 只返回 `dict` / 标量，**不返回 ORM 对象**；
  3. `contract.py` **永不 `db.commit()`**，运行在调用方事务内，保证跨模块写入原子。

核对命令：

```bash
cd backend
grep -rn "from app.modules" app/modules --include=*.py | grep -v "\.contract import"
# 结果只应出现本模块内部引用
```

### B.5 前后端接口一致性（实测）

把 API 层（`frontend/src/api/**/*.ts`）里出现的路径字面量规范化后与 OpenAPI 注册路径逐条比对：

| 指标 | 数值 |
| --- | --- |
| 前端 API 模板数 | **156** |
| 后端模块路径数 | **166** |
| 前端调用了但后端不存在的路径 | **0**（零不匹配） |
| 后端存在但前端未使用的路径 | **10**（均为 by-id 详情 / 报表类接口，页面暂未入口，见 H 节） |

---

## C. Database（数据库）

| 项 | 值 | 核对方式 |
| --- | --- | --- |
| 业务表 | **52 张** | `information_schema.tables` |
| 　system `sys_` | 15 | 同上 |
| 　sales `sal_` | 8 | 同上 |
| 　planning `pln_` | 10 | 同上 |
| 　procurement `pur_` | 9 | 同上 |
| 　inventory `inv_` | 10 | 同上 |
| 字段总数 | **640**（52 张业务表合计；含 `alembic_version` 则为 641） | `information_schema.columns` |
| 外键约束 | **95** | `information_schema.table_constraints` |
| CHECK 约束 | **93** | 同上 |
| UNIQUE 约束 | **42** | 同上 |
| Alembic 迁移 | **2 个**，HEAD = `f5e52ee720d6` | `alembic history` |
| 迁移漂移 | **无**（`alembic check` → `No new upgrade operations detected`） | `alembic check` |

迁移链：

```
<base> → 9e6fa0de8416 (五模块基线建表)
       → f5e52ee720d6 (head: BOM 提前期偏置 / 退货质量状态 / 补库目标量)
```

- **完整 ER 图**：[`docs/database/full-er-diagram.md`](database/full-er-diagram.md)
  （52 实体 / 95 关系 + 模块依赖图），另有五个模块各自的 ER 图
  `system-er.md` / `sales-er.md` / `planning-er.md` / `procurement-er.md` / `inventory-er.md`。
- **物理模型**：[`docs/database/physical-data-model.md`](database/physical-data-model.md)
  （逐表逐字段：类型 / 可空 / 默认值 / 键 / 约束 / 索引）。
- 命名与类型规范：[`docs/database/data-dictionary.md`](database/data-dictionary.md)。
- 表前缀严格按模块划分，**跨模块一律用 ID 引用、不建外键约束**（95 条外键全部落在模块内部）。

核对命令：

```bash
cd backend
alembic history
alembic check

python -c "import app.modules.system.models, app.modules.sales.models, app.modules.planning.models, \
app.modules.procurement.models, app.modules.inventory.models; from app.core.database import Base; \
print(len(Base.metadata.tables))"
# 52
```

---

## D. Five Modules（五模块已实现功能）

### D.1 system（基础信息，`/api/v1/system`，43 路径 / 15 表）

| 功能 | 说明 |
| --- | --- |
| 物料主数据 | 增删改查、按编码唯一（重复报 `1001`）、状态启停、物料类型与供应类型（MAKE/BUY） |
| BOM | 多层 BOM 头 + 明细（用量 / 报废率 / **提前期偏置**）、版本管理、启用版本切换、**BOM 树查询**、**循环引用检测**（报 `1003`） |
| 工艺路线 | 路线头 + 工序明细、按物料版本唯一 |
| 组织架构 | 树形组织 + 扁平列表、层级循环保护 |
| 人员 | 工号唯一（重复报 `1004`）、挂靠组织、状态管理 |
| 用户 / 角色 / 权限 | 用户-角色-权限三级 RBAC 数据结构与分配接口、简化登录 |
| 数据字典 | 字典 + 字典项两级维护 |
| 操作日志 | 全系统状态变更落 `sys_operation_log`，提供分页查询 |
| 课程数据导入 | 物料导入、BOM 导入的 **preview / confirm** 两步式（预览不落库） |

### D.2 sales（销售，`/api/v1/sales`，24 路径 / 8 表）

| 功能 | 说明 |
| --- | --- |
| 客户 | 增删改查、客户编码唯一、状态启停 |
| 销售预测 | 预测单 + 明细、状态流转 |
| 销售订单 | 订单 + 明细、自动算金额、确认（校验必须是成品）、状态机、已发货数量回写 |
| 发货 | 发货单 + 明细、**确认即真实出库**（经 inventory 契约写流水）、超量发货拒绝（`2003`） |
| 退货 | 退货单 + 明细（含**质量状态**）、确认即**真实回增库存**、状态机 |
| 对计划的支撑 | 契约 `list_open_order_demand` 把未交付订单需求交给 planning 归集 |
| 报表 | 订单状态 / 发货 / 退货 / 销售量四张统计 |

### D.3 planning（计划与生产，`/api/v1/planning`，36 路径 / 10 表）

| 功能 | 说明 |
| --- | --- |
| 统一需求 | 需求池（`SALES` / `STOCKFILL` / `MPS` 三类来源），支持从销售订单、库存补库需求自动生成 |
| MPS 主生产计划 | MPS 头 + 行（物料 / 期间 / 计划量 / 起止日期）、状态机、已确认后只读（`3002`）、Excel 式导入 preview/confirm |
| **MRP 多层展开** | 真实多层 BOM 展开引擎（详见下） |
| MRP 结果管理 | 结果行查询、结果状态流转、"为什么这么算"解释接口 |
| 结果转下游 | `create-purchase-plan`（→ 采购）、`create-production-plans`（→ 生产） |
| 生产作业计划 | 由 MRP 结果或补库需求生成、状态机 |
| 派工单 | 作业计划 + 人员/组织 + 数量、状态机 |
| 领料单 | 确认即**真实出库**（经 inventory 契约，写 `MATERIAL_REQUISITION` 流水），缺料整单回滚（`5001`） |
| 完工报告 | 确认即**真实入库**（写 `PRODUCTION_COMPLETION` 流水），并回写作业计划已完工数量 |

**MRP 计算规则**（`service.py`，全部按规格实现）：

```
第 0 层：MPS 行（planned_qty > 0）+ 指定需求（CONFIRMED / RELEASED）归集为毛需求
逐层循环：
    净需求     = max( 毛需求 + 安全库存 − 可用库存 , 0 )
    下达日期   = 需求日期 − 提前期天数
    子件毛需求 = 父件净需求 × 单位用量 × (1 + 报废率)
    子件需求日期 = 父件需求日期 − 提前期偏置
    按 supply_type 分流：MAKE（自制）/ BUY（采购）
```

- 可用库存按**批次内一次性抵扣**（`remaining_available` 递减），同一物料被多个父件引用不会重复抵扣。
- 每次运行生成独立 `pln_mrp_run` 批次（`IN_PROGRESS → COMPLETED`），**历史结果不被覆盖**。
- 展开过程中检测 BOM 环，命中抛 `3001`。

### D.4 procurement（采购，`/api/v1/procurement`，27 路径 / 9 表）

| 功能 | 说明 |
| --- | --- |
| 供应商 | 增删改查、编码唯一、状态启停 |
| 供应商-物料关系 | 供货关系 + 供货价 / 交期，同供应商同物料唯一 |
| 采购计划 | 来源二选一：**MRP 结果**（BUY 行）或**库存补库需求**，计划行含建议数量与需求日期 |
| 采购订单 | 由采购计划生成、订单 + 明细、状态机、**回写计划已订购数量** |
| 到货 | 到货单 + 明细、确认即**真实入库**（写 `PURCHASE_RECEIPT` 流水）、超量到货拒绝 |
| 供应商评价 | 多维度评分 + 总分计算、按供应商查询 |
| 报表 | 采购计划 / 订单 / 到货 / 待办 / 供应商评价五张统计 |

### D.5 inventory（库存，`/api/v1/inventory`，36 路径 / 10 表）

| 功能 | 说明 |
| --- | --- |
| 仓库 / 库位 | 两级结构、状态启停 |
| 库存余额 | 按「物料 × 仓库 × 库位」维护结存，支持余额查询与可用量查询 |
| 库存流水 | 全部变动逐笔落 `inv_transaction`，可按物料 / 仓库 / 来源类型 / 来源单据追溯 |
| 入库 / 出库 | 主动出入库接口（`stock/increase`、`stock/decrease`） |
| 移库 | 库位间调拨，确认时**同事务**写转出 + 转入两条流水 |
| 盘点 | 盘点单 + 明细，确认写 `ADJUST` 调整流水 |
| 订货点 | 订货点规则（订货点 / 订货量 / 提前期）、低于订货点的**补库建议** |
| 补库需求 | 由订货点规则批量生成，支持 `REORDER` / `PRODUCTION` 两种补库方式，确认后交给采购或计划 |
| 期初库存导入 | preview（不落库）/ confirm（建余额 + 写流水）两步式 |
| 报表 | 库存汇总 / 低库存 / 流水汇总三张统计 |

**库存铁律（已实现并测试）**：任何库存变动**必须同时**写 `inv_transaction` 流水 + 更新
`inv_balance` 结存，两者在同一事务内完成；出库不足直接抛 `5001`，**库存不允许为负**。

---

## E. Course Data（课程数据使用情况）

系统使用课程原始文件作为权威数据源，**未编造任何课程数据**：

| 项 | 位置 | 状态 |
| --- | --- | --- |
| 转椅 BOM 原始文件 | `data/reference/BOM例子.doc` | **存在**（案例 2：某办公家具生产企业 → 转椅 BOM） |
| 主生产计划原始文件 | `data/reference/附录1：主生产计划.xls` | **存在** |
| 结构化后的课程种子 | `data/seed/course_chair_case.json` | **存在**，含 `provenance` 逐条来源说明 |
| BOM 提取脚本 | `tools/` | 存在 |

种子文件中的课程原始数据（100% 来自课程文件）：

```
counts:  { levels: 3, semi_components: 5, purchased_parts: 23, total_nodes: 29 }
mps:     { annual_plan_quantity: 120000, monthly_plan_quantity: 10000, month_count: 12,
           product_initial_stock: 30000, product_expected_ending_stock: 18000 }
initial_inventory: { finished_goods_quantity: 30000, component_quantity: 3000 }
```

非课程数据（种子文件 `provenance.system_defaults_note` 已明确标注为**系统默认值**）：

| 项 | 说明 |
| --- | --- |
| 物料编码 `FG-1001` / `SF-2001..2005` / `RM-3001..3023` | 课程未给编码，系统自定义编号方案 |
| 提前期（成品 5 天、半成品 3 天）、安全库存（1000 / 300） | 课程要求「自行设定」，取系统默认 |
| 计量单位 `PCS` | 课程未逐项标注，统一采用件 |

**不使用任何 mock / 随机数据**：入库、MRP、采购、生产、发货、退货全部走真实表、
真实流水与真实事务，端到端用例逐条断言真实数据。

---

## F. Integration Tests（跨模块集成测试）

测试规模（`pytest --collect-only`，共 **64 个用例**）：

| 测试文件 | 用例数 | 覆盖 |
| --- | --- | --- |
| `tests/test_system.py` | 17 | 物料 / BOM 三层树 / 版本切换 / 环检测 / 组织 / 人员 / RBAC / 日志 / 导入 |
| `tests/test_sales.py` | 7 | 客户 / 订单 / 发货扣减 / 超量拒绝 / 退货回增 / 契约 |
| `tests/test_planning.py` | 12 | 单层+三层 MRP / 安全库存净算 / 净需求下限 / 菱形 BOM 只抵扣一次 / 批次独立 / 领料 / 完工 / MPS 只读 / 导入预览 |
| `tests/test_procurement.py` | 8 | 供应商 / 供货关系 / 采购计划（MRP+补库）/ 回写 / 到货入库 / 超量拒绝 / 评价 |
| `tests/test_inventory.py` | 11 | 出入库 / 负库存保护 / 移库原子性 / 盘点 / 订货点 / 补库需求 / 契约 / 期初导入 |
| `tests/test_end_to_end_chair_mts.py` | 1 | 转椅 MTS 全链路（G 节） |
| 五个 `tests/<module>/test_health.py` + `tests/test_app_health.py` | 8 | 健康检查 |
| **合计** | **64** | **全部 PASS** |

跨模块链路逐条验收（均在本机真实 MySQL 上执行）：

| # | 链路 | 触发路径 | 落库证据 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | **Sales → Planning** | `POST /planning/demands/from-sales`（经 sales 契约 `list_open_order_demand` 取未交付需求） | `pln_demand` 新增行，`source_type=SALES` | **PASS** |
| 2 | **Inventory → Planning** | `POST /planning/demands/from-replenishment`（经 inventory 契约 `get_replenishment_request`） | `pln_demand`，`source_type=STOCKFILL`；`PRODUCTION` 补库生成 `pln_production_plan(source=REPLENISHMENT)` | **PASS** |
| 3 | **Planning → Procurement** | `POST /planning/mrp/runs/{id}/create-purchase-plan` | `pur_purchase_plan` + 明细，来自 MRP 的 BUY 行 | **PASS** |
| 4 | **Planning → Inventory** | `POST /planning/requisitions/{id}/confirm`、`POST /planning/completion-reports/{id}/confirm` | `inv_transaction` 写 `MATERIAL_REQUISITION`（减）/ `PRODUCTION_COMPLETION`（增），`inv_balance` 同步 | **PASS** |
| 5 | **Procurement → Inventory** | `POST /procurement/receipts/{id}/confirm` | `inv_transaction` 写 `PURCHASE_RECEIPT`（增），`inv_balance` 同步 | **PASS** |
| 6 | **Sales → Inventory** | `POST /sales/shipments/{id}/confirm` | `inv_transaction` 写发货出库（减），`sal_order_item.delivered_qty` 回写 | **PASS** |
| 7 | **Return → Inventory** | `POST /sales/returns/{id}/confirm` | `inv_transaction` 写 `SALES_RETURN`（增），`inv_balance` 同步 | **PASS** |
| 8 | **Inventory → Procurement** | `POST /inventory/replenishment-requests/generate-from-reorder-rules` → 确认 → 采购计划 | `inv_replenishment_request` → `pur_purchase_plan` | **PASS** |

对应的核心断言用例：

- 链路 1：`test_sales.py::test_contract_open_order_demand`
- 链路 2/8：`test_inventory.py::test_contract_get_replenishment_request_returns_dict`、
  `test_procurement.py::test_purchase_plan_from_replenishment`
- 链路 3：`test_procurement.py::test_purchase_plan_from_mrp_results`
- 链路 4：`test_planning.py::test_requisition_confirm_writes_ledger_and_decreases_stock`、
  `test_completion_confirm_writes_ledger_and_increases_stock`
- 链路 5：`test_procurement.py::test_receipt_confirm_increases_stock_and_writes_ledger`
- 链路 6：`test_sales.py::test_shipment_confirm_decreases_stock_and_updates_delivered`
- 链路 7：`test_sales.py::test_return_confirm_increases_stock_and_writes_ledger`

补充验证的**失败路径**（同样 PASS）：

| 场景 | 期望 | 结果 |
| --- | --- | --- |
| 出库超过结存 | 拒绝并抛 `5001`，结存不变 | PASS |
| 发货超过订单数量 | 拒绝并抛 `2003` | PASS |
| 到货超过订单数量 | 拒绝 | PASS |
| 领料时库存不足 | **整单回滚**，状态与库存均不变 | PASS |
| 已确认 MPS 被修改 | 拒绝并抛 `3002` | PASS |
| BOM 出现循环引用 | 拒绝并抛 `1003` | PASS |
| 导入预览 | 不写任何一行 | PASS |

运行命令与结果：

```bash
cd backend
pytest -q          # 64 passed，退出码 0
```

---

## G. End-to-End（完整真实运行）

用例 `backend/tests/test_end_to_end_chair_mts.py`，通过真实 HTTP API
（`TestClient` → `app.main.app` → router → service → repository）在本机真实 MySQL 上跑完整链路，
**不是 mock**，也不存在前端随机数据。

实测输出（`pytest tests/test_end_to_end_chair_mts.py -q -s`，本轮真实运行结果）：

```
[0] 基础准备：仓库#489 库位#9 组织#106 人员（销售#68/采购#69/装配#70）
[1] 课程导入：物料 29 个 / BOM 3 层（树深 3） / 期初库存 29 行 / MPS#98 12 行
[1.8] 验收 MPS#99：当前课程物料全局现存合计 1026805.0000，计划量取 11268050.0000（×10 + 1000000）以保证各层净需求恒 > 0
[2] MRP：批次 #152 与 #153，各 29 条结果；层集合 [0, 1, 2]，MAKE/BUY 分流齐全，净需求与下达日期逐行自洽
[3] 采购闭环：采购计划#60 → 订单 PO202609190053 → 到货 PR202609190023 入库 100（物料#307），流水 PURCHASE_RECEIPT 已落账
[4] 生产闭环：作业计划#67（10998910.0000）→ 派工 DSP000008 → 领料 REQ000042（5 组件出库） → 完工 CRP000025 入库 50，completed_qty 已回写
[5] 销售发货：订单 SO202609190102（100）确认 → 发货 SH202609190026 出库 40，delivered_qty 已回写，超量发货正确返回 2003
[6] 销售退货：退货单 RT202609190027 确认 → 回增库存 10，流水 SALES_RETURN 已落账
[7] 库存主动补库：订货点规则（物料#307，点 3600.0000）→ REORDER 补库 → 采购计划#61；PRODUCTION 补库 → 生产计划#73（source=REPLENISHMENT）
[8] 负库存保护：超量出库被拒（5001），物料#307 结存 3100.0000 保持不变
```

链路完整性对照：

| 规格要求的环节 | 实测是否覆盖 | 证据 |
| --- | --- | --- |
| MPS 录入 / 导入 | 是 | `[1]` 课程 MPS#98 共 12 行月度计划 |
| MRP 多层展开 | 是 | `[2]` 层集合 `[0,1,2]`，29 条结果，与课程 BOM 的 3 层 / 29 节点一致 |
| MAKE / BUY 分流 | 是 | `[2]` 两类供应类型齐全 |
| 采购闭环 | 是 | `[3]` 采购计划 → 采购订单 → 到货入库 → 流水 |
| 生产闭环 | 是 | `[4]` 作业计划 → 派工 → 领料出库 → 完工入库 → 数量回写 |
| 库存记账 | 是 | `[3][4][5][6]` 四类流水（采购入库 / 领料出库 / 完工入库 / 发货出库 / 退货入库）均落账 |
| 发货 | 是 | `[5]` 出库 40，`delivered_qty` 回写 |
| 退货 | 是 | `[6]` 回增库存 10，`SALES_RETURN` 流水 |
| 库存 → 计划反馈 | 是 | `[7]` 订货点触发补库，分别流向采购与生产 |
| 负库存保护 | 是 | `[8]` 超量出库被拒，结存不变 |

**可重复性说明**：数据库在多次运行间持续累积（共享同一个 MySQL 库），
因此本用例不硬编码期望数量，而是**从课程种子文件推导 BOM 结构**、
**由课程物料当前全局现存合计反推验收 MPS 的计划量**（`现存 × 10 + 1000000`），
从而保证各层净需求恒大于 0、每次运行都能完整展开到第 3 层。
所有业务编码都带随机后缀，用例可连续重复执行。已连续多次单跑 + 全量跑均通过。

---

## H. Remaining Issues（未完成 / 简化项，如实列出）

以下内容**未实现或做了简化**，不视为已完成：

| # | 项 | 现状 |
| --- | --- | --- |
| 1 | **鉴权** | `core/security.py` 只有占位 `HTTPBearer`，**全系统不做 `Authorization` 校验**；`POST /system/auth/login` 是简化登录（不校验权限）。RBAC 只落数据结构与分配接口，未接入请求拦截 |
| 2 | 口令存储 | `sha256` 直接哈希，**无加盐 / 无慢哈希**，不满足生产安全要求 |
| 3 | 单号 / 编码生成 | 演示级实现（前缀 + 日期 + 计数 `+1`），**并发下可能重号**，不是并发安全的正式编号器 |
| 4 | 各模块 `/health` | 占位接口，固定返回 `{module, status:"up"}`，**不反映数据库等真实依赖状态** |
| 5 | 基础数据删除 | 以「停用」代替物理删除；被引用的数据删除返回 `1009` / `5007` |
| 6 | `sys_bom.bom_code` / `sys_routing.routing_code` | **无独立唯一约束**；唯一性实际落在 `(material_id, bom_version)` / `(material_id, routing_version)` 上 |
| 7 | `source_reference_id` 类型不一致 | inventory 为 `BIGINT`，而 `pln_demand` / `pln_production_plan` / `pur_purchase_plan_item` 为 `INTEGER`；当前数据量下无影响，但类型未统一 |
| 8 | 后端 10 条路径前端暂无入口 | `/inventory/balances/available`、`/inventory/{transactions,transfers,stocktakes,replenishment-requests}/{id}`（详情）、`/planning/{demands,requisitions,dispatch-orders,completion-reports}/{id}`（详情）、`/planning/mrp/runs/{id}/results`。接口可用，仅未在页面放入口 |
| 9 | 前端残留 | `components/common/ModulePlaceholder.vue` 已无引用；`views/planning/analysis/` 目录已空 |
| 10 | 工程化 | **无 CI**（`.github/` 只有 PR / Issue 模板，无 workflows）、**无 Docker / 容器化**，只有本地开发运行方式 |
| 11 | 产能与工序排程 | 工艺路线（routing）已建数据，但 MRP 与生产计划**未按产能/工序做有限能力排程**，仍是无限能力假设 |
| 12 | 成本核算 | 只保存单价 / 金额字段，**未实现成本卷积、差异分析等成本核算功能** |

> 以上 12 项均不违反规格 §46 的硬性禁令，且不属于课程要求的核心业务链；
> 若需继续完善，建议优先级为：1 → 3 → 4 → 11 → 2。

---

## 附：一键复现全部验收项的核对命令

```bash
# 后端
cd backend
alembic history                 # 2 条迁移，HEAD = f5e52ee720d6
alembic check                   # No new upgrade operations detected
pytest -q                       # 64 passed
pytest tests/test_end_to_end_chair_mts.py -q -s   # 打印 G 节的完整链路输出
uvicorn app.main:app --reload --port 8000
# 浏览器打开 http://127.0.0.1:8000/openapi.json → 167 条路径

# 前端
cd frontend
npx vue-tsc --noEmit            # 退出码 0
npm run build                   # 构建成功
npm run dev                     # http://127.0.0.1:5173
```