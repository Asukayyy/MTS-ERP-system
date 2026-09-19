# Planning Module 设计文档

计划管理（planning）模块的课程设计文档目录。

## 文档索引

| 文档 | 内容 | 状态 |
| --- | --- | --- |
| [week2-functional-design.md](week2-functional-design.md) | 第 2 周：软件功能初步设计（模块定位、核心业务逻辑、输入-处理-输出、页面规划、技术选型） | 已完成 |
| [diagrams/planning-function-tree.md](diagrams/planning-function-tree.md) | 功能树（Mermaid，可渲染） | 已完成 |
| [diagrams/planning-level1-dfd.md](diagrams/planning-level1-dfd.md) | 第一层数据流图 DFD（Mermaid，可渲染） | 已完成 |
| [diagrams/planning-module-relations.md](diagrams/planning-module-relations.md) | 与 system / sales / procurement / inventory 的关系图（Mermaid，可渲染） | 已完成 |
| [interface-draft.md](interface-draft.md) | 跨模块数据接口需求草案（正式定义已落地为 `contract.py` 与 REST API） | 已完成 |
| [week3-detailed-design.md](week3-detailed-design.md) | 第 3 周：详细功能设计与数据结构模型设计 | 已完成 |

## 阶段边界

| 阶段 | 内容 | 边界 |
| --- | --- | --- |
| 第 2 周 | 系统分析、功能树、第一层 DFD、输入/处理/输出分析、跨模块数据需求草案、页面初步规划、技术选型记录 | 仅文档，不含业务实现 |
| 第 3 周 | 详细功能设计、MRP 处理逻辑、E-R 模型、数据结构物理模型、API 详细定义、页面详细设计 | 设计文档 + 实现落地 |
| 已交付 | 计划模块全部业务功能实现于 `backend/app/modules/planning/` 与 `frontend/src/{api,views}/planning/` | 遵循模块隔离铁律 |

> 最新交付状态：planning 后端 36 个路径已实现，MRP 为真实多层 BOM 展开算法；
> 表结构见 [`../database/planning-er.md`](../database/planning-er.md)，
> 接口清单见 [`../api/api-contract.md`](../api/api-contract.md)。

## 约束

本目录文档遵循仓库根目录 [CONTRIBUTING.md](../../CONTRIBUTING.md) 与
[docs/architecture/module-boundaries.md](../architecture/module-boundaries.md) 的模块隔离约定：

- planning 只读写自己拥有的数据表（MPS / MRP 结果 / 生产作业计划 / 派工单 / 领料单）。
- BOM、物料、库存等数据归其他模块所有，planning 只能通过约定的 Service / API Contract 获取，禁止跨模块直读。
