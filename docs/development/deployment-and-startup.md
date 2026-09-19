# 部署与启动

本文说明如何在**本地**把 BH-ERP 跑起来（后端 API + 前端页面 + MySQL）。

> 本文描述的是当前仓库的**真实状态**：52 张业务表、167 个接口路径（223 个操作）、
> 两条层叠的 Alembic 迁移。所有命令都经过实际执行核对。

## 一、环境要求

| 工具 | 版本 | 用途 | 是否必须 |
| --- | --- | --- | --- |
| Node.js | ≥ 18（推荐 20+） | 前端构建 | 跑前端才需要 |
| Python | ≥ 3.10 | 后端运行 | 必须 |
| MySQL | 8.x | 数据存储 | 只用健康检查可不装 |
| Git | 任意较新版本 | 版本管理 | 必须 |

```bash
node -v
npm -v
python --version
git --version
```

> 没有 MySQL 时后端**仍可启动**：`app.core.database` 的 `create_engine` 是惰性的，
> 启动过程不建立连接。因此 `/health` 与各模块 `/health` 都能正常返回。
> 但只要调用任何读写业务数据的接口，就会因连不上库而失败。

## 二、克隆仓库

```bash
git clone https://github.com/Asukayyy/MTS-ERP-system.git
cd MTS-ERP-system

git checkout develop
git pull origin develop
```

## 三、准备 MySQL

1. 启动本机 MySQL 8.x。
2. 建库（字符集必须是 `utf8mb4`）：

```sql
CREATE DATABASE bh_erp DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

3. 准备一个可用账号（示例用 `root`）。

> 库名 `bh_erp` 只是本仓库的**建议值**，实际以 `backend/.env` 的 `DB_NAME` 为准。

## 四、启动后端

```bash
cd backend

# 1) 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate              # Windows
# source .venv/bin/activate         # macOS / Linux

# 2) 安装依赖
pip install -r requirements.txt

# 3) 生成本地配置
copy .env.example .env              # Windows
# cp .env.example .env              # macOS / Linux

# 4) 打开 .env，按本机情况填写 DB_* 五项

# 5) 建表（见下节）

# 6) 启动
uvicorn app.main:app --reload --port 8000
```

### 4.1 环境变量清单

来源：`backend/.env.example` —— 实际读取入口是 `backend/app/core/config.py` 的 `settings`。

| 变量 | 示例值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `BH-ERP` | 应用名，出现在 `/health` 返回中 |
| `APP_VERSION` | `0.1.0` | 版本号 |
| `DEBUG` | `true` | 调试开关 |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 允许跨域的前端地址，英文逗号分隔 |
| `DB_HOST` | `127.0.0.1` | MySQL 主机 |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_NAME` | `bh_erp` | 数据库名 |
| `DB_USER` | `root` | 账号 |
| `DB_PASSWORD` | （空） | 密码，**只写本地 `.env`** |
| `DB_ECHO` | `false` | 是否打印 SQL |

连接串由 `settings.database_url` 拼接后交给 `app.core.database` 创建引擎，
**不写在代码里、也不写在 `alembic.ini` 里**。`backend/.env` 已被 `.gitignore` 忽略，
仓库中只有 `.env.example`。

### 4.2 建表与应用迁移

```bash
# 仍在 backend/ 目录，且虚拟环境已激活
alembic upgrade head
```

当前迁移链（`backend/migrations/versions/`）：

| 顺序 | revision | 说明 |
| --- | --- | --- |
| 1 | `9e6fa0de8416` | `baseline schema for five modules` —— 五模块基础表结构 |
| 2 | `f5e52ee720d6` | `add lead time offset, return quality status and replenishment target qty`（HEAD） |

细节见 [`database-migration-guide.md`](database-migration-guide.md)。

### 4.3 启动验证

| 地址 | 期望结果 |
| --- | --- |
| `http://127.0.0.1:8000/health` | `{"code":0,"message":"success","data":{"name":"BH-ERP","version":"0.1.0","status":"ok"}}` |
| `http://127.0.0.1:8000/api/v1/system/health` | `data` 为 `{"module":"system","status":"up"}` |
| `http://127.0.0.1:8000/api/v1/sales/health` | 同上，`module` 为 `sales` |
| `http://127.0.0.1:8000/docs` | Swagger UI |
| `http://127.0.0.1:8000/openapi.json` | OpenAPI schema（167 paths / 223 operations） |

五个模块的前缀分别是 `/api/v1/system`、`/api/v1/sales`、`/api/v1/planning`、
`/api/v1/procurement`、`/api/v1/inventory`（见 `app/main.py` 的 `include_router`）。

## 五、启动前端

**另开一个终端**：

```bash
cd frontend

npm install
copy .env.example .env              # Windows（macOS/Linux 用 cp）
npm run dev
```

访问 `http://127.0.0.1:5173`。

| 前端变量 | 值 | 说明 |
| --- | --- | --- |
| `VITE_APP_TITLE` | `BH-ERP` | 页面标题 |
| `VITE_API_BASE_URL` | `/api/v1` | 请求基础路径 |

`frontend/vite.config.ts` 已把 `/api` 代理到 `http://127.0.0.1:8000`（开发端口固定 `5173`），
所以**联调时后端必须跑在 8000 端口**，否则前端所有请求都会失败。

其他命令：

```bash
npm run type-check    # 只做 TypeScript 类型检查（vue-tsc --build）
npm run build         # 类型检查 + 生产构建
npm run preview       # 预览构建产物
```

## 六、运行测试

```bash
cd backend
pytest
```

| 项 | 值 |
| --- | --- |
| 配置 | `backend/pytest.ini`（`testpaths = tests`，`addopts = -q`） |
| 公共 fixture | `backend/tests/conftest.py` 提供 session 级 `TestClient` |
| 测试文件 | `tests/test_app_health.py`、`test_system.py`、`test_sales.py`、`test_planning.py`、`test_procurement.py`、`test_inventory.py`、`test_end_to_end_chair_mts.py`，以及各模块 `tests/<module>/test_health.py` |

选择性地跑：

```bash
pytest tests/test_planning.py
pytest tests/test_end_to_end_chair_mts.py -v
pytest -k "health"
```

> 只跑健康检查相关用例时**不需要 MySQL**（`conftest.py` 注释已说明）。
> 涉及业务数据的用例需要已建表并连得上数据库。

## 七、常见问题

**Q：后端报数据库连接错误？**
A：确认 MySQL 已启动、`bh_erp` 库已建、`.env` 的 `DB_*` 正确、并且已执行
`alembic upgrade head`。

**Q：接口报 `Table 'bh_erp.xxx' doesn't exist`？**
A：没执行迁移。在 `backend/` 下运行 `alembic upgrade head`。

**Q：`alembic revision --autogenerate` 生成的脚本是空的？**
A：说明模型与数据库已一致（无漂移），或 `migrations/env.py` 没有导入你新增的模型。
`env.py` 目前已导入五个模块的 `models`，新增模型文件后请确认它被该模块 `models/__init__.py`
或 `env.py` 引用。可用 `alembic check` 判断是否存在模型与库不一致。

**Q：前端页面能开，但接口全部 404 / 连接失败？**
A：后端没启动或不在 8000 端口；或 `VITE_API_BASE_URL` 被改坏（应为 `/api/v1`）。

**Q：`npm run build` 报 TypeScript 错误？**
A：先 `npm run type-check` 定位。`noUnusedLocals` 已开启，未使用的变量/导入会直接报错。

**Q：`.env` 会被提交吗？**
A：不会，已在 `.gitignore` 中。

## 八、当前未做的部署相关事项

| 项 | 状态 |
| --- | --- |
| 容器化（Docker / Compose） | **未引入**（课程规模不需要，见 CONTRIBUTING.md 第八节） |
| CI/CD 流水线 | **无**（仓库内没有 `.github/workflows`） |
| 生产环境部署脚本 / Nginx 配置 | **无**，当前只支持本地开发运行 |
| 鉴权与登录校验 | **未实现**：所有接口不校验 `Authorization`；`system/auth/login` 是简化版（见 [`../api/api-contract.md`](../api/api-contract.md) 第四节） |
| 生产级 WSGI/ASGI 进程管理 | **无**，只使用 `uvicorn --reload` 开发模式 |