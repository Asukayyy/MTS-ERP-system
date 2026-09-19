# 数据库与迁移约定

## 一、数据库

| 项 | 值 |
| --- | --- |
| 数据库 | MySQL 8.x |
| 建议库名 | `bh_erp` |
| 字符集 / 排序规则 | `utf8mb4` / `utf8mb4_unicode_ci` |
| 驱动 | PyMySQL |
| ORM | SQLAlchemy 2.x |
| 迁移 | Alembic |

创建本地库（示例）：

```sql
CREATE DATABASE bh_erp DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 二、连接配置

**不要在代码或 `alembic.ini` 里写数据库密码。** 统一写在 `backend/.env` 中：

```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=bh_erp
DB_USER=root
DB_PASSWORD=你的本地密码
```

读取入口：`backend/app/core/config.py` 的 `settings`。
连接串由 `settings.database_url` 拼接，`backend/app/core/database.py` 用它创建引擎。

> `backend/.env` 已被 `.gitignore` 忽略，不会入库。仓库里只有 `.env.example`。

## 三、当前状态

库表结构已建立，共 **52 张业务表**：

| 模块 | 表数 | 表前缀 |
| --- | --- | --- |
| system | 15 | `sys_` |
| sales | 8 | `sal_` |
| planning | 10 | `pln_` |
| procurement | 9 | `pur_` |
| inventory | 10 | `inv_` |

`backend/migrations/versions/` 下已有 **2 个迁移**：

| revision | 说明 |
| --- | --- |
| `9e6fa0de8416` | `baseline schema for five modules`（五模块基线表结构） |
| `f5e52ee720d6` | `add lead time offset, return quality status and replenishment target qty`（**HEAD**） |

因此新克隆仓库后**必须执行 `alembic upgrade head`** 才能使用业务接口。

逐表逐字段的完整说明见 [physical-data-model.md](physical-data-model.md)，
ER 图见 [full-er-diagram.md](full-er-diagram.md)，
迁移工作流见 [../development/database-migration-guide.md](../development/database-migration-guide.md)。

## 四、基础类与会话

| 用途 | 位置 |
| --- | --- |
| 声明式基类 | `app.core.database.Base`，所有 ORM 模型继承它 |
| 引擎 | `app.core.database.engine` |
| 会话工厂 | `app.core.database.SessionLocal` |
| FastAPI 依赖 | `app.core.database.get_db` |

业务代码通过依赖注入拿会话：

```python
from sqlalchemy.orm import Session
from fastapi import Depends
from app.core.database import get_db

def list_orders(db: Session = Depends(get_db)):
    ...
```

## 五、新增表的完整流程

```bash
cd backend
.venv\Scripts\activate          # Windows；macOS/Linux 用 source .venv/bin/activate
```

1. 确认这张表的 Owner 模块是你（见 `docs/architecture/module-ownership.md`）。
2. 在自己模块的 `models.py` 中定义模型，继承 `Base`，
   类型别名统一用 `app.core.mixins` 提供的（**不要**手写 `String(32)` 或 `Float`）：

```python
from app.core.database import Base
from app.core.mixins import AuditMixin, BigIntFk, BigIntPk, CodeStr, NameStr, Quantity


class SalesOrder(Base, AuditMixin):
    """销售订单（Owner: sales 模块）。"""

    __tablename__ = "sal_order"          # 必须是模块前缀 sal_

    id: BigIntPk
    customer_id: BigIntFk                # 外键列名为 <entity>_id，类型 BIGINT
    order_no: CodeStr                    # VARCHAR(50)，业务编码/单号
    order_name: NameStr                  # VARCHAR(100)
    quantity: Quantity                   # DECIMAL(18,4)
```

> 命名规范、主键/外键规则、统一数据类型见
> [data-dictionary.md](data-dictionary.md)（对应规格 §18~§22）。

3. 检查 `backend/migrations/env.py` 是否已导入你模块的 models（目前五个模块均已导入）。
4. 生成并应用迁移：

```bash
alembic revision --autogenerate -m "create sales order table"
alembic upgrade head
```

5. 检查生成的脚本是否符合预期（`autogenerate` 不是万能的，务必人工确认；
   **MySQL 的 CHECK 约束不会被 autogenerate 检测**，需手写 `op.create_check_constraint`）。
6. 用 `alembic check` 确认模型与库已一致。
7. 在 `docs/architecture/module-ownership.md` 中把新表补进对应模块的表格。

> 完整流程与注意事项见 [../development/database-migration-guide.md](../development/database-migration-guide.md)。

## 六、协作规则

1. 迁移文件在 `backend/migrations/versions/`，**必须提交到 git**。
2. 迁移文件一旦推送到 `develop`，**其他人不得修改**；需要变更请追加新迁移。
3. 不要提交本地数据库文件（`*.sqlite`、`*.db`、导出的 `.sql` 备份）。
4. 不要手工改别人的迁移文件；发现别人的迁移有问题，找对应负责人。
5. 回退操作（`alembic downgrade`）在共享环境上慎用，本地随意。

## 七、常用命令

```bash
alembic revision --autogenerate -m "描述"   # 生成迁移
alembic upgrade head                        # 应用全部迁移
alembic downgrade -1                        # 回退一个版本
alembic current                             # 查看当前版本
alembic history                             # 查看迁移历史
```
