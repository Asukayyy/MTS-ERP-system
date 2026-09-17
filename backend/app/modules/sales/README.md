# Sales Module（销售管理）

## 模块职责

管理客户与销售需求，向 planning 模块提供销售需求与销售订单，并在库存发货后完成销售发货闭环。

## 计划包含的主要功能

- 客户管理
- 销售预测
- 销售订单管理
- 销售发货

## 输入

- 客户基础信息（来自 system 模块的产品 / 物料数据）
- 库存可用量（来自 inventory 模块，用于可发货性判断）

## 输出

- 销售需求 / 销售预测
- 销售订单
- 发货指令（交 inventory 模块执行）

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/sales/router.py` |
| 后端模型 | `backend/app/modules/sales/models.py` |
| 后端测试 | `backend/tests/sales/` |
| 前端接口 | `frontend/src/api/sales/` |
| 前端页面 | `frontend/src/views/sales/` |

## API 前缀

- 后端：`/api/v1/sales`
- 前端路由：`/sales`

## Owner

TBD

## Status

Not Started

## 占位接口

- `GET /api/v1/sales/health` → `{ "module": "sales", "status": "up" }`（仅用于验证路由注册成功）
