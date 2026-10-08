# Inventory 模块设计文档与汇报材料

库存管理（inventory）模块的课程设计文档目录。**模块已实现并验证**。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [week3-implementation.md](week3-implementation.md) | 第 3 周：库存模块详细设计与实现说明（模块定位、10 表数据模型、库存引擎、订货点、契约、36 接口、前端、测试验证） |
| [presentation/库存管理模块课程设计汇报.pptx](presentation/库存管理模块课程设计汇报.pptx) | **汇报 PPT（16 页，16:9）** |
| [presentation/库存管理模块汇报讲稿.md](presentation/库存管理模块汇报讲稿.md) | **逐页讲稿（约 9–10 分钟）+ 7 个追问答疑要点** |
| [presentation/build_pptx.py](presentation/build_pptx.py) | PPT 生成脚本（`python build_pptx.py` 可改后重新生成，需 python-pptx） |

## 全组统一权威文档（非本目录，汇报引用用）

| 内容 | 出处 |
| --- | --- |
| 库存 ER 图与 23 条外键明细 | [docs/database/inventory-er.md](../database/inventory-er.md) |
| 全字段物理模型 | [docs/database/physical-data-model.md](../database/physical-data-model.md) |
| 全系统 167 个 API 定义 | [docs/api/api-contract.md](../api/api-contract.md) |
| 数据所有权与模块边界 | [docs/architecture/data-ownership.md](../architecture/data-ownership.md) |

## 代码位置

| 层 | 路径 |
| --- | --- |
| 后端（models/schemas/repository/service/router/contract） | `backend/app/modules/inventory/` |
| 后端测试 | `backend/tests/test_inventory.py`（11 个业务用例）、`backend/tests/inventory/test_health.py` |
| 建表迁移 | `backend/migrations/versions/9e6fa0de8416_baseline_schema_for_five_modules.py` |
| 前端 API 封装（36 端点） | `frontend/src/api/inventory/index.ts` |
| 前端页面（8 个） | `frontend/src/views/inventory/` |

## 规模数字（汇报口径，均已在本机核对）

- 数据表：10 张（`inv_` 前缀），外键 23 条
- HTTP 接口：36 个（前缀 `/api/v1/inventory`；全系统 OpenAPI 167 路径）
- 前端页面：8 个；TS 类型 16 个
- 业务测试：11 个（需真实 MySQL）+ 健康检查 1 个（已通过）
- 业务错误码区段：5000–5007
