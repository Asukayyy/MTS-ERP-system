# 采购模块更新日志

> 分支：`feature/procurement`　|　更新人：高歌　|　日期：2026-10-08

## 一、本次提交范围

仅包含**采购模块边界内**的代码修复与设计文档，未修改其他模块后端代码。

### 代码文件（4 个）

| 文件 | 改动类型 |
|------|---------|
| `backend/app/modules/procurement/repository.py` | 修改 |
| `backend/app/modules/procurement/service.py` | 修改 |
| `frontend/src/views/procurement/plan/index.vue` | 修改 |
| `frontend/src/views/procurement/evaluation/index.vue` | 修改 |

### 设计文档（3 个，从本地存档恢复）

| 文件 | 说明 |
|------|------|
| `docs/procurement/functional-design.md` | 功能设计文档（功能树 + 详细功能设计） |
| `docs/procurement/data-flow-diagrams.md` | 各级数据流图 |
| `docs/procurement/module-relationships.md` | 与其他模块的关系图 |

---

## 二、代码修复明细

### 1. 到货报表字段引用错误（已修复）

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

### 2. 停用供应商仍可被新单据引用（已修复）

**文件**：`service.py`

**问题**：`_require_supplier()` 只校验供应商存在性，不校验状态。停用（INACTIVE）供应商仍可被新建供货关系、计划、订单引用，违反功能树 1.4 设计要求。

**修复**：`_require_supplier()` 新增 `require_active: bool = False` 参数，在以下 5 个建单调用点传 `require_active=True`：
- `create_supplier_material()` — 建供货关系
- `_add_plan_item()` — 建计划行
- `create_order()` — 建订单
- `update_order()` — 改订单供应商
- `create_order_from_plan()` — 计划转订单

停用供应商创建新单据时返回 4000「供应商 xxx 已停用，不可被新单据引用」。

### 3. MRP / 补库转计划重复生成（已修复）

**文件**：`repository.py` + `service.py`

**问题**：`_resolve_reusable_plan()` 按 `source_reference_id` 去重，但 MRP 每次运行生成新 result ID、补库每次生成新 RPL 单号，导致每次调用都查不到旧计划 → 重复生成内容相同的草稿计划。

**修复**：
- 新增 `find_active_plan_by_source_type(db, source_type)` 函数，按来源类型查找未终结（非 COMPLETED/CANCELLED）的计划
- 在 `create_purchase_plan_from_mrp` 和 `create_purchase_plan_from_replenishment` 中作为 fallback：第一层按 reference_id 查，查不到则第二层按 source_type 查，找到就复用

### 4. 采购统计口径改为本期（本月）（已修复）

**文件**：`service.py`

**问题**：`stats()` 返回全量总计，工作台显示的是历史累计而非本期数据。

**修复**：所有计数改为 `>= 本月1号` 口径：
- `supplier_count` / `supplier_material_count`：按 `created_at`
- `plan_count` / `plan_counts`：按 `plan_date`
- `order_count` / `order_counts`：按 `order_date`
- `receipt_count`：按 `receipt_date`
- `evaluation_count`：按 `evaluate_date`
- `pending_receipt_line_count`：保持不变（当前未到货状态量，非期间计数）

### 5. 采购计划草稿无编辑按钮（已修复）

**文件**：`plan/index.vue`

**问题**：草稿状态操作列只有「查看明细 / 确认 / 生成采购订单 / 取消」，缺少「编辑」。

**修复**：
- DRAFT 状态新增「编辑」按钮
- 新增 `openEdit(row)` 方法，调用 `getPurchasePlan` 回填表单
- `submit()` 按 `editingId` 区分创建/编辑

### 6. 供应商评价无删除按钮（已修复）

**文件**：`evaluation/index.vue`

**问题**：评价表格无操作列，无法删除评价。

**修复**：
- 新增「操作」列含「删除」按钮
- 新增 `handleDelete(row)` 调用 `deleteEvaluation`

---

## 三、边界说明

| 改动 | 是否在采购模块内 |
|------|----------------|
| repository.py / service.py | ✅ 是 |
| plan/index.vue / evaluation/index.vue | ✅ 是 |
| docs/procurement/*.md | ✅ 是 |

**未包含**：`frontend/src/views/dashboard/index.vue` 的 `page_size: 500 → 200` 修复（属共享页面，非采购模块边界），该改动仍保留在本地工作区未提交。

---

## 四、验证结果

| 测试项 | 结果 |
|--------|------|
| 到货报表 5 个端点 | 全部 HTTP 200 |
| 停用供应商建订单/供货关系 | 返回 4000「已停用」 |
| MRP/补库重复生成 | 复用已有草稿，不再新建 |
| 采购统计 | 本月口径（supplier 0/plan 0/order 0） |
| 草稿计划编辑 | 按钮可用，回填正确 |
| 评价删除 | 按钮可用，删除成功 |

---

## 五、回撤方式

如需回撤本次提交：
```powershell
git reset --hard HEAD~1
```
