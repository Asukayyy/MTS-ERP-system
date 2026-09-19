# BH-ERP

基于 **转椅 BOM 与主生产计划（MPS）** 的 Web 版 **MTS（Make To Stock，面向库存生产）ERP 系统**。

> 课程设计项目（制造管理信息系统专业课设计），五人协作，五个业务模块。
> 数据来源为课程原始文件：`data/reference/BOM例子.doc`（案例 2：某办公家具生产企业 —— 转椅 BOM）
> 与 `data/reference/附录1：主生产计划.xls`。

---

## 一、系统是什么

面向转椅制造场景，覆盖从**销售需求 → 计划 → 采购 / 生产 → 库存 → 发货**的完整闭环，
并让**实时库存状态反馈回计划与 MRP**，形成可循环的 MTS 生产计划体系。

```
Sales（销售预测 / 销售订单）
   ↓
Planning（需求 → MPS → MRP → 生产作业计划 / 派工单 / 领料单 / 完工报告）
   ↓
Procurement（采购计划 / 采购订单 / 到货）  ‖  Production（生产执行，归属 planning 模块）
   ↓
Inventory（入库 / 出库 / 移库 / 盘点 / 结存）
   ↓
Shipment（销售发货 / 退货）
   ↑
订货点 → 补库需求 → 反馈回 Planning / Procurement
```

**核心算法**（planning 模块，`service.py`）：

```
净需求 = max( 毛需求 + 安全库存 − 可用库存 , 0 )
子件毛需求 = 父件净需求 × 单位用量 × (1 + 报废率)
子件需求日期 = 父件需求日期 − 提前期偏置
下达日期   = 需求日期 − 采购/生产提前期
按 supply_type 分流为 MAKE（自制）/ BUY（采购）
```

---

## 二、当前状态

系统的主要业务功能**已经实现并可通过接口与前端页面使用**：

| 指标 | 实际数量 | 核对方式 |
| --- | --- | --- |
| 业务表 | **52 张**（system 15 / sales 8 / planning 10 / procurement 9 / inventory 10） | `docs/database/physical-data-model.md` |
| 字段总数 | **640** | 同上 |
| 外键 / CHECK 约束 | **95 / 93** | 同上 |
| 接口路径 / 操作 | **167 / 223** | `GET /openapi.json`，见 `docs/api/api-contract.md` |
| 前端路由声明 | **42**（登录 1、布局根 1、404 1、工作台 1、模块页面 38） | `frontend/src/router/routes.ts` |
| Alembic 迁移 | **2 个**，HEAD = `f5e52ee720d6` | `alembic history` |
| 前端页面 | 38 个模块页面（全部为真实业务页面） | 侧边栏菜单 |
| 前端 API 路径 | 156 条模板，与后端 166 条模块路径比对**零不匹配** | 见 [`docs/acceptance-report.md`](docs/acceptance-report.md) B.5 节 |

**已知简化项**（详见 [`docs/api/api-contract.md`](docs/api/api-contract.md) 第四节与
[`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md) 第十节）：

| 项 | 现状 |
| --- | --- |
| 登录与鉴权 | **未实现权限校验**：`core/security.py` 只有占位 `HTTPBearer`，所有接口不校验 `Authorization`；`system/auth/login` 是简化版登录 |
| 各模块 `/health` | 占位接口，固定返回 `{module, status:"up"}`，不反映真实依赖状态 |
| 单号/编码生成 | 演示级（如 `SO` + 日期 + 4 位计数），**不是**并发安全的正式编号器 |
| 基础数据删除 | 以「停用」代替物理删除；被引用的数据删除会返回 `1009` / `5007` |
| CI / 容器化 | 无 CI、无 Docker；只有本地开发运行方式 |
| 前端的早期原型 | README 曾提到的 `智能制造大作业/prototype/` **已不在仓库中**（目录与 git 记录均不存在） |

---

## 三、五大业务模块

本系统**只有五个开发模块**，不设独立的 production 模块；
生产相关功能（MPS、MRP、生产作业计划、派工单、领料单、完工报告）全部归属 **planning**。

| 模块 | 路由前缀 | 表前缀 | 职责 |
| --- | --- | --- | --- |
| system | `/api/v1/system` | `sys_` | 基础信息：组织、人员、用户、角色、权限、字典、物料、BOM、工艺路线、操作日志、课程数据导入 |
| sales | `/api/v1/sales` | `sal_` | 客户、销售预测、销售订单、发货、退货 |
| planning | `/api/v1/planning` | `pln_` | 需求、MPS、MRP、生产作业计划、派工单、领料单、完工报告 |
| procurement | `/api/v1/procurement` | `pur_` | 供应商、供应商-物料、采购计划、采购订单、到货、供应商评价 |
| inventory | `/api/v1/inventory` | `inv_` | 仓库、库位、库存余额、库存流水、订货点、补库需求、移库、盘点 |

模块边界与 Owner 原则见 [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md)
与 [`docs/architecture/module-ownership.md`](docs/architecture/module-ownership.md)。

---

## 四、项目目录

```
MTS ERP system/
├── frontend/                     # 前端（Vue 3 + Vite + TypeScript）
│   ├── src/
│   │   ├── api/                  # 按模块划分的接口层 system/ sales/ planning/ procurement/ inventory/
│   │   ├── views/                # 按模块划分的页面（共 38 个模块页面）
│   │   ├── components/common/    # 跨模块公共组件
│   │   ├── layouts/              # 主布局、侧边栏（menu.ts）、顶栏
│   │   ├── router/               # 路由表 routes.ts
│   │   ├── stores/  types/  utils/
│   └── package.json  vite.config.ts  .env.example  README.md
│
├── backend/                      # 后端（FastAPI）
│   ├── app/
│   │   ├── main.py               # create_app()，注册五个模块路由
│   │   ├── core/                 # config / database / security / mixins
│   │   ├── common/               # response / exceptions / pagination
│   │   ├── modules/<module>/     # router / schemas / models / service / repository / contract
│   │   └── shared/               # 跨模块共享枚举与类型
│   ├── migrations/versions/      # Alembic 迁移（2 个）
│   ├── tests/                    # 测试（按模块 + 端到端）
│   ├── requirements.txt  alembic.ini  pytest.ini  .env.example  README.md
│
├── data/
│   ├── reference/                # 课程原始文件（BOM例子.doc、附录1：主生产计划.xls）
│   └── seed/course_chair_case.json  # 结构化后的课程案例数据（含 provenance）
│
├── docs/                         # 全套文档（见第七节）
├── tools/                        # 课程 BOM 提取/渲染脚本
├── scripts/                      # 开发辅助脚本（预留）
├── .github/                      # PR 模板 + Issue 模板（无 workflows）
├── CONTRIBUTING.md               # 多人协作规范
└── README.md
```

---

## 五、技术栈与分层

```
Browser
  ↓
Frontend  Vue 3 Web UI（Element Plus）
  ↓  REST API（统一前缀 /api/v1）
Backend   FastAPI
  ↓
Router → Service → Repository
  ↓
MySQL 8.x（五个模块共享同一数据库，代码按模块隔离）
```

| 层 | 技术栈 |
| --- | --- |
| 前端 | Vue 3 · Vite · TypeScript · Pinia · Vue Router · Axios · Element Plus |
| 后端 | Python ≥3.10 · FastAPI · Pydantic v2 · SQLAlchemy 2.x · Alembic · PyMySQL |
| 数据库 | MySQL 8.x（`utf8mb4` / `utf8mb4_unicode_ci`） |
| 测试 | pytest · httpx · FastAPI TestClient |

模块内分层固定为 `router.py` → `service.py` → `repository.py` → `models.py`，
另有 `schemas.py`（出入参）与 `contract.py`（跨模块契约）：

| 层 | 只做 | 不做 |
| --- | --- | --- |
| `router.py` | 定义路径、注入依赖、**提交事务** | 不写业务规则 |
| `service.py` | 业务规则、状态机、跨模块编排 | **不 `db.commit()`**、不写 SQL |
| `repository.py` | 只写 SQL / ORM 查询 | 不含业务规则 |
| `contract.py` | 对外暴露的读写函数（返回纯 dict / 标量） | 不返回 ORM 对象 |

统一响应信封 `{code, message, data}`（`code=0` 成功），分页固定
`{page, page_size, total, items}`（默认 `page=1`、`page_size=20`，上限 200）。

---

## 六、本地启动

环境要求：**Node.js ≥ 18**、**Python ≥ 3.10**、**MySQL 8.x**。

### 1. 后端

```bash
cd backend

python -m venv .venv
.venv\Scripts\activate              # Windows
# source .venv/bin/activate         # macOS / Linux

pip install -r requirements.txt
copy .env.example .env              # Windows（macOS/Linux 用 cp）
```

编辑 `backend/.env`：

```ini
APP_NAME=BH-ERP
APP_VERSION=0.1.0
DEBUG=true
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=bh_erp
DB_USER=root
DB_PASSWORD=你的本地密码
DB_ECHO=false
```

建库（MySQL 8.x，字符集必须 utf8mb4）：

```sql
CREATE DATABASE bh_erp DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

建表并启动：

```bash
alembic upgrade head                 # 应用全部迁移
uvicorn app.main:app --reload --port 8000
```

| 地址 | 说明 |
| --- | --- |
| http://127.0.0.1:8000/health | 应用健康检查 |
| http://127.0.0.1:8000/api/v1/system/health | 模块健康检查（sales / planning / procurement / inventory 同理） |
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000/openapi.json | OpenAPI schema |

> `create_engine` 是惰性的：**没有 MySQL 也能启动后端**并访问健康检查接口，
> 但任何读写业务数据的接口都会失败。

### 2. 前端

```bash
cd frontend
npm install
copy .env.example .env              # Windows（macOS/Linux 用 cp）
npm run dev                         # http://127.0.0.1:5173
```

`vite.config.ts` 已把 `/api` 代理到 `http://127.0.0.1:8000`，
**联调时后端必须跑在 8000 端口**。

```bash
npm run type-check    # vue-tsc --build
npm run build         # 类型检查 + 生产构建
npm run preview
```

### 3. 跑测试

```bash
cd backend
pytest
pytest tests/test_end_to_end_chair_mts.py -v      # 转椅 MTS 端到端场景
```

更详细的启动说明、环境变量清单与常见问题见
[`docs/development/deployment-and-startup.md`](docs/development/deployment-and-startup.md)。

### 4. 快速体验课程案例

按 [`docs/user-guide/course-scenario-guide.md`](docs/user-guide/course-scenario-guide.md)
走一遍完整主链路（导入课程数据 → MPS → MRP → 采购/生产 → 入库/领料/完工 → 发货/退货 → 补货）。

---

## 七、文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/README.md](docs/README.md) | 文档总索引 |
| [docs/acceptance-report.md](docs/acceptance-report.md) | **最终验收报告**（仓库 / 架构 / 数据库 / 五模块 / 课程数据 / 集成测试 / 端到端 / 未完成项） |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 分支模型、Commit 规范、PR 流程（**必读**） |
| [docs/architecture/system-architecture.md](docs/architecture/system-architecture.md) | 分层架构、模块边界、Owner 原则、跨模块契约规则 |
| [docs/architecture/module-ownership.md](docs/architecture/module-ownership.md) | 52 张表的逐表归属矩阵 + 跨模块调用矩阵（**必读**） |
| [docs/architecture/module-boundaries.md](docs/architecture/module-boundaries.md) | 模块边界与接口方向 |
| [docs/architecture/data-ownership.md](docs/architecture/data-ownership.md) | 数据表归属规划 |
| [docs/architecture/system-overview.md](docs/architecture/system-overview.md) | 系统总体设计与业务闭环 |
| [docs/database/full-er-diagram.md](docs/database/full-er-diagram.md) | 全库 ER 图（52 实体 / 95 关系）+ 各模块 ER 图 |
| [docs/database/physical-data-model.md](docs/database/physical-data-model.md) | 物理数据模型：逐表逐字段（类型/可空/默认/键/约束/索引） |
| [docs/database/data-dictionary.md](docs/database/data-dictionary.md) | 命名规范、主外键规则、统一数据类型、枚举与状态机 |
| `docs/database/{system,sales,planning,procurement,inventory}-er.md` | 各模块 ER 图 |
| [docs/api/api-contract.md](docs/api/api-contract.md) | 统一响应/分页/错误码 + 167 个路径的接口清单 |
| [docs/development/deployment-and-startup.md](docs/development/deployment-and-startup.md) | 本地部署与启动、环境变量、验证命令 |
| [docs/development/database-migration-guide.md](docs/development/database-migration-guide.md) | Alembic 工作流、迁移命名、漂移检查 |
| [docs/development/git-workflow.md](docs/development/git-workflow.md) | 分支模型与 PR 流程的操作指南 |
| [docs/development/getting-started.md](docs/development/getting-started.md) | 新人上手 |
| [docs/user-guide/course-scenario-guide.md](docs/user-guide/course-scenario-guide.md) | 转椅 MTS 场景实操指南 |
| [docs/database/README.md](docs/database/README.md) | 数据库连接与迁移约定 |
| `docs/planning/` | planning 模块的功能设计与图表 |
| `docs/requirements/BH-ERP-完整开发规格.md` | 课程开发规格（权威约束来源） |

---

## 八、协作规则

### 分支模型

```
main         只存稳定/可演示版本，禁止直接提交
  ↑ PR（五模块集成测试通过后）
develop      日常集成分支
  ↑ PR
feature/system  feature/sales  feature/planning  feature/procurement  feature/inventory
```

> 当前远程已存在的 `feature/*` 分支只有 `feature/planning`，其余四条由模块负责人自行创建。

### Commit 规范

```
<type>(<scope>): <subject>
```

`type` ∈ `feat` / `fix` / `docs` / `refactor` / `test` / `chore`；
`scope` 为模块名或公共层名（`system` / `sales` / `planning` / `procurement` / `inventory` / `api` / `db` / `docs`）。

```
feat(planning): implement multi-level MRP explosion
feat(inventory): add production replenishment request
feat(sales): add customer return workflow
feat(system): support BOM lead time offset
test(integration): add chair MTS end-to-end scenario
```

### 三条硬性约束

1. **禁止**一个模块直接 import 另一个模块的 `service.py` / `repository.py` / `models.py`；
   跨模块只能调用对方的 **`contract.py`**。
2. 每张业务表有且只有一个 **Owner 模块**，非 Owner 不得写该表（写操作只能通过 Owner 的契约函数）。
3. 库表结构只通过 **Alembic 迁移**演进，**禁止**用群里传 `final.sql` 的方式同步结构。

详见 [CONTRIBUTING.md](CONTRIBUTING.md) 与
[`docs/development/git-workflow.md`](docs/development/git-workflow.md)。

---

## 九、课程数据说明

课程原始文件只提供**物料名称与数量关系**，以及 **MPS / 期初库存数字**；
物料编码、提前期、安全库存、计量单位均为**系统默认值**。

| 数据 | 来源 | 是否课程原始 |
| --- | --- | --- |
| 转椅 BOM 名称与数量（3 层 / 5 半成品 / 23 采购件 / 29 节点） | `data/reference/BOM例子.doc` 案例 2 | 是 |
| MPS：年计划 120000、期初 30000、期末 18000、1~12 月各 10000 | `data/reference/附录1：主生产计划.xls` | 是 |
| 期初库存：成品 30000、各级物料 3000 | 附录 1 | 是 |
| 物料编码 `FG-1001` / `SF-2001..2005` / `RM-3001..3023` | 系统自定义方案 | 否 |
| 提前期（成品 5 天、半成品 3 天）、安全库存（1000 / 300）、单位 `PCS` | 系统默认 | 否 |

对应关系逐条记录在 `data/seed/course_chair_case.json` 的 `provenance` 字段中，可自行核对。
导入后课程数据即成为普通业务数据，可自由修改。