"""system：修正「库存流水」菜单权限的名称与路径

背景：
    `inventory:ledger` 早期定义为「库存流水与结存」，路径指向早已不存在的
    `/inventory/transaction`。库存流水页实际路由是 `/inventory/stock-journal`，
    代码里的权限种子已改，但 `seed_roles_and_permissions` 对**已存在**的权限只跳过、
    不覆盖元数据（以免冲掉人工调整），所以任何已初始化的库里这一行仍是旧值，
    权限管理页面上显示的名字 / 路径与实际菜单对不上。

本迁移只做一次数据校正，不涉及表结构：
    perm_name: 库存流水与结存 → 库存流水
    path:      /inventory/ledger → /inventory/stock-journal

Revision ID: d2f5a9c4e018
Revises: c1e4b8f7a2d9
Create Date: 2026-10-29
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "d2f5a9c4e018"
down_revision: Union[str, None] = "c1e4b8f7a2d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERM_CODE = "inventory:ledger"


def upgrade() -> None:
    op.get_bind().execute(
        text(
            "UPDATE sys_permission SET perm_name = :name, path = :path "
            "WHERE perm_code = :code"
        ),
        {"name": "库存流水", "path": "/inventory/stock-journal", "code": PERM_CODE},
    )


def downgrade() -> None:
    op.get_bind().execute(
        text(
            "UPDATE sys_permission SET perm_name = :name, path = :path "
            "WHERE perm_code = :code"
        ),
        {"name": "库存流水与结存", "path": "/inventory/ledger", "code": PERM_CODE},
    )
