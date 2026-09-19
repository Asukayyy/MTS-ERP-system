# 文档索引

| 目录 / 文件 | 内容 | 谁需要看 |
| --- | --- | --- |
| [acceptance-report.md](acceptance-report.md) | **最终验收报告**（A–H：仓库 / 架构 / 数据库 / 五模块 / 课程数据 / 集成测试 / 端到端 / 未完成项） | 验收与答辩，**优先看** |
| [development/getting-started.md](development/getting-started.md) | 环境要求、clone、安装依赖、启动前后端 | 所有人，**第一次必看** |
| [development/deployment-and-startup.md](development/deployment-and-startup.md) | 本地部署与启动、环境变量清单、验证命令、常见问题 | 所有人 |
| [development/database-migration-guide.md](development/database-migration-guide.md) | Alembic 工作流、迁移命名、漂移检查、禁止传 SQL 文件 | 需要建表的人 |
| [development/git-workflow.md](development/git-workflow.md) | 分支模型、Commit 规范、PR 流程的操作指南 | 所有人 |

| 目录 / 文件 | 内容 | 谁需要看 |
| --- | --- | --- |
| [architecture/system-architecture.md](architecture/system-architecture.md) | 分层架构、模块边界、Owner 原则、跨模块契约规则 | 所有人，**必读** |
| [architecture/module-ownership.md](architecture/module-ownership.md) | 52 张表的逐表归属矩阵 + 跨模块调用矩阵 | 所有人，**必读** |
| [architecture/module-boundaries.md](architecture/module-boundaries.md) | 模块边界、接口方向、禁止事项 | 所有人 |
| [architecture/data-ownership.md](architecture/data-ownership.md) | 数据表归属规划 | 所有人 |
| [architecture/system-overview.md](architecture/system-overview.md) | 系统目标、MTS 模式、五模块结构与业务闭环 | 所有人 |

| 目录 / 文件 | 内容 | 谁需要看 |
| --- | --- | --- |
| [api/api-contract.md](api/api-contract.md) | 统一响应/分页/错误码 + 167 个路径的接口清单 | 所有人 |
| [api/README.md](api/README.md) | 统一 API 前缀、响应结构、分页规范 | 所有人 |
| [database/physical-data-model.md](database/physical-data-model.md) | 物理数据模型：逐表逐字段（类型/可空/默认/键/约束/索引） | 需要建表或改表的人 |
| [database/full-er-diagram.md](database/full-er-diagram.md) | 全库 ER 图（52 实体 / 95 关系）+ 模块依赖图 | 所有人 |
| [database/data-dictionary.md](database/data-dictionary.md) | 命名规范、主外键规则、统一数据类型、枚举与状态机 | 所有人，**必读** |
| [database/system-er.md](database/system-er.md) | system 模块 ER 图 | system 负责人 |
| [database/sales-er.md](database/sales-er.md) | sales 模块 ER 图 | sales 负责人 |
| [database/planning-er.md](database/planning-er.md) | planning 模块 ER 图 | planning 负责人 |
| [database/procurement-er.md](database/procurement-er.md) | procurement 模块 ER 图 | procurement 负责人 |
| [database/inventory-er.md](database/inventory-er.md) | inventory 模块 ER 图 | inventory 负责人 |
| [database/README.md](database/README.md) | 数据库连接约定与建表流程 | 需要建表的人 |
| [user-guide/course-scenario-guide.md](user-guide/course-scenario-guide.md) | 转椅 MTS 主链路实操（导入 → MPS → MRP → 采购/生产 → 库存 → 发货 → 补货） | 演示与验收 |
| [planning/README.md](planning/README.md) | planning 模块的功能设计、DFD 与图表 | planning 负责人 |
| [requirements/BH-ERP-完整开发规格.md](requirements/BH-ERP-完整开发规格.md) | 课程开发规格（权威约束来源） | 所有人 |

根目录还有：

- [README.md](../README.md)：项目总览与快速启动
- [CONTRIBUTING.md](../CONTRIBUTING.md)：分支模型、Commit 规范、PR 流程（团队约定原文）

> 这些文档的目标是让新成员 5 分钟内知道：**项目怎么跑、自己改哪里、哪些目录不能乱改**。
> 请不要把它们写成几十页的说明书。