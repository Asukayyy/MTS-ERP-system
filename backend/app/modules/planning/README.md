# Planning Module（计划管理）

## 模块职责

负责 MPS、MRP 及生产作业计划。
本课程设计中**生产相关功能全部归属本模块**，不设独立的 production 模块。

## 计划包含的主要功能

- 主生产计划 MPS（输入为课程附录 1 的 MPS）
- 物料需求计划 MRP（依据转椅 BOM 与库存状态展开）
- 生产作业计划
- 派工单
- 领料单

## 输入

- 销售需求 / 销售订单（来自 sales 模块）
- BOM、工艺路线、产品与物料主数据（来自 system 模块）
- 库存状态（来自 inventory 模块）

## 输出

- MRP 结果
- 采购需求（交 procurement 模块执行）
- 生产作业计划 / 派工单 / 领料单（交 inventory 模块执行领料与完工入库）

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

## Owner

TBD

## Status

Not Started

## 占位接口

- `GET /api/v1/planning/health` → `{ "module": "planning", "status": "up" }`（仅用于验证路由注册成功）
