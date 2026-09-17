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

本阶段是**基础工程框架**，因此：

- `backend/app/modules/*/models.py` 全部为空，**没有任何业务表**
- `backend/migrations/versions/` 为空，**没有任何迁移脚本**
- `alembic revision --autogenerate` 目前不会生成建表语句，这是预期结果

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

1. 确认这张表的 Owner 模块是你（见 `docs/architecture/data-ownership.md`）。
2. 在自己模块的 `models.py` 中定义模型，继承 `Base`：

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesOrder(Base):
    """销售订单（Owner: sales 模块）。"""

    __tablename__ = "sales_order"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
```

3. 如果这是你模块的第一个模型，检查 `backend/migrations/env.py` 是否已导入你模块的 models。
4. 生成并应用迁移：

```bash
alembic revision --autogenerate -m "create sales order table"
alembic upgrade head
```

5. 检查生成的脚本是否符合预期（`autogenerate` 不是万能的，务必人工确认）。
6. 在 `docs/architecture/data-ownership.md` 中把新表补进对应模块的表格。

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
