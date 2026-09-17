"""sales 模块 ORM 模型。

**当前不定义任何 ERP 业务表。**

本模块未来的表（建议，见 docs/architecture/data-ownership.md）：
sal_customer / sal_forecast / sal_order / sal_order_item / sal_shipment /
sal_shipment_item / sal_return / sal_return_item

新建模型时：
1. 继承 `app.core.database.Base`
2. 表名使用小写下划线命名
3. 建表后执行 `alembic revision --autogenerate -m "..."` 生成迁移
"""
