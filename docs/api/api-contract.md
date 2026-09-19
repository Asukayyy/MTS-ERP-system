# BH-ERP API 契约（API Contract）

> 本文由**真实 OpenAPI schema**（`create_app().openapi()`）自动导出后编写，
> 路径、HTTP 方法、入参位置、请求体模型名**逐条来自代码**，不存在手写偏差。
>
> - 路由定义：`backend/app/modules/<module>/router.py`
> - 入参/出参模型：`backend/app/modules/<module>/schemas.py`
> - 响应包装：`backend/app/common/response.py`；分页：`backend/app/common/pagination.py`；
>   错误码：`backend/app/common/exceptions.py`
> - 实测规模：**167 个路径 / 223 个操作**

## 一、基础约定

| 项 | 值 | 依据 |
| --- | --- | --- |
| 应用名 / 版本 | `BH-ERP` / `0.1.0` | `core/config.py`（`APP_NAME` / `APP_VERSION`） |
| 统一前缀 | `/api/v1` | `core/config.py`（`API_V1_PREFIX`） |
| 模块路由前缀 | `/api/v1/system`、`/api/v1/sales`、`/api/v1/planning`、`/api/v1/procurement`、`/api/v1/inventory` | `app/main.py` 中 `include_router` |
| 应用级健康检查 | `GET /health` | `app/main.py` |
| 数据格式 | JSON（`Content-Type: application/json`） | FastAPI 默认 |
| 前端基础地址 | `VITE_API_BASE_URL=/api/v1`（开发环境经 Vite proxy 转发到 `http://127.0.0.1:8000`） | `frontend/.env.example` |

### 1.1 统一响应结构

**所有接口**（含业务错误）都返回同一个信封：

```json
{
  "code": 0,
  "message": "success",
  "data": { }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | `int` | **`0` 表示成功**（`common/response.py::SUCCESS_CODE`）；非 0 为业务错误码 |
| `message` | `str` | 成功时为 `success`；失败时为可直接展示给用户的中文提示 |
| `data` | `any` | 业务数据；失败时通常为 `null`（参数校验失败时为错误明细数组） |

定义位置：`common/response.py` 的 `ApiResponse[T]`、`success()`、`error()`。

### 1.2 分页

列表类接口的 `data` 固定为：

```json
{ "page": 1, "page_size": 20, "total": 137, "items": [] }
```

| 参数 | 默认 | 约束 |
| --- | --- | --- |
| `page` | `1`（`DEFAULT_PAGE`） | `>= 1` |
| `page_size` | `20`（`DEFAULT_PAGE_SIZE`） | `1 ~ 200`（`MAX_PAGE_SIZE = 200`） |

定义位置：`common/pagination.py`（`PageParams`、`PageData[T]`）。

### 1.3 错误处理

| 触发方式 | HTTP 状态码 | `code` | 说明 |
| --- | --- | --- | --- |
| `BusinessException(code, message)` | **200** | 模块业务码 | 业务失败也返回 200，由 `code` 区分，前端只看 `code` |
| 请求参数校验失败（Pydantic） | **422** | `9002`（`CODE_VALIDATION_ERROR`） | `data` 为 `exc.errors()` |
| 框架级 404 / 405 / HTTPException | 原始状态码（404/405/...） | `9001`（`CODE_HTTP_ERROR`） | `message` 为原始 detail |
| 未捕获异常 | 500 | `9000`（`CODE_INTERNAL_ERROR`） | 由 FastAPI 默认处理 |

### 1.4 错误码区段

| 区段 | 归属 |
| --- | --- |
| `0` | 成功 |
| `1000~1999` | 系统基础数据（system） |
| `2000~2999` | 销售管理（sales） |
| `3000~3999` | 计划与生产管理（planning） |
| `4000~4999` | 采购管理（procurement） |
| `5000~5999` | 库存管理（inventory） |
| `9000~9999` | 通用 / 框架级（`9000` 内部错误、`9001` HTTP 错误、`9002` 参数校验） |

各模块已定义的错误码常量（源码均为 `CODE_*`，见 `modules/<module>/service.py` 顶部）：

| 模块 | 错误码 | 常量名 | 含义 |
| --- | --- | --- | --- |
| system | `1001` | `CODE_MATERIAL_CODE_EXISTS` | 物料编码已存在 |
| system | `1002` | `CODE_BOM_VERSION_EXISTS` | BOM 版本已存在 |
| system | `1003` | `CODE_BOM_CYCLE` | BOM 存在循环引用 |
| system | `1004` | `CODE_EMPLOYEE_NO_EXISTS` | 工号已存在 |
| system | `1005` | `CODE_NOT_FOUND` | 资源不存在 |
| system | `1006` | `CODE_INVALID_PARAM` | 入参非法 |
| system | `1007` | `CODE_CODE_EXISTS` | 编码已存在 |
| system | `1008` | `CODE_INVALID_STATUS` | 状态非法 |
| system | `1009` | `CODE_DATA_REFERENCED` | 数据已被引用，不能删除 |
| system | `1010` | `CODE_LOGIN_FAILED` | 登录失败 |
| system | `1011` | `CODE_UNSUPPORTED_SOURCE` | 不支持的数据源标识 |
| system | `1012` | `CODE_MATERIAL_MISSING_FOR_BOM` | BOM 引用的物料不存在 |
| sales | `2000` | `CODE_PARAM_INVALID` | 入参 / 状态非法 |
| sales | `2001` | `CODE_DUPLICATE` | 唯一性冲突（如客户编码重复） |
| sales | `2002` | `CODE_IMMUTABLE` | 已完结 / 已取消单据不可修改 |
| sales | `2003` | `CODE_SHIP_QTY_EXCEED` | 发货数量超过未发数量 |
| sales | `2004` | `CODE_RETURN_MISMATCH` | 退货单与原订单客户不一致 |
| sales | `2005` | `CODE_NOT_FOUND` | 资源不存在 |
| sales | `2006` | `CODE_STATUS_INVALID` | 单据状态不允许该操作 |
| planning | `3000` | `CODE_PARAM_INVALID` | 入参 / 状态非法 |
| planning | `3001` | `CODE_BOM_CYCLE` | BOM 存在循环引用 |
| planning | `3002` | `CODE_MPS_LOCKED` | 已确认 / 已下达的 MPS 只读 |
| planning | `3003` | `CODE_NOT_FOUND` | 资源不存在 |
| planning | `3004` | `CODE_DUPLICATE` | 唯一性冲突 |
| planning | `3005` | `CODE_CONTRACT_NOT_READY` | 跨模块契约尚未就绪 |
| planning | `3006` | `CODE_STATUS_INVALID` | 状态机不允许该流转 |
| planning | `3007` | `CODE_IMPORT_INVALID` | 导入数据校验失败 |
| procurement | `4000` | `CODE_PARAM_INVALID` | 入参 / 状态非法 |
| procurement | `4001` | `CODE_DUPLICATE` | 供应商编码重复 |
| procurement | `4002` | `CODE_SUPPLIER_MATERIAL_DUPLICATE` | 供应商-物料关系重复 |
| procurement | `4003` | `CODE_IMMUTABLE` | 已确认 / 已下达 / 已完结单据不可修改 |
| procurement | `4004` | `CODE_RECEIPT_QTY_EXCEED` | 到货数量超过未到货数量 |
| procurement | `4005` | `CODE_NOT_FOUND` | 资源不存在 |
| procurement | `4006` | `CODE_STATUS_INVALID` | 单据状态不允许该流转 |
| procurement | `4007` | `CODE_CONTRACT_NOT_READY` | 跨模块契约尚未就绪 |
| inventory | `5000` | `CODE_PARAM_INVALID` | 入参 / 状态非法 |
| inventory | `5001` | `CODE_STOCK_INSUFFICIENT` | 库存不足 |
| inventory | `5002` | `CODE_CONTRACT_NOT_READY` | 跨模块契约尚未就绪 |
| inventory | `5003` | `CODE_STATUS_INVALID` | 单据状态不允许该操作 |
| inventory | `5004` | `CODE_NOT_FOUND` | 资源不存在 |
| inventory | `5005` | `CODE_DUPLICATE` | 唯一性冲突 |
| inventory | `5006` | `CODE_BALANCE_NEGATIVE` | 调整后库存会为负 |
| inventory | `5007` | `CODE_LOCATION_IN_USE` | 库位已被库存引用，禁止删除 |

## 二、接口清单（按模块）

### 2.1 系统基础数据（`system`，前缀 `/api/v1/system`）—— 61 个操作

| 方法 | 路径 | 说明 | 路径参数 | 查询参数 | 请求体 |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/system/auth/login` | 登录（简化版） | — | — | `LoginIn` |
| `DELETE` | `/api/v1/system/bom-items/{item_id}` | 删除 BOM 子项 | `item_id` | — | — |
| `PUT` | `/api/v1/system/bom-items/{item_id}` | 修改 BOM 子项 | `item_id` | — | `BomItemUpdate` |
| `GET` | `/api/v1/system/boms` | BOM 分页查询 | — | `material_id`、`status`、`is_active`、`page`、`page_size` | — |
| `POST` | `/api/v1/system/boms` | 新增 BOM | — | — | `BomCreate` |
| `GET` | `/api/v1/system/boms/tree` | 多层 BOM 展开 | — | `material_id`、`max_level` | — |
| `DELETE` | `/api/v1/system/boms/{bom_id}` | 删除 BOM | `bom_id` | — | — |
| `GET` | `/api/v1/system/boms/{bom_id}` | BOM 详情 | `bom_id` | — | — |
| `PUT` | `/api/v1/system/boms/{bom_id}` | 修改 BOM | `bom_id` | — | `BomUpdate` |
| `POST` | `/api/v1/system/boms/{bom_id}/activate` | 激活 BOM 版本 | `bom_id` | — | — |
| `POST` | `/api/v1/system/boms/{bom_id}/items` | 新增 BOM 子项 | `bom_id` | — | `BomItemCreate` |
| `PATCH` | `/api/v1/system/boms/{bom_id}/status` | BOM 状态流转 | `bom_id` | — | `app__modules__system__schemas__StatusUpdate` |
| `GET` | `/api/v1/system/dictionaries` | 字典查询 | — | — | — |
| `POST` | `/api/v1/system/dictionaries` | 新增字典 | — | — | `DictionaryCreate` |
| `PUT` | `/api/v1/system/dictionaries/{dict_id}` | 修改字典 | `dict_id` | — | `DictionaryUpdate` |
| `POST` | `/api/v1/system/dictionaries/{dict_id}/items` | 新增字典项 | `dict_id` | — | `DictionaryItemCreate` |
| `DELETE` | `/api/v1/system/dictionary-items/{item_id}` | 删除字典项 | `item_id` | — | — |
| `PUT` | `/api/v1/system/dictionary-items/{item_id}` | 修改字典项 | `item_id` | — | `DictionaryItemUpdate` |
| `GET` | `/api/v1/system/health` | system 模块健康检查 | — | — | — |
| `POST` | `/api/v1/system/import/bom/confirm` | 课程 BOM 导入确认 | — | — | `ImportSourceIn` |
| `POST` | `/api/v1/system/import/bom/preview` | 课程 BOM 导入预览 | — | — | `ImportSourceIn` |
| `POST` | `/api/v1/system/import/materials/confirm` | 课程物料导入确认 | — | — | `ImportSourceIn` |
| `POST` | `/api/v1/system/import/materials/preview` | 课程物料导入预览 | — | — | `ImportSourceIn` |
| `GET` | `/api/v1/system/materials` | 物料分页查询 | — | `material_type`、`supply_type`、`status`、`keyword`、`page`、`page_size` | — |
| `POST` | `/api/v1/system/materials` | 新增物料 | — | — | `MaterialCreate` |
| `GET` | `/api/v1/system/materials/{material_id}` | 物料详情 | `material_id` | — | — |
| `PUT` | `/api/v1/system/materials/{material_id}` | 修改物料 | `material_id` | — | `MaterialUpdate` |
| `PATCH` | `/api/v1/system/materials/{material_id}/status` | 物料状态流转 | `material_id` | — | `app__modules__system__schemas__StatusUpdate` |
| `GET` | `/api/v1/system/operation-logs` | 操作日志分页查询 | — | `module`、`action`、`target_type`、`target_id`、`page`、`page_size` | — |
| `GET` | `/api/v1/system/organizations` | 组织树查询 | — | — | — |
| `POST` | `/api/v1/system/organizations` | 新增组织 | — | — | `OrganizationCreate` |
| `GET` | `/api/v1/system/organizations/flat` | 组织平铺查询 | — | — | — |
| `GET` | `/api/v1/system/organizations/{org_id}` | 组织详情 | `org_id` | — | — |
| `PUT` | `/api/v1/system/organizations/{org_id}` | 修改组织 | `org_id` | — | `OrganizationUpdate` |
| `PATCH` | `/api/v1/system/organizations/{org_id}/status` | 组织状态流转 | `org_id` | — | `app__modules__system__schemas__StatusUpdate` |
| `GET` | `/api/v1/system/permissions` | 权限树查询 | — | — | — |
| `POST` | `/api/v1/system/permissions` | 新增权限点 | — | — | `PermissionCreate` |
| `PUT` | `/api/v1/system/permissions/{permission_id}` | 修改权限点 | `permission_id` | — | `PermissionUpdate` |
| `GET` | `/api/v1/system/personnel` | 人员分页查询 | — | `org_id`、`status`、`keyword`、`page`、`page_size` | — |
| `POST` | `/api/v1/system/personnel` | 新增人员 | — | — | `PersonnelCreate` |
| `GET` | `/api/v1/system/personnel/{personnel_id}` | 人员详情 | `personnel_id` | — | — |
| `PUT` | `/api/v1/system/personnel/{personnel_id}` | 修改人员 | `personnel_id` | — | `PersonnelUpdate` |
| `PATCH` | `/api/v1/system/personnel/{personnel_id}/status` | 人员状态流转 | `personnel_id` | — | `app__modules__system__schemas__StatusUpdate` |
| `GET` | `/api/v1/system/roles` | 角色查询 | — | `status` | — |
| `POST` | `/api/v1/system/roles` | 新增角色 | — | — | `RoleCreate` |
| `PUT` | `/api/v1/system/roles/{role_id}` | 修改角色 | `role_id` | — | `RoleUpdate` |
| `POST` | `/api/v1/system/roles/{role_id}/permissions` | 设置角色权限 | `role_id` | — | `PermissionIdsUpdate` |
| `DELETE` | `/api/v1/system/routing-operations/{operation_id}` | 删除工序 | `operation_id` | — | — |
| `PUT` | `/api/v1/system/routing-operations/{operation_id}` | 修改工序 | `operation_id` | — | `RoutingOperationUpdate` |
| `GET` | `/api/v1/system/routings` | 工艺路线分页查询 | — | `material_id`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/system/routings` | 新增工艺路线 | — | — | `RoutingCreate` |
| `GET` | `/api/v1/system/routings/{routing_id}` | 工艺路线详情 | `routing_id` | — | — |
| `PUT` | `/api/v1/system/routings/{routing_id}` | 修改工艺路线 | `routing_id` | — | `RoutingUpdate` |
| `POST` | `/api/v1/system/routings/{routing_id}/operations` | 新增工序 | `routing_id` | — | `RoutingOperationCreate` |
| `PATCH` | `/api/v1/system/routings/{routing_id}/status` | 工艺路线状态流转 | `routing_id` | — | `app__modules__system__schemas__StatusUpdate` |
| `GET` | `/api/v1/system/stats` | 系统基础数据统计 | — | — | — |
| `GET` | `/api/v1/system/users` | 用户分页查询 | — | `status`、`keyword`、`page`、`page_size` | — |
| `POST` | `/api/v1/system/users` | 新增用户 | — | — | `UserCreate` |
| `PUT` | `/api/v1/system/users/{user_id}` | 修改用户 | `user_id` | — | `UserUpdate` |
| `POST` | `/api/v1/system/users/{user_id}/roles` | 设置用户角色 | `user_id` | — | `RoleIdsUpdate` |
| `PATCH` | `/api/v1/system/users/{user_id}/status` | 用户状态流转 | `user_id` | — | `app__modules__system__schemas__StatusUpdate` |

### 2.2 销售管理（`sales`，前缀 `/api/v1/sales`）—— 33 个操作

| 方法 | 路径 | 说明 | 路径参数 | 查询参数 | 请求体 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/sales/customers` | 客户列表 | — | `keyword`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/sales/customers` | 新增客户 | — | — | `CustomerCreate` |
| `GET` | `/api/v1/sales/customers/{customer_id}` | 客户详情 | `customer_id` | — | — |
| `PUT` | `/api/v1/sales/customers/{customer_id}` | 修改客户 | `customer_id` | — | `CustomerUpdate` |
| `PATCH` | `/api/v1/sales/customers/{customer_id}/status` | 客户启用/停用（不物理删除） | `customer_id` | — | `app__modules__sales__schemas__StatusUpdate` |
| `GET` | `/api/v1/sales/forecasts` | 销售预测列表 | — | `material_id`、`status`、`forecast_month`、`page`、`page_size` | — |
| `POST` | `/api/v1/sales/forecasts` | 新增销售预测 | — | — | `ForecastCreate` |
| `DELETE` | `/api/v1/sales/forecasts/{forecast_id}` | 删除销售预测（仅 DRAFT） | `forecast_id` | `operator_id` | — |
| `PUT` | `/api/v1/sales/forecasts/{forecast_id}` | 修改销售预测 | `forecast_id` | — | `ForecastUpdate` |
| `PATCH` | `/api/v1/sales/forecasts/{forecast_id}/status` | 销售预测状态流转 | `forecast_id` | — | `app__modules__sales__schemas__StatusUpdate` |
| `GET` | `/api/v1/sales/health` | sales 模块健康检查（占位） | — | — | — |
| `GET` | `/api/v1/sales/orders` | 销售订单列表 | — | `customer_id`、`status`、`date_from`、`date_to`、`keyword`、`page`、`page_size` | — |
| `POST` | `/api/v1/sales/orders` | 新增销售订单 | — | — | `app__modules__sales__schemas__OrderCreate` |
| `DELETE` | `/api/v1/sales/orders/{order_id}` | 删除销售订单（仅 DRAFT） | `order_id` | `operator_id` | — |
| `GET` | `/api/v1/sales/orders/{order_id}` | 销售订单详情 | `order_id` | — | — |
| `PUT` | `/api/v1/sales/orders/{order_id}` | 修改销售订单（仅 DRAFT） | `order_id` | — | `app__modules__sales__schemas__OrderUpdate` |
| `PATCH` | `/api/v1/sales/orders/{order_id}/status` | 销售订单状态流转 | `order_id` | — | `app__modules__sales__schemas__StatusUpdate` |
| `GET` | `/api/v1/sales/products` | 销售产品查询（FINISHED + ACTIVE 物料） | — | `keyword` | — |
| `GET` | `/api/v1/sales/reports/order-status` | 报表：订单执行状态 | — | — | — |
| `GET` | `/api/v1/sales/reports/returns` | 报表：退货记录 | — | `date_from`、`date_to` | — |
| `GET` | `/api/v1/sales/reports/sales-volume` | 报表：销售量按物料汇总 | — | `date_from`、`date_to` | — |
| `GET` | `/api/v1/sales/reports/shipments` | 报表：发货记录 | — | `date_from`、`date_to` | — |
| `GET` | `/api/v1/sales/returns` | 销售退货列表 | — | `order_id`、`customer_id`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/sales/returns` | 新增退货单 | — | — | `ReturnCreate` |
| `GET` | `/api/v1/sales/returns/{return_id}` | 退货单详情 | `return_id` | — | — |
| `POST` | `/api/v1/sales/returns/{return_id}/cancel` | 取消退货单（仅 DRAFT） | `return_id` | `operator_id` | — |
| `POST` | `/api/v1/sales/returns/{return_id}/confirm` | 确认退货（调用库存入库） | `return_id` | `operator_id` | — |
| `GET` | `/api/v1/sales/shipments` | 销售发货列表 | — | `order_id`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/sales/shipments` | 新增发货单 | — | — | `ShipmentCreate` |
| `GET` | `/api/v1/sales/shipments/{shipment_id}` | 发货单详情 | `shipment_id` | — | — |
| `POST` | `/api/v1/sales/shipments/{shipment_id}/cancel` | 取消发货单（仅 DRAFT） | `shipment_id` | `operator_id` | — |
| `POST` | `/api/v1/sales/shipments/{shipment_id}/confirm` | 确认发货（调用库存出库） | `shipment_id` | `operator_id` | — |
| `GET` | `/api/v1/sales/stats` | 销售统计 | — | — | — |

### 2.3 计划与生产管理（`planning`，前缀 `/api/v1/planning`）—— 45 个操作

| 方法 | 路径 | 说明 | 路径参数 | 查询参数 | 请求体 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/planning/completion-reports` | 完工报告列表 | — | `status`、`plan_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/planning/completion-reports` | 新增完工报告 | — | — | `CompletionReportCreate` |
| `GET` | `/api/v1/planning/completion-reports/{report_id}` | 完工报告详情 | `report_id` | — | — |
| `POST` | `/api/v1/planning/completion-reports/{report_id}/cancel` | 取消完工报告 | `report_id` | — | — |
| `POST` | `/api/v1/planning/completion-reports/{report_id}/confirm` | 确认完工（入库） | `report_id` | — | — |
| `GET` | `/api/v1/planning/demands` | 需求列表 | — | `source_type`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/planning/demands` | 新增需求 | — | — | `DemandCreate` |
| `POST` | `/api/v1/planning/demands/from-replenishment` | 从库存补库需求生成需求 | — | — | `DemandFromReplenishmentRequest` |
| `POST` | `/api/v1/planning/demands/from-sales` | 从销售订单导入需求 | — | — | — |
| `GET` | `/api/v1/planning/demands/{demand_id}` | 需求详情 | `demand_id` | — | — |
| `PATCH` | `/api/v1/planning/demands/{demand_id}/status` | 需求状态流转 | `demand_id` | — | `DemandStatusUpdate` |
| `GET` | `/api/v1/planning/dispatch-orders` | 派工单列表 | — | `status`、`plan_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/planning/dispatch-orders` | 新增派工单 | — | — | `DispatchOrderCreate` |
| `GET` | `/api/v1/planning/dispatch-orders/{dispatch_id}` | 派工单详情 | `dispatch_id` | — | — |
| `PATCH` | `/api/v1/planning/dispatch-orders/{dispatch_id}/status` | 派工单状态流转 | `dispatch_id` | — | `app__modules__planning__schemas__StatusUpdate` |
| `GET` | `/api/v1/planning/health` | planning 模块健康检查（占位） | — | — | — |
| `GET` | `/api/v1/planning/mps` | MPS 列表 | — | `status`、`year`、`page`、`page_size` | — |
| `POST` | `/api/v1/planning/mps` | 新增 MPS | — | — | `MpsCreate` |
| `POST` | `/api/v1/planning/mps/import/confirm` | MPS 导入确认 | — | — | `MpsImportRequest` |
| `POST` | `/api/v1/planning/mps/import/preview` | MPS 导入预览（不落库） | — | — | `MpsImportRequest` |
| `DELETE` | `/api/v1/planning/mps/{mps_id}` | 删除 MPS | `mps_id` | — | — |
| `GET` | `/api/v1/planning/mps/{mps_id}` | MPS 详情 | `mps_id` | — | — |
| `PUT` | `/api/v1/planning/mps/{mps_id}` | 修改 MPS | `mps_id` | — | `MpsUpdate` |
| `PATCH` | `/api/v1/planning/mps/{mps_id}/status` | MPS 状态流转 | `mps_id` | — | `app__modules__planning__schemas__StatusUpdate` |
| `GET` | `/api/v1/planning/mrp/results` | MRP 结果（跨批次分页） | — | `run_id`、`supply_type`、`status`、`page`、`page_size` | — |
| `PATCH` | `/api/v1/planning/mrp/results/{result_id}/status` | MRP 结果状态流转 | `result_id` | — | `MrpResultStatusUpdate` |
| `POST` | `/api/v1/planning/mrp/run` | 执行 MRP 运算 | — | — | `MrpRunCreate` |
| `GET` | `/api/v1/planning/mrp/runs` | MRP 批次列表 | — | `page`、`page_size` | — |
| `GET` | `/api/v1/planning/mrp/runs/{run_id}` | MRP 批次详情（含结果） | `run_id` | — | — |
| `POST` | `/api/v1/planning/mrp/runs/{run_id}/create-production-plans` | 由 MRP 批次生成生产作业计划 | `run_id` | — | — |
| `POST` | `/api/v1/planning/mrp/runs/{run_id}/create-purchase-plan` | 由 MRP 批次生成采购计划 | `run_id` | — | — |
| `GET` | `/api/v1/planning/mrp/runs/{run_id}/explain` | MRP 计算明细 | `run_id` | `material_id` | — |
| `GET` | `/api/v1/planning/mrp/runs/{run_id}/results` | MRP 批次结果（分页） | `run_id` | `supply_type`、`status`、`page`、`page_size` | — |
| `GET` | `/api/v1/planning/production-plans` | 生产作业计划列表 | — | `status`、`material_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/planning/production-plans` | 新增生产作业计划 | — | — | `ProductionPlanCreate` |
| `POST` | `/api/v1/planning/production-plans/from-mrp` | 由 MRP 结果生成生产作业计划 | — | — | `ProductionPlanFromMrpRequest` |
| `GET` | `/api/v1/planning/production-plans/{plan_id}` | 生产作业计划详情 | `plan_id` | — | — |
| `PUT` | `/api/v1/planning/production-plans/{plan_id}` | 修改生产作业计划 | `plan_id` | — | `ProductionPlanUpdate` |
| `PATCH` | `/api/v1/planning/production-plans/{plan_id}/status` | 生产作业计划状态流转 | `plan_id` | — | `app__modules__planning__schemas__StatusUpdate` |
| `GET` | `/api/v1/planning/requisitions` | 领料单列表 | — | `status`、`plan_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/planning/requisitions` | 新增领料单 | — | — | `RequisitionCreate` |
| `GET` | `/api/v1/planning/requisitions/{req_id}` | 领料单详情 | `req_id` | — | — |
| `POST` | `/api/v1/planning/requisitions/{req_id}/cancel` | 取消领料单 | `req_id` | — | — |
| `POST` | `/api/v1/planning/requisitions/{req_id}/confirm` | 确认领料（出库） | `req_id` | — | — |
| `GET` | `/api/v1/planning/stats` | 计划模块统计 | — | — | — |

### 2.4 采购管理（`procurement`，前缀 `/api/v1/procurement`）—— 39 个操作

| 方法 | 路径 | 说明 | 路径参数 | 查询参数 | 请求体 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/procurement/evaluations` | 供应商评价列表 | — | `supplier_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/procurement/evaluations` | 新增供应商评价 | — | — | `EvaluationCreate` |
| `GET` | `/api/v1/procurement/evaluations/supplier/{supplier_id}` | 某供应商的评价记录 | `supplier_id` | — | — |
| `DELETE` | `/api/v1/procurement/evaluations/{evaluation_id}` | 删除供应商评价 | `evaluation_id` | `operator_id` | — |
| `GET` | `/api/v1/procurement/health` | procurement 模块健康检查 | — | — | — |
| `GET` | `/api/v1/procurement/materials` | 采购材料查询（supply_type = BUY 的物料） | — | `keyword` | — |
| `GET` | `/api/v1/procurement/orders` | 采购订单列表 | — | `supplier_id`、`status`、`date_from`、`date_to`、`keyword`、`page`、`page_size` | — |
| `POST` | `/api/v1/procurement/orders` | 新增采购订单 | — | — | `app__modules__procurement__schemas__OrderCreate` |
| `POST` | `/api/v1/procurement/orders/from-plan` | 由采购计划生成采购订单 | — | — | `OrderFromPlanRequest` |
| `DELETE` | `/api/v1/procurement/orders/{order_id}` | 删除采购订单（仅 DRAFT） | `order_id` | `operator_id` | — |
| `GET` | `/api/v1/procurement/orders/{order_id}` | 采购订单详情 | `order_id` | — | — |
| `PUT` | `/api/v1/procurement/orders/{order_id}` | 修改采购订单（仅 DRAFT） | `order_id` | — | `app__modules__procurement__schemas__OrderUpdate` |
| `PATCH` | `/api/v1/procurement/orders/{order_id}/status` | 采购订单状态流转 | `order_id` | — | `app__modules__procurement__schemas__StatusUpdate` |
| `GET` | `/api/v1/procurement/purchase-plans` | 采购计划列表 | — | `status`、`date_from`、`date_to`、`keyword`、`page`、`page_size` | — |
| `POST` | `/api/v1/procurement/purchase-plans` | 新增采购计划（头 + 行） | — | — | `PlanCreate` |
| `DELETE` | `/api/v1/procurement/purchase-plans/{plan_id}` | 删除采购计划（仅 DRAFT） | `plan_id` | `operator_id` | — |
| `GET` | `/api/v1/procurement/purchase-plans/{plan_id}` | 采购计划详情 | `plan_id` | — | — |
| `PUT` | `/api/v1/procurement/purchase-plans/{plan_id}` | 修改采购计划（仅 DRAFT） | `plan_id` | — | `PlanUpdate` |
| `PATCH` | `/api/v1/procurement/purchase-plans/{plan_id}/status` | 采购计划状态流转 | `plan_id` | — | `app__modules__procurement__schemas__StatusUpdate` |
| `GET` | `/api/v1/procurement/receipts` | 到货登记列表 | — | `purchase_order_id`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/procurement/receipts` | 新增到货登记 | — | — | `ReceiptCreate` |
| `GET` | `/api/v1/procurement/receipts/{receipt_id}` | 到货单详情 | `receipt_id` | — | — |
| `POST` | `/api/v1/procurement/receipts/{receipt_id}/cancel` | 取消到货单（仅 DRAFT） | `receipt_id` | `operator_id` | — |
| `POST` | `/api/v1/procurement/receipts/{receipt_id}/confirm` | 确认到货（调用库存入库） | `receipt_id` | `operator_id` | — |
| `GET` | `/api/v1/procurement/reports/orders` | 报表：采购订单及到货进度 | — | — | — |
| `GET` | `/api/v1/procurement/reports/pending` | 报表：未到货 | — | — | — |
| `GET` | `/api/v1/procurement/reports/plans` | 报表：采购计划及执行 | — | — | — |
| `GET` | `/api/v1/procurement/reports/receipts` | 报表：到货记录 | — | `date_from`、`date_to` | — |
| `GET` | `/api/v1/procurement/reports/supplier-evaluation` | 报表：供应商评分汇总 | — | — | — |
| `GET` | `/api/v1/procurement/stats` | 采购统计 | — | — | — |
| `GET` | `/api/v1/procurement/supplier-materials` | 供应商-物料关系列表 | — | `supplier_id`、`material_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/procurement/supplier-materials` | 新增供应商-物料关系 | — | — | `SupplierMaterialCreate` |
| `DELETE` | `/api/v1/procurement/supplier-materials/{link_id}` | 删除供应商-物料关系 | `link_id` | `operator_id` | — |
| `PUT` | `/api/v1/procurement/supplier-materials/{link_id}` | 修改供应商-物料关系 | `link_id` | — | `SupplierMaterialUpdate` |
| `GET` | `/api/v1/procurement/suppliers` | 供应商列表 | — | `keyword`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/procurement/suppliers` | 新增供应商 | — | — | `SupplierCreate` |
| `GET` | `/api/v1/procurement/suppliers/{supplier_id}` | 供应商详情 | `supplier_id` | — | — |
| `PUT` | `/api/v1/procurement/suppliers/{supplier_id}` | 修改供应商 | `supplier_id` | — | `SupplierUpdate` |
| `PATCH` | `/api/v1/procurement/suppliers/{supplier_id}/status` | 供应商启用/停用（不物理删除） | `supplier_id` | — | `app__modules__procurement__schemas__StatusUpdate` |

### 2.5 库存管理（`inventory`，前缀 `/api/v1/inventory`）—— 44 个操作

| 方法 | 路径 | 说明 | 路径参数 | 查询参数 | 请求体 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/inventory/balances` | 实时库存列表 | — | `material_id`、`warehouse_id`、`keyword`、`page`、`page_size` | — |
| `GET` | `/api/v1/inventory/balances/available` | 可用量查询 | — | `material_id`、`warehouse_id` | — |
| `GET` | `/api/v1/inventory/health` | inventory 模块健康检查（占位） | — | — | — |
| `POST` | `/api/v1/inventory/import/initial-stock/confirm` | 期初库存导入确认 | — | — | `InitialStockImportRequest` |
| `POST` | `/api/v1/inventory/import/initial-stock/preview` | 期初库存导入预览 | — | — | `InitialStockImportRequest` |
| `GET` | `/api/v1/inventory/locations` | 库位列表 | — | `warehouse_id`、`keyword`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/inventory/locations` | 新增库位 | — | — | `LocationCreate` |
| `DELETE` | `/api/v1/inventory/locations/{location_id}` | 删除库位 | `location_id` | `operator_id` | — |
| `PUT` | `/api/v1/inventory/locations/{location_id}` | 修改库位 | `location_id` | — | `LocationUpdate` |
| `PATCH` | `/api/v1/inventory/locations/{location_id}/status` | 启用/停用库位 | `location_id` | — | `app__modules__inventory__schemas__StatusUpdate` |
| `GET` | `/api/v1/inventory/reorder-rules` | 订货点规则列表 | — | `status`、`material_id`、`warehouse_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/inventory/reorder-rules` | 新增订货点规则 | — | — | `ReorderRuleCreate` |
| `GET` | `/api/v1/inventory/reorder-rules/suggestions` | 补库建议 | — | — | — |
| `PUT` | `/api/v1/inventory/reorder-rules/{rule_id}` | 修改订货点规则 | `rule_id` | — | `ReorderRuleUpdate` |
| `PATCH` | `/api/v1/inventory/reorder-rules/{rule_id}/status` | 启用/停用订货点规则 | `rule_id` | — | `app__modules__inventory__schemas__StatusUpdate` |
| `GET` | `/api/v1/inventory/replenishment-requests` | 补库需求列表 | — | `status`、`source_type`、`material_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/inventory/replenishment-requests` | 新增补库需求 | — | — | `ReplenishmentRequestCreate` |
| `POST` | `/api/v1/inventory/replenishment-requests/generate-from-reorder-rules` | 按订货点批量生成补库需求 | — | `operator_id` | — |
| `GET` | `/api/v1/inventory/replenishment-requests/{request_id}` | 补库需求详情 | `request_id` | — | — |
| `POST` | `/api/v1/inventory/replenishment-requests/{request_id}/cancel` | 取消补库需求 | `request_id` | `operator_id` | — |
| `POST` | `/api/v1/inventory/replenishment-requests/{request_id}/confirm` | 确认补库需求 | `request_id` | `operator_id` | — |
| `GET` | `/api/v1/inventory/reports/flow-summary` | 出入库汇总报表 | — | `date_from`、`date_to` | — |
| `GET` | `/api/v1/inventory/reports/low-stock` | 低库存/缺料报表 | — | — | — |
| `GET` | `/api/v1/inventory/reports/stock-summary` | 库存汇总报表 | — | `warehouse_id` | — |
| `GET` | `/api/v1/inventory/stats` | 库存模块统计 | — | — | — |
| `POST` | `/api/v1/inventory/stock/decrease` | 手工出库 | — | — | `StockDecreaseCreate` |
| `POST` | `/api/v1/inventory/stock/increase` | 手工入库 | — | — | `StockIncreaseCreate` |
| `GET` | `/api/v1/inventory/stocktakes` | 盘点单列表 | — | `warehouse_id`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/inventory/stocktakes` | 新增盘点单 | — | — | `StocktakeCreate` |
| `GET` | `/api/v1/inventory/stocktakes/{stocktake_id}` | 盘点单详情 | `stocktake_id` | — | — |
| `POST` | `/api/v1/inventory/stocktakes/{stocktake_id}/cancel` | 取消盘点 | `stocktake_id` | `operator_id` | — |
| `POST` | `/api/v1/inventory/stocktakes/{stocktake_id}/confirm` | 确认盘点 | `stocktake_id` | `operator_id` | — |
| `GET` | `/api/v1/inventory/transactions` | 库存流水列表 | — | `transaction_type`、`material_id`、`warehouse_id`、`source_type`、`date_from`、`date_to`、`source_no`、`keyword`、`page`、`page_size` | — |
| `GET` | `/api/v1/inventory/transactions/{transaction_id}` | 库存流水详情 | `transaction_id` | — | — |
| `GET` | `/api/v1/inventory/transfers` | 移库单列表 | — | `status`、`from_warehouse_id`、`page`、`page_size` | — |
| `POST` | `/api/v1/inventory/transfers` | 新增移库单 | — | — | `TransferCreate` |
| `GET` | `/api/v1/inventory/transfers/{transfer_id}` | 移库单详情 | `transfer_id` | — | — |
| `POST` | `/api/v1/inventory/transfers/{transfer_id}/cancel` | 取消移库 | `transfer_id` | `operator_id` | — |
| `POST` | `/api/v1/inventory/transfers/{transfer_id}/confirm` | 确认移库 | `transfer_id` | `operator_id` | — |
| `GET` | `/api/v1/inventory/warehouses` | 仓库列表 | — | `keyword`、`status`、`page`、`page_size` | — |
| `POST` | `/api/v1/inventory/warehouses` | 新增仓库 | — | — | `WarehouseCreate` |
| `GET` | `/api/v1/inventory/warehouses/{warehouse_id}` | 仓库详情 | `warehouse_id` | — | — |
| `PUT` | `/api/v1/inventory/warehouses/{warehouse_id}` | 修改仓库 | `warehouse_id` | — | `WarehouseUpdate` |
| `PATCH` | `/api/v1/inventory/warehouses/{warehouse_id}/status` | 启用/停用仓库 | `warehouse_id` | — | `app__modules__inventory__schemas__StatusUpdate` |

### 2.6 应用级

| 方法 | 路径 | 说明 | 路径参数 | 查询参数 | 请求体 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/health` | 应用健康检查 | — | — | — |

## 三、关键流程接口

这些接口是课程演示主链路的关键节点，行为细节见 [`../user-guide/course-scenario-guide.md`](../user-guide/course-scenario-guide.md)。

### 3.1 课程数据导入（两段式：先预览、再确认）

| 步骤 | 接口 | 说明 |
| --- | --- | --- |
| 1 | `POST /api/v1/system/import/materials/preview` | 预览课程物料（转椅成品/半成品/采购件） |
| 2 | `POST /api/v1/system/import/materials/confirm` | 确认导入物料 |
| 3 | `POST /api/v1/system/import/bom/preview` | 预览课程 BOM（多层结构） |
| 4 | `POST /api/v1/system/import/bom/confirm` | 确认导入 BOM |
| 5 | `POST /api/v1/planning/mps/import/preview` | 预览附录 1 主生产计划 |
| 6 | `POST /api/v1/planning/mps/import/confirm` | 确认导入 MPS |
| 7 | `POST /api/v1/inventory/import/initial-stock/preview` | 预览期初库存 |
| 8 | `POST /api/v1/inventory/import/initial-stock/confirm` | 确认导入期初库存（写入真实库存流水） |

> 导入源由 `source` 参数指定；服务端内置的课程数据源标识为
> `course_chair_case`（`planning/service.py::COURSE_CASE_SOURCE`），
> 未知标识返回 system 模块 `1011`。

### 3.2 MRP 运算与分流

| 接口 | 说明 |
| --- | --- |
| `POST /api/v1/planning/mrp/run` | 执行 MRP：BOM 逐层展开、净需求计算（`net = max(毛需求+安全库存-可用库存, 0)`）、按 `supply_type` 分流 MAKE/BUY |
| `GET /api/v1/planning/mrp/runs` | MRP 批次列表 |
| `GET /api/v1/planning/mrp/runs/{run_id}` | 批次详情（含结果） |
| `GET /api/v1/planning/mrp/runs/{run_id}/results` | 批次结果（分页） |
| `GET /api/v1/planning/mrp/runs/{run_id}/explain` | 计算明细（可解释性） |
| `POST /api/v1/planning/mrp/runs/{run_id}/create-production-plans` | 把 MAKE 需求下达为生产作业计划 |
| `POST /api/v1/planning/mrp/runs/{run_id}/create-purchase-plan` | 把 BUY 需求下达为采购计划（经 `procurement.contract`） |

### 3.3 库存联动（调用方 → `inventory.contract`）

| 接口 | 联动动作 |
| --- | --- |
| `POST /api/v1/procurement/receipts/{receipt_id}/confirm` | `increase_stock`（`source_type=PURCHASE_RECEIPT`） |
| `POST /api/v1/planning/requisitions/{req_id}/confirm` | `decrease_stock`（`source_type=MATERIAL_REQUISITION`） |
| `POST /api/v1/planning/completion-reports/{report_id}/confirm` | `increase_stock`（`source_type=PRODUCTION_COMPLETION`） |
| `POST /api/v1/sales/shipments/{shipment_id}/confirm` | `decrease_stock`（`source_type=SALES_SHIPMENT`） |
| `POST /api/v1/sales/returns/{return_id}/confirm` | `increase_stock`（`source_type=SALES_RETURN`） |
| `POST /api/v1/inventory/transfers/{transfer_id}/confirm` | `TRANSFER_OUT` + `TRANSFER_IN` |
| `POST /api/v1/inventory/stocktakes/{stocktake_id}/confirm` | `ADJUST`（差异调整） |
| `POST /api/v1/inventory/replenishment-requests/{request_id}/confirm` | `REORDER` → `procurement.contract`；`PRODUCTION` → `planning.contract` |

### 3.4 状态流转

除「确认 / 取消」类动作接口外，多数单据提供统一的状态流转接口：

```
PATCH /api/v1/<module>/<resource>/{id}/status   body: { "status": "CONFIRMED" }
```

允许的状态集合与流转规则见 [`../database/data-dictionary.md`](../database/data-dictionary.md) 第八节。

## 四、已知例外与注意事项

1. **无鉴权**：所有接口都不校验 `Authorization`；`core/security.py` 仅预留
   `HTTPBearer(auto_error=False)`。`POST /api/v1/system/auth/login` 为简化版登录。
2. **模块健康检查是占位接口**：`GET /api/v1/{module}/health` 一律返回
   `{module, status: "up"}`（`shared/types.py::HealthData`），不反映真实依赖状态；
   其中 procurement 的 `health` 摘要未带「占位」字样，其余四个模块带「（占位）」。
3. **删除语义**：物料 / 客户 / 供应商 / 仓库 / 库位等基础数据以 `status` 接口停用，
   不物理删除；被引用的数据删除会返回 `1009` / `5007` 等错误。
4. **OpenAPI 文档**：应用启动后可直接访问 `/docs`（Swagger UI）与 `/openapi.json` 核对本文。
