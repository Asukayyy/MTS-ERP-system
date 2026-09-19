"""ORM 公共列类型与 Mixin。

统一约定来源：`docs/requirements/BH-ERP-完整开发规格.md`（§18 命名规范、§19 主键、
§20 外键、§22 数据类型、§24 审计与追踪）与 `docs/architecture/data-ownership.md`。

硬性约定：

- 主键：所有业务表统一 `id BIGINT PRIMARY KEY`（使用 `BigIntPk`）。
- 外键：统一指向对方 `id`，类型 `BIGINT`（使用 `BigIntFk`）。
- 业务编码：`VARCHAR(50) UNIQUE NOT NULL`（使用 `CodeStr`）。
- 名称 `VARCHAR(100)`、状态 `VARCHAR(20)`。
- 数量 `DECIMAL(18,4)`（`Quantity`）、金额 `DECIMAL(18,2)`（`Money`）、
  比例 `DECIMAL(8,4)`（`Ratio`）。**禁止用 FLOAT 存储关键数量与金额。**
- 业务日期 `DATE`、时间戳 `DATETIME`。
- 审计列：`created_at / updated_at / created_by / updated_by`（`AuditMixin`）。

用法示例：

```python
class SysMaterial(Base, AuditMixin):
    __tablename__ = "sys_material"

    id: Mapped[BigIntPk]
    material_code: Mapped[CodeStr] = mapped_column(unique=True, comment="物料编码")
    safety_stock: Mapped[Quantity] = mapped_column(default=0, comment="安全库存")
```
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Optional

from sqlalchemy import BigInteger, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

# ==================== 列类型别名 ====================

#: 主键：`id BIGINT PRIMARY KEY AUTO_INCREMENT`
BigIntPk = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]

#: 外键：`BIGINT`，指向对方表 `id`
BigIntFk = Annotated[int, mapped_column(BigInteger)]

#: 业务编码 / 单号：`VARCHAR(50)`
CodeStr = Annotated[str, mapped_column(String(50))]

#: 名称：`VARCHAR(100)`
NameStr = Annotated[str, mapped_column(String(100))]

#: 状态 / 枚举：`VARCHAR(20)`
StatusStr = Annotated[str, mapped_column(String(20))]

#: 数量：`DECIMAL(18,4)`
Quantity = Annotated[Decimal, mapped_column(Numeric(18, 4))]

#: 金额：`DECIMAL(18,2)`
Money = Annotated[Decimal, mapped_column(Numeric(18, 2))]

#: 比例（如损耗率）：`DECIMAL(8,4)`
Ratio = Annotated[Decimal, mapped_column(Numeric(8, 4))]


# ==================== Mixin ====================


class PkMixin:
    """自增 BIGINT 主键。仅在需要显式声明时才继承（通常直接写 `id: Mapped[BigIntPk]`）。"""

    id: Mapped[BigIntPk]


class TimestampMixin:
    """时间戳审计列。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )


class AuditMixin(TimestampMixin):
    """完整审计列：时间 + 操作人（指向 `sys_user.id`，不建外键以便框架层解耦）。"""

    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="创建人ID（sys_user.id）"
    )
    updated_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="更新人ID（sys_user.id）"
    )