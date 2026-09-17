"""分页基础设施。

**只提供分页的数据结构与参数依赖，不实现任何业务分页查询逻辑。**

各模块在实现自己的列表接口时按此结构返回，保证前端分页体验一致：

```python
@router.get("/orders", response_model=ApiResponse[PageData[OrderOut]])
def list_orders(page: PageParams = Depends(PageParams.as_dependency)) -> ...:
    ...
```

返回结构固定为 `{ page, page_size, total, items }`。
"""

from typing import Generic, List, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")

# 分页参数保护值，避免一次拉全表
DEFAULT_PAGE: int = 1
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 200


class PageParams(BaseModel):
    """分页查询参数。"""

    page: int = Field(default=DEFAULT_PAGE, ge=1, description="页码，从 1 开始")
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"
    )

    @property
    def offset(self) -> int:
        """SQL 查询偏移量。"""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """SQL 查询条数。"""
        return self.page_size

    @staticmethod
    def as_dependency(
        page: int = Query(DEFAULT_PAGE, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(
            DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"
        ),
    ) -> "PageParams":
        """FastAPI 依赖工厂，用法：`params: PageParams = Depends(PageParams.as_dependency)`。"""
        return PageParams(page=page, page_size=page_size)


class PageData(BaseModel, Generic[T]):
    """分页返回结构。"""

    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total: int = Field(description="总记录数")
    items: List[T] = Field(default_factory=list, description="当前页数据")
