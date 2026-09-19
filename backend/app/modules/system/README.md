# System Module（系统与基础信息管理）

> 状态：**已实现**（后端 43 个路径 / 前端页面已接；实现详见 `service.py`）

## 模块职责

提供全系统共用的基础主数据与系统管理能力。本模块是 `sys_material`、`sys_personnel`、
BOM、工艺路线的**唯一 Owner**，其它模块只能通过本模块的 `contract.py` 读取，不得直接
操作本模块的表与业务代码（见 `docs/architecture/module-ownership.md`）。

## 已实现功能

| 功能 | 说明 |
| --- | --- |
| 物料管理 | 增删改查、状态流转、按类型/供应类型/关键字检索 |
| BOM 管理 | 头 + 明细、多层展开树、版本激活（`/boms/{id}/activate`）、环检测 |
| 工艺路线 | 头 + 工序明细、状态流转 |
| 组织管理 | 树形结构、扁平列表、状态流转 |
| 人员管理 | 增删改查、按组织过滤、状态流转 |
| 基础字典 | 字典 + 字典项两级维护 |
| RBAC | 用户 / 角色 / 权限 / 角色授权 / 用户授角色 / 简化登录 |
| 操作日志 | 全模块写入的 `sys_operation_log` 统一查询入口 |
| 课程数据导入 | 物料与 BOM 的 `preview → confirm` 两段式导入（读 `data/seed/course_chair_case.json`） |
| 统计与健康检查 | `/stats`、`/health` |

## 输入

- 管理员与基础数据维护人员的人工录入
- 课程种子数据 `data/seed/course_chair_case.json`（转椅递归 BOM 树）

## 输出

- 产品、物料、BOM、工艺路线等基础主数据
- 用户 / 角色 / 权限等系统基础能力

## 数据表（Owner: system，共 15 张）

`sys_material`、`sys_bom`、`sys_bom_item`、`sys_routing`、`sys_routing_operation`、
`sys_organization`、`sys_personnel`、`sys_dictionary`、`sys_dictionary_item`、
`sys_user`、`sys_role`、`sys_permission`、`sys_user_role`、`sys_role_permission`、
`sys_operation_log`

> 表结构详见 `docs/database/system-er.md` 与 `docs/database/physical-data-model.md`。

## 对外契约（唯一跨模块入口）

`backend/app/modules/system/contract.py`：

- 主数据读取：`get_material` / `get_materials` / `find_material_by_code` /
  `search_materials` / `get_finished_materials`
- 人员读取：`get_personnel` / `get_personnel_name` / `get_personnel_names`
- BOM 读取（供 MRP 逐层展开）：`get_active_bom` / `get_bom` /
  `get_active_bom_children` / `has_bom`
- 操作日志：`log_operation`（**不 commit**，由调用方事务一并提交）

契约函数只返回 `dict` / 标量，不返回 ORM 对象，且永不调用 `db.commit()`。

## 主要接口分组

| 分组 | 前缀 |
| --- | --- |
| 物料 | `/api/v1/system/materials` |
| BOM | `/api/v1/system/boms`、`/boms/tree`、`/bom-items/{item_id}` |
| 工艺路线 | `/api/v1/system/routings`、`/routing-operations/{operation_id}` |
| 组织 | `/api/v1/system/organizations`、`/organizations/flat` |
| 人员 | `/api/v1/system/personnel` |
| 字典 | `/api/v1/system/dictionaries`、`/dictionary-items/{item_id}` |
| RBAC | `/api/v1/system/users`、`/roles`、`/permissions`、`/auth/login` |
| 操作日志 | `/api/v1/system/operation-logs` |
| 课程数据导入 | `/api/v1/system/import/materials/{preview,confirm}`、`/import/bom/{preview,confirm}` |
| 统计 | `/api/v1/system/stats`、`/health` |

完整清单见 `docs/api/api-contract.md`。

## 目录对应关系

| 层 | 路径 |
| --- | --- |
| 后端路由 | `backend/app/modules/system/router.py` |
| 后端模型 | `backend/app/modules/system/models.py` |
| 数据访问 | `backend/app/modules/system/repository.py` |
| 业务规则 | `backend/app/modules/system/service.py` |
| 跨模块契约 | `backend/app/modules/system/contract.py` |
| 后端测试 | `backend/tests/test_system.py` |
| 前端接口 | `frontend/src/api/system/` |
| 前端页面 | `frontend/src/views/system/` |

## API 前缀

- 后端：`/api/v1/system`
- 前端路由：`/system`
- 业务错误码区段：`1000~1999`

| 码 | 含义 |
| --- | --- |
| 1001 | 物料编码已存在 |
| 1002 | BOM 版本已存在 |
| 1003 | BOM 存在循环引用 |
| 1004 | 工号已存在 |
| 1005 | 目标数据不存在 |
| 1006 | 入参非法 |
| 1007 | 编码已存在 |
| 1008 | 状态流转非法 |
| 1009 | 数据已被引用，不可删除 |
| 1010 | 登录失败 |
| 1011 | 不支持的导入来源 |
| 1012 | 导入 BOM 前物料缺失 |