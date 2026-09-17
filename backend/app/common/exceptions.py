"""统一异常与错误响应。

业务代码只需要 `raise BusinessException(code=4001, message="库存不足")`，
由本文件注册的处理器统一转换成 `{ code, message, data }` 结构。

错误码分段约定（各模块在此范围内自行细分，避免冲突）：
- 0        成功
- 1000~1999 system 模块
- 2000~2999 sales 模块
- 3000~3999 planning 模块
- 4000~4999 procurement 模块
- 5000~5999 inventory 模块
- 9000~9999 通用/框架级错误
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.response import error

# 通用错误码
CODE_HTTP_ERROR: int = 9001
CODE_VALIDATION_ERROR: int = 9002
CODE_INTERNAL_ERROR: int = 9000


class BusinessException(Exception):
    """业务异常。业务代码抛出后由统一处理器转换为标准错误响应。"""

    def __init__(self, code: int, message: str, data: object = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """把统一异常处理器注册到 FastAPI 应用上。"""

    @app.exception_handler(BusinessException)
    async def _business_exception_handler(_: Request, exc: BusinessException) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content=error(exc.code, exc.message, exc.data).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error(CODE_VALIDATION_ERROR, "请求参数校验失败", exc.errors()).model_dump(),
        )

    # 使用 Starlette 的 HTTPException 基类，可同时覆盖 FastAPI 抛出的 HTTPException
    # 与框架内置的 404 / 405 等错误，保证所有错误响应结构一致。
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error(CODE_HTTP_ERROR, str(exc.detail)).model_dump(),
        )
