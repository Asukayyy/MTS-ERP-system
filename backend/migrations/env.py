"""Alembic 迁移环境。

要点：
1. 连接串从 `app.core.config.settings` 读取（`backend/.env`），**不在 alembic.ini 中写死密码**。
2. `target_metadata = Base.metadata`，因此各模块 `models.py` 中继承 `Base` 的表会被自动收集。
3. 新增模块的模型后，记得在上面的 models 导入区补一行，否则 autogenerate 发现不了该模块的表。

当前 `Base.metadata` 已包含五个模块的 **52 张业务表**（system 15 / sales 8 / planning 10 /
procurement 9 / inventory 10，含 BOM 明细、库存流水、MRP 结果等）。

迁移链：

- `9e6fa0de8416` 基线：一次性建立全部业务表、外键与 CHECK 约束
- `f5e52ee720d6` 补充：BOM 提前期偏置、退货质量状态、补库目标量

每次改完 `models.py` 后执行 `alembic revision --autogenerate -m "..."`，
再用 `alembic check` 确认没有遗漏的漂移（MySQL 的 CHECK 约束不会被 autogenerate 检测，需手工补）。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base

# 导入各模块的模型，保证 autogenerate 能发现所有表
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.planning import models as planning_models  # noqa: F401
from app.modules.procurement import models as procurement_models  # noqa: F401
from app.modules.sales import models as sales_models  # noqa: F401
from app.modules.system import models as system_models  # noqa: F401

config = context.config

# 把 .env 中的数据库连接串注入 Alembic 配置
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 脚本，不连接数据库。"""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
