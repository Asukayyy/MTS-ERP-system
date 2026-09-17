"""system 模块 ORM 模型。

**当前不定义任何 ERP 业务表。**

本模块未来的表（建议，见 docs/architecture/data-ownership.md）：
sys_material / sys_bom / sys_bom_item / sys_routing / sys_routing_operation /
sys_organization / sys_personnel / sys_dictionary / sys_dictionary_item /
sys_user / sys_role / sys_permission / sys_user_role / sys_role_permission /
sys_operation_log

新建模型时：
1. 继承 `app.core.database.Base`
2. 表名使用小写下划线命名
3. 建表后执行 `alembic revision --autogenerate -m "..."` 生成迁移
"""
