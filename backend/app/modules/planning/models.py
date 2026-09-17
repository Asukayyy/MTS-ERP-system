"""planning 模块 ORM 模型。

**当前不定义任何 ERP 业务表，也不实现 MPS / MRP 算法。**

本模块未来的表（建议，见 docs/architecture/data-ownership.md）：
mps / mps_line / mrp_result / planned_order /
production_work_plan / dispatch_order / material_requisition

新建模型时：
1. 继承 `app.core.database.Base`
2. 表名使用小写下划线命名
3. 建表后执行 `alembic revision --autogenerate -m "..."` 生成迁移
"""
