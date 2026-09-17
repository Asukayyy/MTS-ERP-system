# Alembic 迁移说明

## 目录用途

存放数据库结构变更脚本。当前 `versions/` 为空，因为本阶段（基础框架）**不创建任何业务表**。

## 常用命令

在 `backend/` 目录下执行（先激活虚拟环境，并确保 `.env` 已配置好 `DB_*`）：

```bash
# 生成迁移脚本（根据 models.py 与数据库现状的差异）
alembic revision --autogenerate -m "create sales order tables"

# 应用到数据库
alembic upgrade head

# 回退一个版本
alembic downgrade -1

# 查看当前版本
alembic current
```

## 协作约定

1. 建表前先确认这张表的 Owner 模块是你（见 `docs/architecture/data-ownership.md`）。
2. 迁移文件一旦推送到 `develop`，**其他人不得修改**；需要变更请追加新迁移。
3. 迁移文件必须提交到 git，数据库本地文件不要提交。
4. 新增模块模型后，记得在 `migrations/env.py` 的 models 导入区补一行。
