# System Module（系统与基础信息管理）

## 模块职责

提供全系统共用的基础主数据与系统管理能力。其它模块只能读取本模块提供的基础数据，
不得直接操作本模块的表与业务代码。

## 计划包含的主要功能

- 产品管理
- 物料管理
- BOM 管理（转椅 BOM 为课程验证对象）
- 工艺路线管理
- 组织与人员管理
- 基础字典维护
- 用户 / 角色 / 权限管理
- 操作日志

## 输入

- 管理员与基础数据维护人员的人工录入
- 外部导入的基础数据（后续）

## 输出

- 产品、物料、BOM、工艺路线等基础主数据
- 用户 / 角色 / 权限等系统基础能力

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/system/router.py` |
| 后端模型 | `backend/app/modules/system/models.py` |
| 后端测试 | `backend/tests/system/` |
| 前端接口 | `frontend/src/api/system/` |
| 前端页面 | `frontend/src/views/system/` |

## API 前缀

- 后端：`/api/v1/system`
- 前端路由：`/system`

## Owner

TBD

## Status

Not Started

## 占位接口

- `GET /api/v1/system/health` → `{ "module": "system", "status": "up" }`（仅用于验证路由注册成功）
