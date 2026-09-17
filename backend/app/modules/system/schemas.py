"""system 模块 Pydantic Schema。

当前只有占位健康检查响应。
业务请求/响应模型请在本文件中定义，命名建议：
- `XxxCreate` 新增入参
- `XxxUpdate` 修改入参
- `XxxOut` 出参
"""

from app.common.response import ApiResponse
from app.shared.types import HealthData

# 占位健康检查响应，与其它四个模块保持完全一致的返回结构
HealthResponse = ApiResponse[HealthData]
