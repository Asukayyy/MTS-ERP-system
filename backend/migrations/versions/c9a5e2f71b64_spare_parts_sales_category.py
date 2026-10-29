"""标记可独立零售的自制维修备件

背景：
    销售预测与实时库存需要区分「整机 / 可售备件 / 内部件」。
    仅把本公司自制、外部市场买不到、且客户会单独购买更换的零件标为
    `SPARE`；五金店可买到的标准件、原材料、包装材料均保持 `INTERNAL`。

Revision ID: c9a5e2f71b64
Revises: b3e7a9c52d18
Create Date: 2026-10-25
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9a5e2f71b64"
down_revision: Union[str, None] = "b3e7a9c52d18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: 可售备件物料编码
SPARE_CODES = (
    "RM-3001",        # 脚轮
    "RM-3005",        # 背猪腰
    "SF-KIT-001",     # 配件包
    "RM-PISTON-001",  # 活塞
    "RM-FRICTION-001",  # 摩擦片
    "RM-SPACER-001",  # 隔垫
    "RM-SLEEVE-001",  # 开口导向套管
    "RM-HOUSING-L",   # 左壳体
    "RM-HOUSING-R",   # 右壳体
    "RM-BRACKET-001",  # 支架
)

_CODES_SQL = ", ".join(f"'{code}'" for code in SPARE_CODES)


def upgrade() -> None:
    op.execute(
        f"UPDATE sys_material SET sales_category = 'SPARE' "
        f"WHERE material_code IN ({_CODES_SQL})"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE sys_material SET sales_category = 'INTERNAL' "
        f"WHERE material_code IN ({_CODES_SQL})"
    )
