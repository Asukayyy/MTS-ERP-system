"""统一响应规范。

所有接口（含健康检查）统一返回：

```json
{ "code": 0, "message": "success", "data": ... }
```

出错时：

```json
{ "code": 4001, "message": "库存不足", "data": null }
```

约定：`code == 0` 表示成功，非 0 表示失败。前端 axios 拦截器据此统一判断（见 `frontend/src/utils/request.ts`）。
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

# 成功码，全系统统一
SUCCESS_CODE: int = 0
SUCCESS_MESSAGE: str = "success"


class ApiResponse(BaseModel, Generic[T]):
    """统一响应体。"""

    code: int = Field(default=SUCCESS_CODE, description="业务状态码，0 表示成功")
    message: str = Field(default=SUCCESS_MESSAGE, description="提示信息")
    data: Optional[T] = Field(default=None, description="业务数据，失败时为 null")


def success(data: Any = None, message: str = SUCCESS_MESSAGE) -> ApiResponse[Any]:
    """构造成功响应。"""
    return ApiResponse(code=SUCCESS_CODE, message=message, data=data)


def error(code: int, message: str, data: Any = None) -> ApiResponse[Any]:
    """构造失败响应。"""
    return ApiResponse(code=code, message=message, data=data)
