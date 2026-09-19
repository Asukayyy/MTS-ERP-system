# 系统总体设计

## 一、BH-ERP 的最终目标

BH-ERP 是一个 **Web B/S 架构**的制造企业资源计划系统，面向**转椅制造**场景，
采用 **MTS（Make To Stock，面向库存生产）** 生产模式：

> 企业根据对市场需求的预测与已有库存，**提前组织生产并入库**，客户订单到达后直接由库存发货。

因此系统的核心不是"接单后生产"，而是：**用计划驱动采购与生产，把成品提前备进仓库**。
这也决定了 **MPS 与 MRP 是整条业务链的发动机**。

## 二、验证对象

| 对象 | 说明 |
| --- | --- |
| 转椅 BOM | 系统的基础数据验证对象（成品 → 部件 → 零件 → 原材料的多层结构） |
| 附录 1 主生产计划（MPS） | 系统的计划输入验证对象（课程提供的 MPS 数据） |

> 课程原始数据已结构化保存到 `data/seed/course_chair_case.json`，
> 并可通过 **课程数据导入**接口写入系统：
> system 模块导入物料与 BOM，planning 模块导入附录 1 的 MPS，
> inventory 模块导入期初库存。导入采用「先预览、再确认」两段式。
> 实操步骤见 [../user-guide/course-scenario-guide.md](../user-guide/course-scenario-guide.md)。

## 三、五个模块

系统**只有五个开发模块**：

```
system        系统与基础信息管理   —— 提供全局基础数据与系统能力
sales         销售管理             —— 产生销售需求与销售订单
planning      计划管理             —— MPS / MRP / 生产作业计划（含生产执行）
procurement   采购管理             —— 采购订单与到货
inventory     库存管理             —— 实时库存状态
```

**不设独立的 production 模块。** 本课程中生产相关功能（MPS、MRP、生产作业计划、派工单、领料单）
全部归属 **planning** 模块。

## 四、业务闭环

```
                 ┌──────────────────────────────┐
                 │  实时库存状态（反馈）          │
                 └──────────────┬───────────────┘
                                │
Sales   ──销售需求/订单──▶  Planning  ──采购需求──▶  Procurement
（销售）                    （计划）                    （采购）
                                │                          │
                                │ 生产作业计划/派工单        │ 采购订单/到货
                                ▼                          ▼
                          Production Execution  ──▶   Inventory
                          （生产执行，归属 planning）    （库存）
                                                          │
                                                          ▼
                                                      Shipment
                                                     （销售发货）
```

正式链路：

```
Sales
  → Planning
  → Procurement / Production Execution
  → Inventory
  → Shipment
  → 库存状态反馈回 Planning / MRP
```

## 五、技术架构

```
Browser
  ↓
Frontend   Vue 3 Web UI        （frontend/）
  ↓  REST API  /api/v1
Backend    FastAPI             （backend/app/）
  ↓
Service Layer                  （modules/*/service.py）
  ↓
Repository / Data Access Layer （modules/*/repository.py）
  ↓
MySQL                          （五个模块共享同一个库，代码按模块隔离）
```

| 层 | 技术栈 |
| --- | --- |
| 前端 | Vue 3 · Vite · TypeScript · Pinia · Vue Router · Axios · Element Plus |
| 后端 | Python · FastAPI · SQLAlchemy 2.x · Pydantic v2 · Alembic |
| 数据库 | MySQL 8.x（utf8mb4） |

## 六、模块内分层

每个后端模块内部固定五层结构：

```
router.py       HTTP 层：定义路径、入参出参、调用 service、提交事务
schemas.py      Pydantic 模型：请求 / 响应结构
service.py      业务层：业务规则、状态机、跨模块编排（不 commit）
repository.py   数据访问层：SQL / ORM 查询
models.py       ORM 模型：表结构定义（五模块共 52 张表）
contract.py     跨模块契约：对外暴露的读写函数，返回纯 dict / 标量
```

调用方向**只允许自上而下**：

```
router  →  service  →  repository  →  MySQL
```

反向调用（repository 调 service、service 调 router）一律禁止。
跨模块调用**只能**走对方模块的 `contract.py`。

## 七、当前状态

系统主要业务功能**已实现**：

- 后端：**52 张业务表**、**167 个路径 / 223 个操作**、2 个 Alembic 迁移（HEAD `f5e52ee720d6`）
- 前端：**35 个模块页面**（路由表共 39 处 `path` 声明）
- 业务闭环：课程数据导入 → MPS → MRP → 采购 / 生产 → 入库 / 领料 / 完工 → 发货 / 退货 → 订货点补库

**已知简化项**：

- 未实现鉴权：所有接口不校验 `Authorization`，`system/auth/login` 为简化版登录
- 各模块 `/health` 为占位接口，固定返回 `{module, status:"up"}`
- 单号/编码生成为演示级实现，不是并发安全的正式编号器
- 无 CI、无容器化部署

各模块的开发顺序与依赖关系见 [module-boundaries.md](module-boundaries.md)，
完整架构与跨模块契约规则见 [system-architecture.md](system-architecture.md)。
