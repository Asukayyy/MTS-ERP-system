"""procurement 模块 ORM 模型。

**当前不定义任何 ERP 业务表。**

本模块未来的表（建议，见 docs/architecture/data-ownership.md）：
pur_supplier / pur_supplier_material / pur_purchase_plan / pur_purchase_plan_item /
pur_order / pur_order_item / pur_receipt / pur_receipt_item /
pur_supplier_evaluation

新建模型时：
1. 继承 `app.core.database.Base`
2. 表名使用小写下划线命名
3. 建表后执行 `alembic revision --autogenerate -m "..."` 生成迁移
"""
