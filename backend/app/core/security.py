"""安全基础设施（占位）。

**当前不实现任何登录、鉴权、权限逻辑。**

后续由 system 模块负责人在本文件基础上补充：
- 密码哈希与校验（如 passlib + bcrypt）
- JWT 的签发与解析
- 获取当前登录用户的依赖项（CurrentUser）

约定：其它模块需要"当前用户"时，只能依赖 system 模块对外暴露的认证依赖项 / API Contract，
不要各自实现一套。
"""

from fastapi.security import HTTPBearer

# 预留的 Bearer 认证方案，仅用于让后续鉴权接口的 OpenAPI 文档结构统一。
# auto_error=False：当前阶段不强制携带 Authorization 头。
bearer_scheme = HTTPBearer(auto_error=False)
