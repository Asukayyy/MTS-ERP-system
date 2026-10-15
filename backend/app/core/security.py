"""安全基础设施：密码哈希、登录凭证签发与校验、鉴权 / 授权依赖。

凭证方案：HMAC-SHA256 签名的自包含 token，格式 `<payload>.<signature>`（均为 base64url）。
payload 含 `sub`（用户ID）与 `exp`（过期时间戳）。

选择自包含签名而非落库 token，是为了**不在团队共享库中新增表**——共享库的任何结构变更
都会影响全部成员，需要全员同步执行补丁。本方案无状态、零第三方依赖。

约定：其它模块需要"当前用户"时，只能依赖本文件对外暴露的依赖项，不要各自实现一套：

- `get_current_user`：解析 `Authorization: Bearer <token>`，失败抛 401；
- `get_optional_user`：同上但不抛错，未登录返回 None（仅供公开接口旁路使用）；
- `require_permission`：按权限编码拦截的依赖项，缺失抛 403；
- `require_route_permission`：按"METHOD + 路由模板"查策略表拦截的路由级依赖（fail-closed）。
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Callable, Iterable, Mapping, Optional, Set

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.modules.system import models, repository as system_repository
from app.shared.enums import RecordStatus

# 预留的 Bearer 认证方案。auto_error=False：由本文件自行抛出统一结构的 401，
# 避免框架默认返回与项目响应规范不一致的错误体。
bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHORIZED_MESSAGE: str = "未登录或登录已过期，请重新登录"
FORBIDDEN_MESSAGE: str = "当前身份无权执行该操作"


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=UNAUTHORIZED_MESSAGE,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str = FORBIDDEN_MESSAGE) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# --------------------------------------------------------------------------- #
# 密码
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """密码哈希（与既有 service / 种子脚本保持一致的 sha256 十六进制）。"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    """校验明文密码与库中哈希是否一致（常量时间比较）。"""
    return hmac.compare_digest(hash_password(password), password_hash or "")


# --------------------------------------------------------------------------- #
# 登录凭证
# --------------------------------------------------------------------------- #
def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str) -> str:
    digest = hmac.new(
        settings.AUTH_SECRET_KEY.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def create_access_token(user_id: int) -> str:
    """签发登录凭证。"""
    payload = {
        "sub": int(user_id),
        "exp": int(time.time()) + settings.AUTH_TOKEN_EXPIRE_MINUTES * 60,
    }
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def parse_access_token(token: str) -> Optional[int]:
    """校验签名与有效期；合法则返回用户ID，否则返回 None。"""
    payload_b64, separator, signature = token.partition(".")
    if not separator or not payload_b64 or not signature:
        return None
    if not hmac.compare_digest(_sign(payload_b64), signature):
        return None
    try:
        payload = json.loads(_b64decode(payload_b64))
        expire_at = int(payload["exp"])
        subject = int(payload["sub"])
    except (ValueError, TypeError, KeyError):
        # base64 解码失败（binascii.Error）、JSON 非法、字段缺失或类型不符
        return None
    if expire_at < int(time.time()):
        return None
    return subject


# --------------------------------------------------------------------------- #
# 当前用户与权限
# --------------------------------------------------------------------------- #
def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.SysUser]:
    """解析凭证并返回用户；未携带 / 非法 / 已停用时返回 None，不抛异常。"""
    if credentials is None or not credentials.credentials:
        return None
    user_id = parse_access_token(credentials.credentials)
    if user_id is None:
        return None
    user = db.get(models.SysUser, user_id)
    if user is None or user.status != RecordStatus.ACTIVE.value:
        return None
    return user


def get_current_user(
    user: Optional[models.SysUser] = Depends(get_optional_user),
) -> models.SysUser:
    """强制登录：未登录 / 凭证失效抛 401。"""
    if user is None:
        raise _unauthorized()
    return user


def get_permission_codes(db: Session, user: models.SysUser) -> Set[str]:
    """用户经由角色获得的权限编码集合。"""
    role_ids = [role.id for role in user.roles]
    if not role_ids:
        return set()
    return {permission.perm_code for permission in system_repository.list_role_permissions(db, role_ids)}


def require_permission(*permission_codes: str) -> Callable[..., models.SysUser]:
    """生成"需持有其中任意一个权限编码"的依赖项。

    用法：`user: models.SysUser = Depends(require_permission("system:user"))`。
    不传编码时只要求登录。
    """

    def dependency(
        user: models.SysUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> models.SysUser:
        if permission_codes and not get_permission_codes(db, user).intersection(permission_codes):
            raise _forbidden()
        return user

    return dependency


def require_route_permission(
    policy: Mapping[str, Optional[Iterable[str]]],
    *,
    public: Iterable[str] = (),
    route_prefix: str = "",
) -> Callable[[Request, Optional[models.SysUser], Session], None]:
    """生成路由级鉴权依赖：按 `METHOD 路由模板` 查策略表。

    - `policy[key] is None`：该接口只要求登录；
    - `policy[key]` 为权限编码集合：需持有其中任意一个；
    - `key` 命中 `public`：完全放行，不要求登录；
    - **未登记的路由一律拒绝**（fail-closed），避免漏登记导致接口意外对外开放；
      配合模块内的启动期完整性自检（见 `system/router.py` 末尾）可提前暴露漏登记。

    `route_prefix` 为模块挂载前缀（如 `/api/v1/system`），会从实际路由路径中剥掉，
    以便策略表的键只写模块内相对路径，与自检逻辑使用同一套键。
    """

    public_keys = set(public)

    def _key(request: Request) -> str:
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        if route_prefix and path.startswith(route_prefix):
            path = path[len(route_prefix):] or "/"
        return f"{request.method} {path}"

    def dependency(
        request: Request,
        user: Optional[models.SysUser] = Depends(get_optional_user),
        db: Session = Depends(get_db),
    ) -> None:
        key = _key(request)
        if key in public_keys:
            return
        if user is None:
            raise _unauthorized()

        if key not in policy:
            raise _forbidden(f"接口未登记权限策略：{key}")
        required = policy[key]
        if required and not get_permission_codes(db, user).intersection(required):
            raise _forbidden()

    return dependency