# 数据库迁移指南（Alembic）

本仓库的库表结构**只通过 Alembic 迁移演进**。

> 规格 §31 原文要求：严禁通过群里传 `final.sql` / `final2.sql` / `真正final.sql` 来维护数据库结构，
> 必须使用 Alembic，并保证 Migration 可追踪。

## 一、为什么禁止传 SQL 文件

| 传 SQL 文件的后果 | 迁移文件的做法 |
| --- | --- |
| 每个人的库结构靠口头/截图对齐，无法追溯 | 结构变化有 revision id、有时间、有 commit 记录 |
| 不知道自己的库是第几版 | `alembic current` 一条命令就能确认 |
| 有人改了表但没通知别人 | 迁移文件入库 + PR，所有人都能看到 |
| 出问题无法回退 | `downgrade()` 明确写了回退方式 |

因此：

- **禁止**在群里/仓库里传 `final.sql`、`db.sql`、导出的 `.sql` 备份来同步结构。
- 迁移文件**必须提交到 git**（在 `backend/migrations/versions/`）。
- 本地数据库文件（`*.sqlite`/`*.db`/`*.sql` 备份）**不进仓库**（`.gitignore` 已忽略 `*.sqlite`、`*.sqlite3`、`*.db`）。

## 二、相关文件

| 文件 | 作用 |
| --- | --- |
| `backend/alembic.ini` | Alembic 配置：`script_location = migrations`、`prepend_sys_path = .`。**不含数据库 URL**（避免提交密码） |
| `backend/migrations/env.py` | 运行时从 `app.core.config.settings` 注入 `sqlalchemy.url`；导入五个模块的 `models`；`target_metadata = Base.metadata`；开启 `compare_type=True` |
| `backend/migrations/versions/` | 迁移脚本目录 |
| `backend/app/core/database.py` | `Base`、`engine`、`SessionLocal`、`get_db` |

因为 URL 由 `env.py` 在运行时注入，所以 `alembic` 命令**必须在 `backend/` 目录、且 `.env` 配置正确的情况下执行**。

## 三、当前迁移链

| 顺序 | revision | 标题 | 内容 |
| --- | --- | --- | --- |
| 1 | `9e6fa0de8416` | `baseline schema for five modules` | 五模块 52 张表的基线结构 |
| 2 | `f5e52ee720d6` | `add lead time offset, return quality status and replenishment target qty` | 给 `sys_bom_item` 加 `lead_time_offset`、给 `sal_return_item` 加 `quality_status`、给 `inv_replenishment_request` 加 `target_qty`，并补 2 个 CHECK 约束 |

`f5e52ee720d6` 是当前的 **HEAD**。

表结构现状可用以下命令查看：

```bash
alembic current     # 当前库停在哪个 revision
alembic heads       # 代码里的 head（应为 f5e52ee720d6）
alembic history     # 完整迁移历史
```

## 四、标准工作流

每一次 schema 变化都走同一条链路（规格 §31）：

```
Model  →  Migration  →  Git  →  Pull Request  →  其他成员 alembic upgrade head
```

具体步骤：

```bash
cd backend
.venv\Scripts\activate              # Windows；macOS/Linux 用 source .venv/bin/activate
```

1. **改模型**：只在**自己模块**的 `models.py` 里增删表/字段，类型别名统一用 `app/core/mixins.py`
   提供的 `BigIntPk` / `BigIntFk` / `CodeStr` / `NameStr` / `StatusStr` / `Quantity` / `Money` / `Ratio`，
   时间戳与审计列继承 `TimestampMixin` / `AuditMixin`。命名规范见
   [`../database/data-dictionary.md`](../database/data-dictionary.md)。

2. **确认 `env.py` 能看见你的模型**：`migrations/env.py` 导入五个模块的 `models`；
   新增模型文件后要保证它被模块的 `models` 包导出。

3. **生成迁移**：

```bash
alembic revision --autogenerate -m "add xxx column to yyy table"
```

4. **人工审阅生成的脚本**（这一步不可省，见下节）。

5. **应用到本地库并验证**：

```bash
alembic upgrade head
```

6. **跑测试**：

```bash
pytest
```

7. **提交**（迁移文件与模型改动必须同一个 commit / 同一个 PR）：

```bash
git add backend/app/modules/<module>/models.py backend/migrations/versions/<新文件>.py
git commit -m "feat(<module>): add xxx field to yyy"
```

## 五、必须人工审阅的点

`alembic revision --autogenerate` **不是万能的**，生成后逐条检查：

| 检查项 | 原因 |
| --- | --- |
| 是否误删表/字段 | autogenerate 会为「模型里删掉但库里还在」的列生成 `drop_column`，误删不可逆 |
| `nullable` 是否符合预期 | 给已有数据的表加 `NOT NULL` 列会失败，需分两步（先 nullable 或给 server_default） |
| 类型是否正确 | 统一用 `Numeric(18,4)` 存数量、`Numeric(18,2)` 存金额、`Numeric(8,4)` 存比例；**不允许 FLOAT** |
| 索引与唯一约束 | 业务编码列（如 `*_code`、`*_no`）应有唯一约束；跨模块外键按约定只允许指向 `sys_material.id` |
| **CHECK 约束** | **MySQL 的 CHECK 约束不会被 autogenerate 检测**，必须像 `f5e52ee720d6` 那样手写 `op.create_check_constraint(...)` |
| `downgrade()` 是否可用 | 回退路径要能跑通，别只写 `pass` |

`f5e52ee720d6` 中真实存在的这一行就是典型例子：

```python
# MySQL 的 CHECK 约束不会被 autogenerate 检测，需显式补齐（规格 §22 约束）
op.create_check_constraint(
    'ck_sys_bom_item_lead_offset', 'sys_bom_item', 'lead_time_offset >= 0'
)
```

## 六、检查「模型与库是否漂移」

Alembic ≥ 1.9 提供 `check` 子命令（本仓库 `requirements.txt` 要求 `alembic>=1.14,<2.0`）：

```bash
cd backend
alembic check
```

- 输出 `No new upgrade operations detected.` → 模型与数据库一致。
- 输出待生成的 upgrade 操作 → 说明有模型改动**没有**配套迁移脚本，必须补一个迁移。

> 该命令需要连得上 `backend/.env` 里配置的 MySQL。

**约定：不要用「本地手改表 + 直接改模型」的方式绕过迁移。** 否则其他人的
`alembic upgrade head` 会与你的库不一致。

## 七、协作规则

1. 迁移文件在 `backend/migrations/versions/`，**必须提交**。
2. 迁移一旦推送到 `develop`，**其他人不得修改**；需要变更请**追加新迁移**。
3. 不要手工改别人的迁移文件；不要 `downgrade` + 改旧迁移后强推。
4. 不要提交本地数据库文件或导出的 `.sql`。
5. `alembic downgrade` 在共享环境上慎用，本地随意。
6. 一个 PR 内的模型改动与迁移文件必须成对出现 —— 只有模型没有迁移，Review 时直接打回。
7. 新增表前先确认 Owner 归属，见
   [`../architecture/module-ownership.md`](../architecture/module-ownership.md)。

## 八、常用命令速查

```bash
alembic revision --autogenerate -m "描述"   # 按模型差异生成迁移
alembic upgrade head                        # 应用全部迁移
alembic upgrade +1                          # 只应用下一个版本
alembic downgrade -1                        # 回退一个版本
alembic current                             # 当前库版本
alembic heads                               # 代码中的 head 版本
alembic history                             # 迁移历史
alembic check                               # 检测模型与库是否漂移
alembic show <revision>                      # 查看某个迁移的详情
```

## 九、当前未落地的事项

| 项 | 状态 |
| --- | --- |
| CI 中的自动漂移检查 | **无**：仓库没有 CI，`alembic check` 需要成员本地自觉执行 |
| 数据迁移（DML） | 现有两个迁移都是结构变更，**没有任何数据回填脚本** |
| 迁移回滚演练 | **未做**；`downgrade()` 只是按 Alembic 模板编写，未在真实库上验证过 |
| 多分支并行迁移（merge revision） | **未使用**；目前是单链 `9e6fa0de8416 → f5e52ee720d6` |