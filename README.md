# BH-ERP

基于 **转椅 BOM 与主生产计划（MPS）** 的 Web 版 **MTS（Make To Stock，面向库存生产）ERP 系统**。

> **当前状态：Foundation / Skeleton（基础工程框架）**
> 本仓库目前**只完成协作开发所需的基础工程框架**：目录结构、前后端可运行环境、数据库与迁移框架、统一 API 响应规范、协作规范文档。
> **具体 ERP 业务功能尚未实现**，五个业务模块只提供占位路由与占位页面（"功能开发中"）。
> 看到页面壳子不代表系统已开发完成。

---

## 一、系统业务目标

面向转椅制造场景，覆盖从**销售需求 → 计划 → 采购 / 生产 → 库存 → 发货**的完整闭环，
并让**实时库存状态反馈回计划与 MRP**，形成可循环的 MTS 生产计划体系。

验证载体：转椅产品的 **BOM（物料清单）** 与课程提供的 **附录 1 主生产计划（MPS）**。

最终业务闭环：

```
Sales（销售需求 / 销售订单）
   ↓
Planning（MPS → MRP → 生产作业计划 / 派工单 / 领料单）
   ↓
Procurement（采购订单 / 到货）  ‖  Production Execution（生产执行，归属 planning 模块）
   ↓
Inventory（入库 / 出库 / 结存）
   ↓
Shipment（销售发货）
   ↑
实时库存状态反馈回 Planning / MRP
```

---

## 二、五大业务模块

本系统**只有五个开发模块**，不设独立的 production 模块；生产相关功能（MPS、MRP、生产作业计划、派工单、领料单）全部归属 **planning**。

| 模块 | 目录前缀 | 职责 |
| --- | --- | --- |
| system | `/api/v1/system`、`/system` | 系统与基础信息管理：产品、物料、BOM、工艺路线、组织人员、基础字典、用户、角色、权限、操作日志 |
| sales | `/api/v1/sales`、`/sales` | 销售管理：客户、销售预测、销售订单、发货 |
| planning | `/api/v1/planning`、`/planning` | 计划管理：MPS、MRP、生产作业计划、派工单、领料单 |
| procurement | `/api/v1/procurement`、`/procurement` | 采购管理：供应商、采购计划、采购订单、到货 |
| inventory | `/api/v1/inventory`、`/inventory` | 库存管理：仓库、库位、出入库、移库、盘点、实时库存 |

每个模块的详细职责、输入输出与负责人占位见 `backend/app/modules/<module>/README.md`。

---

## 三、项目目录

```
BH-ERP/
├── frontend/                     # 前端工程（Vue 3 + Vite + TypeScript）
│   ├── src/
│   │   ├── api/                  # 按模块划分的接口层
│   │   │   ├── system/ sales/ planning/ procurement/ inventory/
│   │   ├── views/                # 按模块划分的页面
│   │   │   ├── dashboard/  error/
│   │   │   └── system/ sales/ planning/ procurement/ inventory/
│   │   ├── components/common/    # 跨模块公共组件
│   │   ├── layouts/              # 主布局、侧边栏、顶栏
│   │   ├── router/               # 路由表（/system、/sales、/planning、/procurement、/inventory）
│   │   ├── stores/               # Pinia 状态
│   │   ├── types/                # 公共 TypeScript 类型
│   │   └── utils/                # axios 实例等公共工具
│   ├── package.json  vite.config.ts  .env.example
│   └── README.md
│
├── backend/                      # 后端工程（FastAPI）
│   ├── app/
│   │   ├── main.py               # 应用入口，统一注册五个模块路由
│   │   ├── core/                 # config / database / security
│   │   ├── common/               # response / exceptions / pagination
│   │   ├── modules/              # 五个业务模块（router/schemas/models/service/repository）
│   │   │   ├── system/ sales/ planning/ procurement/ inventory/
│   │   └── shared/               # 跨模块共享枚举与类型
│   ├── migrations/               # Alembic 迁移
│   ├── tests/                    # 按模块划分的测试
│   ├── requirements.txt  alembic.ini  .env.example
│   └── README.md
│
├── docs/
│   ├── architecture/             # 系统概览、模块边界、数据所有权
│   ├── api/                      # 统一 API 与响应规范
│   ├── database/                 # 数据库与迁移约定
│   └── development/              # 新人上手
│
├── scripts/                      # 开发辅助脚本（预留）
├── .github/                      # PR / Issue 模板
├── LICENSE                       # 暂未创建（课程设计项目）
├── CONTRIBUTING.md               # 多人协作规范
└── README.md
```

---

## 四、技术架构

```
Browser
  ↓
Frontend  Vue 3 Web UI
  ↓  REST API
Backend   FastAPI
  ↓
Service Layer
  ↓
Repository / Data Access Layer
  ↓
MySQL（五个模块共享同一数据库，代码按模块隔离）
```

| 层 | 技术栈 |
| --- | --- |
| 前端 | Vue 3 · Vite · TypeScript · Pinia · Vue Router · Axios · Element Plus |
| 后端 | Python · FastAPI · SQLAlchemy 2.x · Pydantic v2 · Alembic |
| 数据库 | MySQL 8.x（字符集 utf8mb4） |

设计原则：前后端分离、模块内分层（router → service → repository）、模块之间低耦合。

---

## 五、快速启动

环境要求：Node.js ≥ 18、Python ≥ 3.10、MySQL 8.x（可选，缺失也能完成代码导入与配置检查）。

### 1. 后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt

# 复制环境变量模板（不要提交 .env）
cp .env.example .env        # Windows: copy .env.example .env

# 按需修改 .env 中的 DB_* 为本地 MySQL 连接信息

uvicorn app.main:app --reload --port 8000
```

- 接口文档：http://127.0.0.1:8000/docs
- 根健康检查：http://127.0.0.1:8000/health
- 模块健康检查：http://127.0.0.1:8000/api/v1/sales/health 等

### 2. 前端

```bash
cd frontend

npm install
cp .env.example .env        # Windows: copy .env.example .env

npm run dev                 # http://127.0.0.1:5173
npm run build               # 类型检查 + 生产构建
```

前端开发服务器已配置 `/api` 代理到 `http://127.0.0.1:8000`，无需额外处理跨域。

### 3. 更完整的上手说明

见 [docs/development/getting-started.md](docs/development/getting-started.md)。

---

## 六、开发规范入口

| 文档 | 内容 |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 分支模型、Commit 规范、PR 流程 |
| [docs/architecture/system-overview.md](docs/architecture/system-overview.md) | 系统总体设计与业务闭环 |
| [docs/architecture/module-boundaries.md](docs/architecture/module-boundaries.md) | 五个模块的边界与接口方向（**必读**） |
| [docs/architecture/data-ownership.md](docs/architecture/data-ownership.md) | 数据表归属规划（**必读**） |
| [docs/api/README.md](docs/api/README.md) | 统一 API 前缀与响应规范 |
| [docs/database/README.md](docs/database/README.md) | 数据库与 Alembic 迁移约定 |
| [docs/development/getting-started.md](docs/development/getting-started.md) | 环境搭建与启动 |

**五个人必读的两条硬性约束：**

1. 禁止一个模块直接 import 另一个模块的 `service` / `repository`，跨模块只能通过约定好的 Service / API Contract 通信。
2. 每张业务表必须有唯一的 Owner 模块，非 Owner 模块不得直接改表对应的业务代码。

---

## 七、Git 协作方式

```
main         只保存稳定版本（禁止长期直接提交）
  ↑ PR
develop      集成开发分支（默认集成分支）
  ↑ PR
feature/system  feature/sales  feature/planning  feature/procurement  feature/inventory
```

```bash
git checkout develop
git pull origin develop
git checkout -b feature/<module>

git add .
git commit -m "feat(<module>): ..."
git push origin feature/<module>
```

然后发起 Pull Request：`feature/<module>` → `develop`；集成测试通过后再 `develop` → `main`。

Commit 前缀：`feat` / `fix` / `docs` / `refactor` / `test` / `chore`。
详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 附录：早期前端交互原型（历史产物，与本次工程骨架无关）

仓库中 `智能制造大作业/prototype/` 是一份**纯前端交互原型**（React 18 + Ant Design 5 + ECharts 5 + Vite 5），
数据全部来自内置模拟数据（`src/mock/demoData.js`），**不依赖任何后端服务**，仅用于课设早期界面风格验证。

它**不是**本次协作开发的前后端工程骨架，后续业务开发请在 `frontend/` 与 `backend/` 中进行，原型目录保持只读参考。

### 直接体验原型（不需要装任何环境）

1. 点击仓库页面的绿色 **Code** 按钮 → **Download ZIP**
2. 解压到任意目录
3. 双击根目录的 `index.html`，浏览器会自动跳转（即 `智能制造大作业/prototype/dist/index.html`）

Windows / macOS / Linux 均可，不需要 Node.js、不需要联网、不需要启动服务。

> 注意：不要直接双击 `智能制造大作业/prototype/index.html`。它是源码入口，引用 `src/main.jsx`，需要 Vite 编译，
> 直接打开会因 CORS 拦截而白屏，属于预期现象。

### 修改原型源码（需要 Node.js 18+）

```bash
cd 智能制造大作业/prototype
npm install
npm run dev      # http://localhost:5173
npm run build    # 产物输出到 prototype/dist
```

原型打包为可双击运行的方式（`HashRouter` + `iife` 输出 + `base: './'`）见 `智能制造大作业/prototype/vite.config.js`。
