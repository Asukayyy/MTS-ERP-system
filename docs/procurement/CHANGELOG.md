# 采购模块更新日志（CHANGELOG）

> 分支：`feature/procurement`　|　维护人：高歌
>
> 本文件合并记录采购模块历次变更，**最新批次在前**；每批均严格限定在采购模块边界内。

---

## 2026-10-15　第三批：expected_date 回归推算 + 串单 bug 修复 + 测试加固

### 一、变更说明

上一批（移除供货提前期）落地后暴露两类问题，本次一并修复：

1. **`expected_date` 写入 NULL 报错**：移除提前期时连带删除了 `create_order_from_plan`
   中推算 `expected_date` 的逻辑，而该列为 `NOT NULL`，由计划生成订单时直接触发数据库写入错误。
2. **MRP / 补库转计划跨来源串单**：第一批为解决"重复生成"引入的
   `find_active_plan_by_source_type` fallback 只按 `source_type` 匹配"任意未终结计划"，
   会把不同来源单据（不同 RPL 单号）的需求错误追加进同一个 DRAFT 计划
   （测试表现为 `test_purchase_plan_from_replenishment` 断言 `assert 2 == 1`）。

### 二、影响范围

| 文件 | 改动 |
|------|------|
| `backend/app/modules/procurement/service.py` | ① `expected_date` 恢复自动推算：提前期改从 system 模块 `sys_material.lead_time_days` 取值（经 `system.contract` 读取，多物料取最大值）；② 移除 MRP / 补库两处 `find_active_plan_by_source_type` fallback，回归**严格幂等**（只按 `source_reference_id` 精确匹配复用） |
| `backend/app/modules/procurement/repository.py` | 删除死代码 `find_active_plan_by_source_type`（约 26 行） |
| `backend/tests/test_procurement.py` | ① 计划生成断言改为按 `source_reference_id` 精确定位本次明细（不受计划复用与共享库基线影响）；② 新增 2 个用例：多物料取最大提前期、显式 `expected_date` 优先于推算 |
| `frontend/src/views/procurement/receipt/index.vue` | 新增到货单的「采购订单」下拉选项改为显示供应商名称（原为 `供应商{ID}`），无名称时降级显示 ID；「供应商ID」栏保持只读、选单后自动带出 |
| `docs/procurement/conceptual-model.md` | 新增：系统信息概念模型（Chen 记号 E-R 图，实体与联系全部来源于本地项目）+ 物理数据模型（9 张 `pur_*` 表逐表逐字段） |
| `docs/procurement/functional-design.md`、`data-flow-diagrams.md` | 修正指向不存在文件的失效引用，统一指向 conceptual-model.md |
| `docs/procurement/CHANGELOG.md` | 合并原 `CHANGELOG.md` 与 `CHANGELOG-lead-time-removal.md` 为一份，新增本批记录 |

### 三、对前两批记录的修正

- **第二批「如何验证」第 6 条已作废**：「`expected_date` 不再自动推算（为空时留空）」的做法引发
  NOT NULL 写入错误，现恢复自动推算；提前期来源为 `sys_material.lead_time_days`
  （system 模块，MRP 同源），而非已删除的 `pur_supplier_material.lead_time_days`。
- **第一批「修复 3」中的 fallback 已回撤**：按 `source_type` 兜底去重属于过度宽泛，导致跨来源串单；
  「重复生成」问题的正解是严格幂等（按 `source_reference_id` 精确匹配）+ 测试断言按来源精筛，
  共享库中残留 DRAFT 计划不再影响测试结果。

### 四、验证结果

| 测试项 | 结果 |
|--------|------|
| `python -m pytest tests/test_procurement.py`（10 个用例） | 全部通过（14.93s） |
| `test_purchase_plan_from_replenishment`（队友报告的 `assert 2 == 1` 失败用例） | 通过 |
| `test_purchase_plan_from_mrp_results`（同模式加固） | 通过 |
| 前端 Vite 编译 | 通过（HMR 正常，无编译错误） |
| 边界检查 | 全部改动在 `backend/app/modules/procurement/`、`backend/tests/test_procurement.py`、`frontend/src/views/procurement/`、`docs/procurement/` 内 |

### 五、回撤方式

```powershell
git reset --hard HEAD~1
```

---

## 2026-10-08　第二批：移除供应商供货提前期

> 原 `CHANGELOG-lead-time-removal.md`，合并入本文件；「如何验证」第 6 条已被 2026-10-15 批次修正。

### 一、变更说明

移除采购模块中供应商-物料关系的「供货提前期（天）」字段及其全部业务逻辑。经核查，该字段从未被 planning MRP 或 inventory 补库使用（MRP 用的提前期来自 system 模块的 `sys_material.lead_time_days`，非采购模块），属于孤立字段，删除不影响任何跨模块数据流通。

### 二、所属模块

- procurement

### 三、变更类型

- fix 移除孤立字段
- refactor 清理业务逻辑

### 四、影响范围

| 文件 | 改动 |
|------|------|
| `backend/app/modules/procurement/schemas.py` | 删除 `SupplierMaterialCreate/Update/Out` 和 `PurchaseMaterialOut` 的 `lead_time_days` 字段；`expected_date` 描述去掉提前期推算 |
| `backend/app/modules/procurement/router.py` | 删除 create/update supplier-material 的 `lead_time_days` 传参；修改注释 |
| `backend/app/modules/procurement/service.py` | 删除 `create_supplier_material`/`update_supplier_material` 的 `lead_time_days` 参数与赋值；删除 `create_order_from_plan` 中用提前期推算 `expected_date` 的逻辑；删除 `timedelta` import；删除返回字典中的 `lead_time_days` |
| `backend/app/modules/procurement/models.py` | 仅更新类注释文档字符串（**保留 `lead_time_days` 字段映射，不动数据库结构，无需迁移**） |
| `backend/app/modules/procurement/README.md` | 功能描述去掉「提前期」 |
| `frontend/src/views/procurement/supplier-material/index.vue` | 删除类型定义、表单 reactive、openCreate/openEdit 赋值、submit 传参中的 `lead_time_days`；删除表格列和表单输入框 |
| `frontend/src/views/procurement/plan/index.vue` | placeholder 文案去掉「与提前期」「按供货提前期推算」 |
| `frontend/src/views/procurement/order/index.vue` | 同上两处 placeholder |

### 五、是否修改了公共层

否。所有改动严格在 `backend/app/modules/procurement/` 和 `frontend/src/views/procurement/` 内。

### 六、数据库影响

**无影响。** `models.py` 保留 `lead_time_days` 字段映射（`nullable=False, default=0`），不删除 ORM 列、不生成迁移。数据库表结构不变，已有数据不受影响，只是 API 不再接受/返回该字段。

### 七、如何验证

1. 启动后端：`cd backend && uvicorn app.main:app --port 8000`
2. 启动前端：`cd frontend && npm run dev`
3. 访问 http://localhost:5173 → 采购管理 → 供应商-物料关系
   - 新增供货关系表单应无「供货提前期(天)」输入框
   - 列表表格应无「提前期(天)」列
4. `GET /api/v1/procurement/supplier-materials` 返回数据中无 `lead_time_days` 字段
5. `POST /api/v1/procurement/supplier-materials` 不再接受 `lead_time_days` 参数
6. ~~从计划生成采购订单时，`expected_date` 不再自动推算（为空时留空，由用户手动填写）~~
   **【2026-10-15 修正】** 该做法引发 NOT NULL 写入错误，已恢复自动推算：
   `expected_date = 下单日 + max(sys_material.lead_time_days)`，显式传入的日期优先。

### 八、自检清单

- [x] 只改了自己模块目录
- [x] 没有 import 其他模块的 `service.py` / `repository.py` / `models.py`
- [x] 没有提交 `.env`、真实密码、`node_modules/`、`.venv/`、`__pycache__/`
- [x] 后端 import 通过
- [x] 前端编译通过（Vite HMR 正常）
- [x] 未修改数据库结构（无迁移文件）

### 九、关联 Issue

无

---

## 2026-10-08　第一批：模块修复与设计文档恢复

> 原 `CHANGELOG.md` 内容，合并入本文件；其中「修复 3」的 fallback 已被 2026-10-15 批次回撤。

### 一、本次提交范围

仅包含**采购模块边界内**的代码修复与设计文档，未修改其他模块后端代码。

**代码文件（4 个）**

| 文件 | 改动类型 |
|------|---------|
| `backend/app/modules/procurement/repository.py` | 修改 |
| `backend/app/modules/procurement/service.py` | 修改 |
| `frontend/src/views/procurement/plan/index.vue` | 修改 |
| `frontend/src/views/procurement/evaluation/index.vue` | 修改 |

**设计文档（3 个，从本地存档恢复）**

| 文件 | 说明 |
|------|------|
| `docs/procurement/functional-design.md` | 功能设计文档（功能树 + 详细功能设计） |
| `docs/procurement/data-flow-diagrams.md` | 各级数据流图 |
| `docs/procurement/module-relationships.md` | 与其他模块的关系图 |

### 二、代码修复明细

#### 1. 到货报表字段引用错误（已修复）

**文件**：`repository.py`

**问题**：`receipt_report()` 查询中从 `PurReceiptItem`（到货行表）取 `warehouse_id`，但该字段实际在 `PurReceipt`（到货单头表）上，导致 `AttributeError` → HTTP 500。

**修复**：
```python
# 修复前
models.PurReceiptItem.warehouse_id,  # ❌ 行表无此字段
models.PurReceiptItem.location_id,   # 多余列

# 修复后
models.PurReceipt.warehouse_id,      # ✅ 头表字段
# 删除 location_id 列（与 service 10 字段位置解包对齐）
```

#### 2. 停用供应商仍可被新单据引用（已修复）

**文件**：`service.py`

**问题**：`_require_supplier()` 只校验供应商存在性，不校验状态。停用（INACTIVE）供应商仍可被新建供货关系、计划、订单引用，违反功能树 1.4 设计要求。

**修复**：`_require_supplier()` 新增 `require_active: bool = False` 参数，在以下 5 个建单调用点传 `require_active=True`：
- `create_supplier_material()` — 建供货关系
- `_add_plan_item()` — 建计划行
- `create_order()` — 建订单
- `update_order()` — 改订单供应商
- `create_order_from_plan()` — 计划转订单

停用供应商创建新单据时返回 4000「供应商 xxx 已停用，不可被新单据引用」。

#### 3. MRP / 补库转计划重复生成（已修复；fallback 于 2026-10-15 回撤）

**文件**：`repository.py` + `service.py`

**问题**：`_resolve_reusable_plan()` 按 `source_reference_id` 去重，但 MRP 每次运行生成新 result ID、补库每次生成新 RPL 单号，导致每次调用都查不到旧计划 → 重复生成内容相同的草稿计划。

**当时修复**（**已被 2026-10-15 批次回撤**）：
- 新增 `find_active_plan_by_source_type(db, source_type)` 函数，按来源类型查找未终结计划作为 fallback
- 该 fallback 只按 `source_type` 匹配，会把不同来源单据的需求错误追加进同一个计划（串单），
  已于 2026-10-15 移除并删除死代码；正解为严格幂等（只按 `source_reference_id` 精确匹配），
  详见 2026-10-15 批次说明。

#### 4. 采购统计口径改为本期（本月）（已修复）

**文件**：`service.py`

**问题**：`stats()` 返回全量总计，工作台显示的是历史累计而非本期数据。

**修复**：所有计数改为 `>= 本月1号` 口径：
- `supplier_count` / `supplier_material_count`：按 `created_at`
- `plan_count` / `plan_counts`：按 `plan_date`
- `order_count` / `order_counts`：按 `order_date`
- `receipt_count`：按 `receipt_date`
- `evaluation_count`：按 `evaluate_date`
- `pending_receipt_line_count`：保持不变（当前未到货状态量，非期间计数）

#### 5. 采购计划草稿无编辑按钮（已修复）

**文件**：`plan/index.vue`

**问题**：草稿状态操作列只有「查看明细 / 确认 / 生成采购订单 / 取消」，缺少「编辑」。

**修复**：
- DRAFT 状态新增「编辑」按钮
- 新增 `openEdit(row)` 方法，调用 `getPurchasePlan` 回填表单
- `submit()` 按 `editingId` 区分创建/编辑

#### 6. 供应商评价无删除按钮（已修复）

**文件**：`evaluation/index.vue`

**问题**：评价表格无操作列，无法删除评价。

**修复**：
- 新增「操作」列含「删除」按钮
- 新增 `handleDelete(row)` 调用 `deleteEvaluation`

### 三、边界说明

| 改动 | 是否在采购模块内 |
|------|----------------|
| repository.py / service.py | ✅ 是 |
| plan/index.vue / evaluation/index.vue | ✅ 是 |
| docs/procurement/*.md | ✅ 是 |

**未包含**：`frontend/src/views/dashboard/index.vue` 的 `page_size: 500 → 200` 修复（属共享页面，非采购模块边界），该改动仍保留在本地工作区未提交。

### 四、验证结果

| 测试项 | 结果 |
|--------|------|
| 到货报表 5 个端点 | 全部 HTTP 200 |
| 停用供应商建订单/供货关系 | 返回 4000「已停用」 |
| MRP/补库重复生成 | 复用已有草稿，不再新建 |
| 采购统计 | 本月口径（supplier 0/plan 0/order 0） |
| 草稿计划编辑 | 按钮可用，回填正确 |
| 评价删除 | 按钮可用，删除成功 |

### 五、回撤方式

```powershell
git reset --hard HEAD~1
```
