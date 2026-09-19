# API 规范

## 一、统一前缀

所有后端接口统一挂载在 `/api/v1` 下，按模块划分：

| 模块 | 前缀 |
| --- | --- |
| system | `/api/v1/system` |
| sales | `/api/v1/sales` |
| planning | `/api/v1/planning` |
| procurement | `/api/v1/procurement` |
| inventory | `/api/v1/inventory` |

前缀由 `backend/app/main.py` 统一注入，模块的 `router.py` 中**只写相对路径**。例如：

```python
# backend/app/modules/sales/router.py
@router.get("/orders")          # 实际路径 → /api/v1/sales/orders
def list_orders():
    ...
```

应用级接口不加模块前缀：

| 接口 | 说明 |
| --- | --- |
| `GET /health` | 应用健康检查 |
| `GET /docs` | Swagger 文档 |
| `GET /openapi.json` | OpenAPI 描述 |

## 二、统一响应结构

**所有接口**（包括健康检查与错误）统一返回：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | int | 业务状态码，**0 表示成功**，非 0 表示失败 |
| `message` | string | 提示信息，成功固定为 `success` |
| `data` | any | 业务数据，失败时为 `null` |

后端用法：

```python
from app.common.response import ApiResponse
from app.common.pagination import PageData

@router.get("/orders", response_model=ApiResponse[PageData[OrderOut]])
def list_orders(params: PageParams = Depends(PageParams.as_dependency)):
    ...
```

前端用法（`@/utils/request.ts` 已自动拆包，业务代码直接拿 `data`）：

```ts
import { get } from '@/utils/request'

const data = await get<HealthData>('/sales/health')
```

## 三、错误响应

```json
{
  "code": 4001,
  "message": "库存不足",
  "data": null
}
```

业务代码抛出异常即可，由统一处理器转换：

```python
from app.common.exceptions import BusinessException

raise BusinessException(code=4001, message="库存不足")
```

### 错误码分段

| 区段 | 归属 |
| --- | --- |
| `0` | 成功 |
| `1000~1999` | system |
| `2000~2999` | sales |
| `3000~3999` | planning |
| `4000~4999` | procurement |
| `5000~5999` | inventory |
| `9000~9999` | 通用 / 框架级（`9000` 内部错误、`9001` HTTP 错误、`9002` 参数校验失败） |

各模块在自己区段内自行细分，避免与他人冲突。

## 四、分页规范

请求参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 1 | 页码，从 1 开始 |
| `page_size` | int | 20 | 每页条数，最大 200 |

响应 `data` 结构固定为：

```json
{
  "page": 1,
  "page_size": 20,
  "total": 135,
  "items": []
}
```

后端结构定义在 `backend/app/common/pagination.py`（`PageParams` / `PageData`），
前端类型定义在 `frontend/src/types/api.ts`（`PageQuery` / `PageData`）。

## 五、命令规范

| 方法 | 用途 |
| --- | --- |
| `GET` | 查询（**不得产生副作用**） |
| `POST` | 新增 |
| `PUT` | 整体更新 |
| `PATCH` | 局部更新 |
| `DELETE` | 删除 |

路径使用**复数名词**，避免动词：`/api/v1/sales/orders`、`/api/v1/inventory/transactions`。

## 六、当前已实现的接口

当前共 **167 个路径 / 223 个操作**，完整清单见 [api-contract.md](api-contract.md)（由
`create_app().openapi()` 导出，可逐条核对）。

以下是应用级与各模块的**占位健康检查**，仅用于验证模块路由注册成功：

| 接口 | 返回 `data` |
| --- | --- |
| `GET /health` | `{"name": "BH-ERP", "version": "0.1.0", "status": "ok"}` |
| `GET /api/v1/system/health` | `{"module": "system", "status": "up"}` |
| `GET /api/v1/sales/health` | `{"module": "sales", "status": "up"}` |
| `GET /api/v1/planning/health` | `{"module": "planning", "status": "up"}` |
| `GET /api/v1/procurement/health` | `{"module": "procurement", "status": "up"}` |
| `GET /api/v1/inventory/health` | `{"module": "inventory", "status": "up"}` |

> 这些健康检查**仅用于证明路由注册成功**，固定返回 `up`（不反映真实依赖状态），
> 请勿在其上扩展任何业务逻辑。

## 七、接口文档

启动后端后访问：

- Swagger UI：http://127.0.0.1:8000/docs
- OpenAPI JSON：http://127.0.0.1:8000/openapi.json
