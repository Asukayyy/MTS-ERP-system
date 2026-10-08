# 采购模块更新日志：移除供应商供货提前期

> 分支：`feature/procurement`　|　更新人：高歌　|　日期：2026-10-08

## 一、变更说明

移除采购模块中供应商-物料关系的「供货提前期（天）」字段及其全部业务逻辑。经核查，该字段从未被 planning MRP 或 inventory 补库使用（MRP 用的提前期来自 system 模块的 `sys_material.lead_time_days`，非采购模块），属于孤立字段，删除不影响任何跨模块数据流通。

## 二、所属模块

- procurement

## 三、变更类型

- fix 移除孤立字段
- refactor 清理业务逻辑

## 四、影响范围

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

## 五、是否修改了公共层

否。所有改动严格在 `backend/app/modules/procurement/` 和 `frontend/src/views/procurement/` 内。

## 六、数据库影响

**无影响。** `models.py` 保留 `lead_time_days` 字段映射（`nullable=False, default=0`），不删除 ORM 列、不生成迁移。数据库表结构不变，已有数据不受影响，只是 API 不再接受/返回该字段。

## 七、如何验证

1. 启动后端：`cd backend && uvicorn app.main:app --port 8000`
2. 启动前端：`cd frontend && npm run dev`
3. 访问 http://localhost:5173 → 采购管理 → 供应商-物料关系
   - 新增供货关系表单应无「供货提前期(天)」输入框
   - 列表表格应无「提前期(天)」列
4. `GET /api/v1/procurement/supplier-materials` 返回数据中无 `lead_time_days` 字段
5. `POST /api/v1/procurement/supplier-materials` 不再接受 `lead_time_days` 参数
6. 从计划生成采购订单时，`expected_date` 不再自动推算（为空时留空，由用户手动填写）

## 八、自检清单

- [x] 只改了自己模块目录
- [x] 没有 import 其他模块的 `service.py` / `repository.py` / `models.py`
- [x] 没有提交 `.env`、真实密码、`node_modules/`、`.venv/`、`__pycache__/`
- [x] 后端 import 通过
- [x] 前端编译通过（Vite HMR 正常）
- [x] 未修改数据库结构（无迁移文件）

## 九、关联 Issue

无
