# Planning Module（计划管理）

## 模块职责

负责 MPS、MRP 及生产作业计划。
本课程设计中**生产相关功能全部归属本模块**，不设独立的 production 模块。

## 功能范围（第 2 周功能初步设计）

1. 主生产计划 MPS（导入 / 维护 / 确认 / 查询）
2. 物料需求计划 MRP（参数设置 / BOM 逐层展开 / 毛需求计算 / 库存净算 / 净需求计算 / 结果确认）
3. 生产作业计划（自制件需求生成 / 作业计划维护）
4. 派工单管理（生成 / 下达 / 状态查询）
5. 领料单管理（生成 / 下达 / 状态查询）
6. 综合查询与统计分析

详细设计文档见 `docs/planning/`：
功能树、第一层数据流图 DFD、模块关系图、跨模块接口草案、第 2 周功能初步设计方案。

## 输入

- 销售需求 / 销售订单（来自 sales 模块）
- BOM、工艺路线、产品与物料主数据（来自 system 模块）
- 库存状态（来自 inventory 模块）

## 输出

- MRP 结果
- 采购需求（交 procurement 模块执行）
- 生产作业计划 / 派工单 / 领料单（交 inventory 模块执行领料与完工入库）

## 数据表规划（Owner: planning）

`pln_demand` / `pln_mps` / `pln_mps_item` / `pln_mrp_run` / `pln_mrp_result` / `pln_production_plan` / `pln_dispatch_order` / `pln_material_requisition` / `pln_material_requisition_item` / `pln_completion_report`

> 详见 `docs/architecture/data-ownership.md`。第 3 周完成 E-R 与物理模型设计后才建表，**当前不创建任何业务表**。

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/planning/router.py` |
| 后端模型 | `backend/app/modules/planning/models.py` |
| 后端测试 | `backend/tests/planning/` |
| 前端接口 | `frontend/src/api/planning/` |
| 前端页面 | `frontend/src/views/planning/` |

## API 前缀

- 后端：`/api/v1/planning`
- 前端路由：`/planning`
- 业务错误码区段：`3000~3999`

## Owner

TBD

## Status

- 第 2 周：功能初步设计（仅文档）已完成 —— 见 `docs/planning/week2-functional-design.md`
- 业务功能实现：Not Started

## 占位接口

- `GET /api/v1/planning/health` → `{ "module": "planning", "status": "up" }`（仅用于验证路由注册成功）
