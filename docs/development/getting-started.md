# 新人上手指南

目标：**5 分钟内**把项目跑起来，并知道自己该改哪里。

## 一、环境要求

| 工具 | 版本 | 说明 |
| --- | --- | --- |
| Node.js | ≥ 18（推荐 20+） | 前端构建 |
| Python | ≥ 3.10（推荐 3.11/3.12） | 后端运行 |
| MySQL | 8.x | 必装；没有数据库时后端仍可启动并访问健康检查接口 |
| Git | 任意较新版本 | 版本管理 |

检查是否就绪：

```bash
node -v
npm -v
python --version
git --version
```

## 二、克隆与分支

```bash
git clone https://github.com/Asukayyy/MTS-ERP-system.git
cd MTS-ERP-system

git checkout develop
git pull origin develop

git checkout -b feature/<module>     # 换成你自己的模块：system/sales/planning/procurement/inventory
```

## 三、启动后端

```bash
cd backend

# 1. 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate              # Windows
# source .venv/bin/activate         # macOS / Linux

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
copy .env.example .env              # Windows
# cp .env.example .env              # macOS / Linux

# 4. 按本机情况修改 .env 中的 DB_* （必须先建好 bh_erp 库）
#    DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD

# 5. 启动
uvicorn app.main:app --reload --port 8000
```

验证：

| 地址 | 期望结果 |
| --- | --- |
| http://127.0.0.1:8000/health | `{"code":0,"message":"success","data":{"name":"BH-ERP",...}}` |
| http://127.0.0.1:8000/api/v1/sales/health | `{"code":0,"message":"success","data":{"module":"sales","status":"up"}}` |
| http://127.0.0.1:8000/docs | Swagger 文档 |

> 本机没有 MySQL 也能启动后端并访问上述接口，因为 `create_engine` 是惰性的，不会在启动时连接数据库。

跑测试：

```bash
cd backend
pytest
```

## 四、启动前端

**另开一个终端**：

```bash
cd frontend

npm install
copy .env.example .env              # Windows（macOS/Linux 用 cp）
npm run dev
```

访问 http://127.0.0.1:5173 ，应能看到主布局（顶栏 + 侧边栏 + 内容区），
侧边栏包含：工作台、系统与基础信息管理、销售管理、计划管理、采购管理、库存管理。

在工作台点击"调用五个模块的 health 接口"，若五个模块都返回 `up`，说明前后端联调打通。

> 前端开发服务器已把 `/api` 代理到 `http://127.0.0.1:8000`，不需要额外处理跨域。
> 因此**联调时后端必须跑在 8000 端口**。

其他命令：

```bash
npm run type-check    # 只做 TypeScript 类型检查
npm run build         # 类型检查 + 生产构建
```

## 五、你应该改哪里

假设你负责 **sales** 模块：

| 你该改的 | 你不该动的 |
| --- | --- |
| `backend/app/modules/sales/**` | 其他人的 `backend/app/modules/<别人>/**` |
| `backend/tests/sales/**` | 其他人的测试目录 |
| `frontend/src/api/sales/**` | `frontend/src/api/<别人>/**` |
| `frontend/src/views/sales/**` | `frontend/src/views/<别人>/**` |
| `frontend/src/router/routes.ts` 中 **sales 节点内部** | 别人的路由节点 |
| `frontend/src/layouts/menu.ts` 中 **sales 条目内部** | 别人的菜单条目 |
| 你自己模块的迁移文件 | 别人的迁移文件、已推送的迁移文件 |

公共层（改之前先在群里说一声）：

```
backend/app/core/**  backend/app/common/**  backend/app/shared/**
backend/app/main.py  backend/alembic.ini    backend/migrations/env.py
frontend/src/utils/**  frontend/src/types/**  frontend/src/components/common/**
frontend/src/layouts/**  frontend/src/router/**  frontend/src/stores/index.ts
frontend/vite.config.ts  frontend/tsconfig*.json  frontend/package.json
```

## 六、动手前必读

| 文档 | 为什么 |
| --- | --- |
| [../architecture/module-boundaries.md](../architecture/module-boundaries.md) | 搞清楚模块边界，别 import 别人的 service/repository |
| [../architecture/data-ownership.md](../architecture/data-ownership.md) | 搞清楚哪张表归你，别乱建表 |
| [../api/README.md](../api/README.md) | 统一响应、分页、错误码规范 |
| [../../CONTRIBUTING.md](../../CONTRIBUTING.md) | 分支、Commit、PR 流程 |

## 七、常见问题

**Q：后端启动报数据库连接错误？**
A：确认 MySQL 已启动、`bh_erp` 库已创建、`.env` 中 `DB_*` 正确。
注意本阶段还没有任何业务表，不需要执行迁移。

**Q：前端页面能看到，但点"调用 health 接口"报错？**
A：后端没启动，或没跑在 8000 端口。前端 proxy 固定指向 `http://127.0.0.1:8000`。

**Q：`npm run build` 报 TypeScript 错误？**
A：先跑 `npm run type-check` 定位具体文件。请确保没有未使用的变量/导入（`noUnusedLocals` 已开启）。

**Q：`alembic revision --autogenerate` 没生成任何内容？**
A：正常。当前 `Base.metadata` 里还没有业务表。

**Q：我改的 `.env` 会不会被提交？**
A：不会。`.env` 已在 `.gitignore` 中；仓库里只有 `.env.example`。
