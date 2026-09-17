# Inventory Module（库存管理）

## 模块职责

管理仓库、库位与库存流水，维护实时库存状态，并把库存状态反馈给 planning 模块用于 MRP 计算。

## 计划包含的主要功能

- 仓库与库位管理
- 采购到货入库
- 生产领料出库
- 完工入库
- 销售发货出库
- 移库与盘点
- 实时库存查询

## 输入

- 采购到货信息（来自 procurement 模块）
- 生产领料单、完工入库单（来自 planning 模块）
- 销售发货指令（来自 sales 模块）

## 输出

- 实时库存状态（反馈给 planning 模块 / MRP）
- 库存流水与结存

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/inventory/router.py` |
| 后端模型 | `backend/app/modules/inventory/models.py` |
| 后端测试 | `backend/tests/inventory/` |
| 前端接口 | `frontend/src/api/inventory/` |
| 前端页面 | `frontend/src/views/inventory/` |

## API 前缀

- 后端：`/api/v1/inventory`
- 前端路由：`/inventory`

## Owner

TBD

## Status

Not Started

## 占位接口

- `GET /api/v1/inventory/health` → `{ "module": "inventory", "status": "up" }`（仅用于验证路由注册成功）
