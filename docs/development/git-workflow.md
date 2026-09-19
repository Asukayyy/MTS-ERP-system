# Git 协作规范

BH-ERP 是五人协作的课程设计项目。本文规定**分支模型、提交规范、PR 流程**，
目的是让五个模块能并行开发而不互相覆盖。

> 本文与仓库根目录的 [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) 内容一致，
> 后者是必须遵守的约定；本文补充了当前仓库的**真实分支状态**与操作示例。

## 一、分支模型

```
main         只存稳定/可演示版本，禁止直接提交
  ↑ Pull Request（五模块集成测试通过后）
develop      日常集成分支
  ↑ Pull Request
feature/system  feature/sales  feature/planning  feature/procurement  feature/inventory
```

| 分支 | 用途 | 允许谁提交 | 来源 |
| --- | --- | --- | --- |
| `main` | 稳定版本、演示版本 | 仅通过 `develop` → `main` 的 PR | `origin/main` |
| `develop` | 集成开发 | 仅通过 `feature/*` → `develop` 的 PR | `origin/develop` |
| `feature/<module>` | 个人模块开发 | 对应模块负责人，可自由提交 | 每人一条 |

`<module>` 只能是：`system` / `sales` / `planning` / `procurement` / `inventory`。

**当前仓库实际存在的分支**（`git branch -a` 实测）：

| 分支 | 本地 | 远程 |
| --- | --- | --- |
| `main` | 有 | `origin/main`（`origin/HEAD`） |
| `develop` | 有 | `origin/develop` |
| `feature/planning` | 有（当前所在分支） | `origin/feature/planning` |

即：分支模型已按上表落地，五个 `feature/*` 分支中**目前只建立了 `feature/planning`**，
其余四条由对应模块负责人在开工时自行创建。

### 禁止事项（规格 §46）

- **不要** `git push --force`（强推）。
- **不要**重写别人的历史、不要删除其他成员的有效 commit。
- **不要**五个人长期直接向 `main` 提交。
- **不要**自行引入 `release/*`、`hotfix/*`、`git-flow` 等分支 —— 课程规模不需要。
- 冲突时：先 `pull` / `rebase` 或 `merge`，**人工解决**，不要用强推覆盖。

## 二、第一次上手

```bash
git clone https://github.com/Asukayyy/MTS-ERP-system.git
cd MTS-ERP-system

git checkout develop
git pull origin develop

git checkout -b feature/<module>       # 例如：git checkout -b feature/sales
```

> 只创建**自己**那一条 `feature/*` 远程分支，不要替别人建。

## 三、日常开发流程

```
develop → feature/<module> → commit → push → PR → develop
```

```bash
git status
git add backend/app/modules/sales/ frontend/src/views/sales/
git commit -m "feat(sales): add customer return workflow"
git push origin feature/sales
```

### 提交前自检

1. 只改自己模块目录内的文件：
   - 后端 `backend/app/modules/<module>/`、`backend/tests/<module>/`
   - 前端 `frontend/src/api/<module>/`、`frontend/src/views/<module>/`
2. 改**公共层**前先在群里说一声：`backend/app/core`、`backend/app/common`、
   `backend/app/shared`、`app/main.py`、`alembic.ini`、`migrations/env.py`，
   以及前端的 `utils` / `types` / `components/common` / `layouts` / `router` /
   `stores` / 根配置文件。
3. 不要提交 `.env`、真实密码、`node_modules/`、`.venv/`、`__pycache__/`、
   构建产物、数据库文件（`.gitignore` 已覆盖）。
4. 本地至少保证自己的模块能被 import / 编译通过。
5. 有 schema 变化时，**模型与迁移文件必须成对提交**（见
   [`database-migration-guide.md`](database-migration-guide.md)）。
6. 遵守模块隔离铁律：不跨模块 import 别人的 `service.py` / `repository.py` / `models.py`，
   跨模块只走对方 `contract.py`（见
   [`../architecture/system-architecture.md`](../architecture/system-architecture.md)）。

### 模块化提交（规格 §45）

即使当前只有一个人在全量建设，也要**保持模块化 Commit，不要一个 Commit 完成整个系统**：

```
feat(system): implement material and BOM management
feat(inventory): implement inventory balance and ledger
feat(sales): implement order shipment and return
feat(planning): implement MPS and MRP workflow
feat(procurement): implement purchasing workflow
test(integration): add chair MTS end-to-end scenario
```

这样后续五名成员仍可分别接管各自模块。

## 四、Commit Message 规范

格式（规格 §33）：

```
<type>(<scope>): <subject>
```

| type | 含义 |
| --- | --- |
| `feat` | 新增功能 |
| `fix` | 修复问题 |
| `docs` | 文档 |
| `refactor` | 重构（不改变外部行为） |
| `test` | 测试 |
| `chore` | 工程配置、依赖、构建 |

`scope` 用模块名或公共层名：`system` / `sales` / `planning` / `procurement` /
`inventory` / `api` / `db` / `docs` / `core`。

示例（与本仓库已有提交风格一致）：

```
feat(sales): add sales order query
feat(planning): implement multi-level MRP explosion
feat(inventory): add production replenishment request
feat(system): support BOM lead time offset
fix(inventory): correct stock balance update
docs(api): add procurement API specification
chore(core): freeze shared ORM conventions and cross-module enums
```

要求：

- 使用**祈使句**，小写开头。
- 一次 Commit 只做一件事，不要把格式化与功能混在一起。
- 禁止 `update`、`修改`、`111` 这类无信息量的描述。

## 五、Pull Request 流程

```
feature/<module>  →  develop      （开发阶段，随时可提）
develop           →  main         （五模块集成测试通过后）
```

PR 要求：

1. 标题与 Commit 风格一致，例如 `feat(planning): implement MRP calculation`。
2. 描述填写 `.github/pull_request_template.md` 模板的内容（仓库中该模板已存在），
   写清楚：**做了什么、影响范围、如何验证**。
3. 至少 **1 名**其他成员 Review 后才能合并。
4. 合并前先 `git pull origin develop`，**在自己的分支上**解决冲突，
   不要在 `develop` 上直接解冲突。
5. 合并方式全组统一（Squash merge 或 Merge commit 二选一），
   **不要** Rebase 后强推。
6. 涉及迁移文件、公共层、`data-ownership` 相关文档的 PR，要额外说明影响面。

## 六、常见场景

**A. 同步最新 `develop` 到自己的分支**

```bash
git checkout develop
git pull origin develop
git checkout feature/sales
git merge develop          # 或 git rebase develop（提交历史干净时）
# 解决冲突 → git add <文件> → git commit
```

**B. 提交后发现写错了信息**

追加一个新 commit（不要 `--amend` 已推送的提交，更不要强推）：

```bash
git commit -m "fix(sales): correct order status transition"
```

**C. 误把 `.env` 加入暂存区**

```bash
git restore --staged backend/.env
```

`.env` 已在 `.gitignore` 中，不会真的入库。

**D. 查看自己改了什么**

```bash
git status
git diff
git log --oneline -10
```

## 七、当前未落地的事项

| 项 | 状态 |
| --- | --- |
| 分支保护规则（Branch protection） | **未配置**，全靠约定与 Review |
| CI 状态检查 | **无**（`.github/` 下只有 `pull_request_template.md` 与 `ISSUE_TEMPLATE/`，没有 `workflows/`），PR 不会自动跑测试 |
| PR 模板 | 已有：`.github/pull_request_template.md`；Issue 模板：`.github/ISSUE_TEMPLATE/` |
| 代码所有者（CODEOWNERS） | **无** |
| Commit 信息自动校验（如 commitlint） | **无**，格式靠人工 Review |