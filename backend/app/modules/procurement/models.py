"""procurement 模块 ORM 模型。

**当前不定义任何 ERP 业务表。**

本模块未来的表（建议，见 docs/architecture/data-ownership.md）：
supplier / purchase_plan / purchase_plan_line /
purchase_order / purchase_order_line / receiving / receiving_line

新建模型时：
1. 继承 `app.core.database.Base`
2. 表名使用小写下划线命名
3. 建表后执行 `alembic revision --autogenerate -m "..."` 生成迁移
"""
