# 贡献指南（CONTRIBUTING）

BH-ERP 是五人协作的课程设计项目。为减少互相覆盖与集成冲突，请严格遵守以下约定。

---

## 一、分支模型

```
main         只保存可演示的稳定版本，禁止长期直接提交
  ↑ Pull Request（集成测试通过后）
develop      集成开发分支，所有人的功能最终汇总到这里
  ↑ Pull Request
feature/system / feature/sales / feature/planning / feature/procurement / feature/inventory
```

| 分支 | 用途 | 允许谁提交 |
| --- | --- | --- |
| `main` | 稳定版本、演示版本 | 仅通过 `develop` → `main` 的 PR |
| `develop` | 集成开发 | 仅通过 `feature/*` → `develop` 的 PR |
| `feature/<module>` | 个人模块开发 | 对应模块负责人，可自由提交 |

**禁止五个人长期直接向 `main` 提交。**

`release/*`、`hotfix/*` 等分支在本课程设计规模下**不需要**，请勿自行引入。

---

## 二、开始开发（新成员第一次操作）

```bash
git clone https://github.com/Asukayyy/MTS-ERP-system.git
cd MTS-ERP-system

git checkout develop
git pull origin develop

git checkout -b feature/<module>       # <module> ∈ system / sales / planning / procurement / inventory
```

例如负责销售模块：

```bash
git checkout -b feature/sales
```

> 本地基础框架已包含 `develop` 分支。请**不要**自行创建别人的 `feature/*` 远程分支，每人只创建自己那一条。

---

## 三、日常提交

```bash
git add .
git commit -m "feat(sales): add sales order query"
git push origin feature/sales
```

### 提交前自检

1. 只修改自己模块目录内的文件（`backend/app/modules/<module>/`、`frontend/src/{api,views}/<module>/`、`backend/tests/<module>/`）。
2. 如需修改**公共层**（`backend/app/core`、`backend/app/common`、`backend/app/shared`、`frontend/src/utils`、`frontend/src/components/common`、根配置文件、迁移文件），
   **必须先与组内沟通**，因为会影响其他四人。
3. 不要提交 `.env`、真实密码、`node_modules/`、`.venv/`、`__pycache__/`、构建产物、数据库文件。
4. 本地至少保证自己的模块能被 import / 编译通过。

---

## 四、Pull Request 流程

```
feature/<module>  →  develop      （开发阶段，随时可提）
develop           →  main         （集成测试通过后）
```

PR 要求：

1. 标题与 Commit 风格一致，例如 `feat(planning): implement MRP calculation`。
2. 描述中填写 `.github/pull_request_template.md` 模板内容：做了什么、影响范围、如何验证。
3. 至少 **1 名**其他成员 Review 后才能合并。
4. 合并前先 `git pull origin develop` 并解决冲突（**在自己分支上解决**，不要在 `develop` 上直接解冲突）。
5. 合并方式统一使用 **Squash merge** 或 **Merge commit** 任选其一，但全组保持一致；**不要**使用 Rebase 后强推。

---

## 五、Commit Message 规范

格式：

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

`scope` 建议为模块名或公共层名：`system` / `sales` / `planning` / `procurement` / `inventory` / `api` / `db` / `docs`。

示例：

```
feat(sales): add sales order query
feat(planning): implement MRP calculation
fix(inventory): correct stock balance update
docs(api): add procurement API specification
chore(deps): upgrade fastapi to 0.115
```

要求：

- 使用**祈使句**、英文小写开头（示例风格统一即可）。
- 一次 Commit 只做一件事，不要把格式化与功能混在一起。
- 禁止 `update`、`修改`、`111` 这类无信息量的描述。

---

## 六、模块隔离铁律

1. **禁止**一个模块直接 import 另一个模块的 `service.py` / `repository.py` / `models.py`。
   跨模块通信必须通过已约定的 Service / API Contract（见 `docs/architecture/module-boundaries.md`）。
2. **禁止**非 Owner 模块直接改别人模块的业务表与对应业务代码（见 `docs/architecture/data-ownership.md`）。
3. 允许所有模块 import 的公共内容：
   - 后端：`app.core.*`、`app.common.*`、`app.shared.*`
   - 前端：`@/utils/*`、`@/types/*`、`@/components/common/*`、`@/stores/*`、`@/layouts/*`
4. 新增公共能力前先问一句：**这是不是只有我这个模块用？** 只有自己用就放在自己模块目录内。

---

## 七、数据库与迁移

1. 建表前先确认这张表的 Owner 模块是不是你。
2. 迁移文件在 `backend/migrations/versions/`，由 `alembic revision --autogenerate -m "..."` 生成。
3. 迁移文件一旦被推送到 `develop`，**其他人不得修改**，需要变更请追加新迁移。
4. 不要手工改别人的迁移文件；不要提交本地数据库文件。

详见 `docs/database/README.md`。

---

## 八、不要做的事

1. 不要引入当前不需要的基础设施：Docker、Kubernetes、消息队列、Redis。
2. 不要引入课程任务之外的功能模块（财务、人力资源、质量、设备等）。
3. 不要为了"看起来完整"提前实现别人负责的模块。
4. 不要提交生成文件、缓存、运行产物、IDE 配置。
5. 不要对 `main` / `develop` 强推（`push --force`）。
