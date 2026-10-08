# Master Data Boundaries（公共主数据边界 · 初步定义）

> 本文档为**第二周初步边界定义**，只确定 **Owner / Consumer / Purpose** 三类信息。
> 表名、SQL 类型、外键、索引、完整字段清单等属于第三周"数据结构物理模型"，本轮**不提前定死**。
> 设计原则见 [week2-functional-design.md](week2-functional-design.md) 的"设计原则"节：
> **Single Source of Truth（单一数据源）**——同一类基础数据只由一个 Owner 模块负责维护，
> 其他模块只能引用，不重复建设自己的副本。

---

## 1. Product / 产品

| 项 | 内容 |
|---|---|
| Owner | System |
| Consumers | Sales、Planning、Inventory |
| Purpose | Sales：销售产品引用；Planning：MPS 产品引用；Inventory：成品库存引用 |

## 2. Material / 物料

| 项 | 内容 |
|---|---|
| Owner | System |
| Consumers | Planning、Procurement、Inventory |
| Purpose | Planning：MRP 计算；Procurement：采购物料引用；Inventory：库存物料引用 |

## 3. BOM

| 项 | 内容 |
|---|---|
| Owner | System |
| Consumer | Planning |
| Purpose | MRP 多层级需求展开 |
| 约定 | 其他模块**禁止维护自己的 BOM 副本**；Planning 只读 BOM 用于 MRP 展开 |

## 4. Routing / 工艺路线

| 项 | 内容 |
|---|---|
| Owner | System |
| Consumer | Planning |
| Purpose | 车间生产作业计划参考 |

## 5. Organization / Personnel（组织 / 人员）

| 项 | 内容 |
|---|---|
| Owner | System |
| Consumers | 各业务模块 |
| Purpose | 销售员、采购员等相关业务人员引用 |

## 6. Common Dictionary（共性基础字典）

| 项 | 内容 |
|---|---|
| Owner | System |
| Consumers | All Modules |
| Purpose | 计量单位、状态、分类、业务类型等统一编码 |

## 7. User / Role / Permission（用户 / 角色 / 权限）与 Operation Log（操作日志）

| 项 | 内容 |
|---|---|
| Owner | System |
| Consumers / Producers | 权限：All Modules **Use**；日志：其他模块 **Produce Event**，由 System 统一 **Record** |
| Purpose | 账号、角色、访问范围与权限分配；全系统操作留痕 |

---

## 公共数据责任矩阵

术语含义：

- **Owner**：拥有并负责维护该数据（唯一、排他）
- **Read**：只读引用
- **Use**：按 System 提供的访问控制使用
- **Produce**：产生事件数据（由 System 记录）
- **-** ：无直接关系

| 数据对象 | Owner | Sales | Planning | Procurement | Inventory |
|---|---|---|---|---|---|
| 产品 Product | System | Read | Read | - | Read |
| 物料 Material | System | - | Read | Read | Read |
| BOM | System | - | Read | - | - |
| 工艺路线 Routing | System | - | Read | - | - |
| 组织 / 人员 | System | 按需 Read | 按需 Read | 按需 Read | 按需 Read |
| 共性基础字典 | System | Read | Read | Read | Read |
| 用户 / 角色 / 权限 | System | Use | Use | Use | Use |
| 操作日志 | System | Produce | Produce | Produce | Produce |

## 边界约定（协作纪律）

1. Sales **不建立**自己的 Product Master。
2. Planning **不建立**自己的 BOM Master。
3. Procurement **不建立**自己的 Material Master。
4. Inventory **不建立**自己的 Material Master；库存记录用「物料引用 + 数量」表达，物料本身仍归 System。
5. 其他模块**不允许反向修改** System 主数据；只能通过接口（未来定义）读取，并可向 System 日志提交操作事件。
6. 即使五个模块最终共享同一个 MySQL 数据库，也必须遵守上述 Data Ownership；本轮**不实施**数据库层强权限隔离，只记录原则。