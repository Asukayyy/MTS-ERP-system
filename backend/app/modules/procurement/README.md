# Procurement Module（采购管理）

## 模块职责

接收 planning 模块产生的采购需求，完成供应商选择、采购下单与到货登记。

## 计划包含的主要功能

- 供应商管理
- 采购计划
- 采购订单管理
- 到货登记

## 输入

- MRP 采购需求（来自 planning 模块）
- 物料主数据（来自 system 模块）
- 实时库存状态（来自 inventory 模块，用于采购决策参考）

## 输出

- 采购计划
- 采购订单
- 到货信息（交 inventory 模块执行入库）

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/procurement/router.py` |
| 后端模型 | `backend/app/modules/procurement/models.py` |
| 后端测试 | `backend/tests/procurement/` |
| 前端接口 | `frontend/src/api/procurement/` |
| 前端页面 | `frontend/src/views/procurement/` |

## API 前缀

- 后端：`/api/v1/procurement`
- 前端路由：`/procurement`

## Owner

TBD

## Status

Not Started

## 占位接口

- `GET /api/v1/procurement/health` → `{ "module": "procurement", "status": "up" }`（仅用于验证路由注册成功）
