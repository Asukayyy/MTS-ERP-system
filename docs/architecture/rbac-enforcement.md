# RBAC 权限落地现状与改造方案

> 结论先行：**当前 RBAC 只有"数据"，没有"执行"。** 角色、权限树、角色-权限绑定、分配界面都是真实可用的，
> 但没有任何一处拿它去拦截访问——后端接口不鉴权，前端只判断"有没有登录"。
>
> 本文档为**讨论稿**，供团队确认方向后再动代码。

## 一、现状核查（附证据）

### 1.1 后端接口完全没有鉴权

登录接口自己声明不签发凭证：

- [router.py L740-L745](../backend/app/modules/system/router.py) —— `POST /auth/login` 的 docstring 写明
  「简化说明：本接口**不签发 JWT / Token**」，只把 `user / roles / permissions` 打包返回。

全仓库检索不到任何鉴权依赖：没有 `get_current_user`、没有 `require_permission`、没有 OAuth2 / JWT 解码、
`main.py` 也没有鉴权中间件（只有 CORS）。

实测证据（不带任何 header 直接请求）：

```
GET http://127.0.0.1:8000/api/v1/system/users?page=1&page_size=5
→ 200，返回账号列表（含登录名、显示名、工号、角色）
```

即：**任何人都能读写任意接口，包括账号与角色管理。**

### 1.2 前端只判断"有没有登录"，不看权限

- [router/index.ts L30-L43](../frontend/src/router/index.ts) —— 守卫仅检查
  `localStorage.getItem('bh-erp-user')` 是否存在；该键是登录页明文写入的 JSON，手工伪造即可进入全部页面。
- [AppSidebar.vue L20](../frontend/src/layouts/components/AppSidebar.vue) —— 菜单来自静态的
  `layouts/menu.ts`，与权限无关。
- 全前端检索不到 `hasPermission` / `v-permission` / 按权限过滤路由的代码；登录返回的 `permissions`
  被存进 localStorage 后再没被读取过。
- `permissions` 唯一的实际用途是角色管理页：`role/index.vue` 勾选后调用
  `POST /system/roles/{id}/permissions` 写库——**能写，但不生效**。

### 1.3 真实可用的部分

| 能力 | 状态 |
| --- | --- |
| 数据模型 `sys_role` / `sys_permission` / `sys_user_role` / `sys_role_permission` | 已实现 |
| 权限树与角色绑定种子（幂等，启动写入） | 已实现 |
| 登录校验用户名密码、返回角色与权限 | 已实现 |
| 角色管理页分配权限（写库） | 已实现 |
| 接口鉴权 / 权限校验 / 前端按权限渲染 | **未实现** |

## 二、权限树 `path` 与真实路由的对齐情况

### 2.1 先纠正一个前提：前端过滤不该按 `path` 匹配

`path` 不是前端过滤的必要条件。正确做法是在路由上直接标注所需**权限码**：

```ts
{ path: 'sales/order', name: 'SalesOrder', meta: { title: '销售订单', perm: 'sales:order' } }
```

守卫与菜单过滤都用「登录返回的权限码集合」比对 `meta.perm`。这样：

- `path` 与真实路由是否一致**不影响功能**，路由将来改名也不会破坏权限判断；
- `path` 退化为权限管理界面上的展示文案，只影响可读性。

因此"13 条 path 对不上"并非阻塞项——上一版结论把严重性说过头了，此处更正。

### 2.2 但仍分三类问题，逐一处置

**第一类：有对应页面、`path` 写错的 9 条 —— 已修正到 `seed.py`**

| 权限码 | 原 path | 修正为 |
| --- | --- | --- |
| `system:org`（含 `system:org:manage`） | `/system/org` | `/system/organization` |
| `sales:demand` | `/sales/demand` | `/sales/forecast` |
| `sales:shipping` | `/sales/shipping` | `/sales/shipment` |
| `planning:schedule` | `/planning/schedule` | `/planning/work-plan` |
| `planning:picking` | `/planning/picking` | `/planning/requisition` |
| `planning:finish` | `/planning/finish` | `/planning/completion` |
| `procurement:arrival` | `/procurement/arrival` | `/procurement/receipt` |
| `inventory:stock` | `/inventory/stock` | `/inventory/balance` |
| `inventory:ledger` | `/inventory/ledger` | `/inventory/transaction` |

**第二类：标成 MENU 但系统里没有这个页面 —— 4 条，需要决策**

`sales:stock`（可发货量查询）、`planning:qc`（完工质检）、`procurement:demand`（采购需求）、
`procurement:qc`（到货质检）——没有可对齐的路由。三种处置：① 建页面；② 并入相邻页面的操作权限
（如 `procurement:qc` 挂到到货页做按钮权限）；③ 保留为操作权限、不参与菜单渲染。倾向 ② + ③。

**第三类：有页面但没有权限码 —— 14 个，需要新编码**

上一版漏了 3 个（`system/personnel`、`sales/forecast`、`planning/demand`），更正后的完整清单：

| 真实路由 | 建议权限码 | 模块 | 建议挂给角色 |
| --- | --- | --- | --- |
| `system/personnel` | `system:personnel` | system | ADMIN、DEPT_HEAD、DIRECTOR |
| `dashboard` | 不需要（所有登录用户可见） | — | — |
| `sales/customer` | `sales:customer` | sales | SALES、DEPT_HEAD |
| `sales/return` | `sales:return` | sales | SALES、DEPT_HEAD |
| `planning/demand` | `planning:demand` | planning | PLAN、DEPT_HEAD |
| `procurement/supplier` | `procurement:supplier` | procurement | PURCHASE、DEPT_HEAD |
| `procurement/supplier-material` | `procurement:supplier-material` | procurement | PURCHASE、DEPT_HEAD |
| `procurement/evaluation` | `procurement:evaluation` | procurement | PURCHASE、DEPT_HEAD |
| `procurement/report` | `procurement:report` | procurement | PURCHASE、DEPT_HEAD、FINANCE |
| `inventory/transfer` | `inventory:transfer` | inventory | INVENTORY、DEPT_HEAD |
| `inventory/stocktake` | `inventory:stocktake` | inventory | INVENTORY、DEPT_HEAD |
| `inventory/reorder` | `inventory:reorder` | inventory | INVENTORY、DEPT_HEAD |
| `inventory/replenishment` | `inventory:replenishment` | inventory | INVENTORY、DEPT_HEAD |

> "建议挂给角色"一列会改动共享库里各角色的权限，属跨模块的角色设计，
> 需各模块 owner 确认后再改，不建议单方面决定。

### 2.3 seed 幂等的坑：改了种子也不会更新共享库

`seed_roles_and_permissions` 对已存在的 `perm_code` 是**跳过**（`if existing is not None: continue`），
所以本次改的 9 条 `path` 只对全新安装生效，共享库里已有的行仍是旧值。
若确需同步历史数据，要额外写一次性 `UPDATE sys_permission SET path=... WHERE perm_code=...` 补丁脚本；
若采用 2.1 的按权限码匹配方案，这步可以不做。

## 三、需要团队拍板的四个决策点

1. **凭证方案**
   - A. 简化不透明 token：新增 `sys_user_token` 表，登录写入随机串并有过期时间，请求带
     `Authorization: Bearer <token>`。不引入新依赖，适合课程项目。
   - B. 标准 JWT：引入 `pyjwt` + 配置 `SECRET_KEY`，无状态、可带权限声明。
   - 倾向：**A**，改动最小且可解释。
2. **权限校验粒度**
   - A. 只校验"功能码"（如 `planning:mrp`）：能看即能改。
   - B. 功能码 + 操作码（如 `planning:mrp:manage`）：查看与写操作分离。
   - 倾向：**B**，因为种子权限树里 `:manage` 类 ACTION 权限已经存在，不用浪费。
3. **是否实现"数据范围"**（角色描述里写的"本组织 / 仅本人"）
   - 这是独立于功能权限的第三层，工作量最大，需要各业务模块改造查询条件。
   - 倾向：**本期不做**，只在文档里标注为遗留项。
4. **无权限时的前端表现**
   - 隐藏菜单（推荐）／显示但置灰／直接跳 403 页。
   - 需要新增一个 403 页面（目前只有 `NotFound`）。

## 四、改造清单

### 4.1 后端

| # | 内容 | 位置 |
| --- | --- | --- |
| 1 | 登录签发 token（方案 A 则新增 `sys_user_token` 表 + 过期时间） | `system/router.py` `system/service.py` |
| 2 | 新增鉴权依赖 `get_current_user`：解析 `Authorization`，校验 token 有效性与用户状态 | 建议 `app/core/security.py` |
| 3 | 新增权限依赖工厂 `require_perm(*codes)`：查当前用户权限码集合，缺失则返回 403 | 同上 |
| 4 | `system` 模块优先挂保护：账号 / 角色 / 权限 / 组织 / 员工 / 操作日志的写接口 | `system/router.py` |
| 5 | 各业务模块接口逐个挂功能码（**需各模块 owner 配合**） | `sales` / `planning` / `procurement` / `inventory` router |
| 6 | 保持公开：`/auth/login`、`/auth/register`、`/auth/register-roles` | `system/router.py` |
| 7 | 统一异常：401（未登录）与 403（无权限）走既有 `BusinessException` 体系 | `app/common` |

### 4.2 前端

| # | 内容 | 位置 |
| --- | --- | --- |
| 1 | 请求拦截器加 `Authorization` 头；401 已有清除登录态逻辑，补齐跳转 | `utils/request.ts` |
| 2 | 登录后持久化 token 与权限码集合（不要只存展示用字段） | `views/login/index.vue` |
| 3 | 路由 `meta.perm` 标注所需权限码，`beforeEach` 校验并跳 403 | `router/routes.ts` `router/index.ts` |
| 4 | 侧边栏 `menu.ts` 每项加 `perm`，按当前权限过滤渲染 | `layouts/menu.ts` `AppSidebar.vue` |
| 5 | 新增 `v-permission` 指令用于按钮级控制（新增 / 编辑 / 删除 / 审批） | 建议 `directives/permission.ts` |
| 6 | 新增无权限页 | `views/error/Forbidden.vue` |

### 4.3 数据与种子

| # | 内容 |
| --- | --- |
| 1 | ~~对齐权限码 `path` 与真实路由~~ **已完成 9 条**（见 2.2 第一类，改在 `seed.py`；共享库历史行未同步） |
| 2 | 为 2.2 第三类列出的 14 个页面补权限码，并加入对应角色的绑定（**需 owner 确认**） |
| 3 | 为 2.2 第二类的 4 个"无页面 MENU"定处置方式（建页 / 并入相邻页 / 降级为操作权限） |
| 4 | ACTION 类权限保留接口地址（用于后端校验），不要与前端路由混用 |
| 5 | 若采用方案 A，新增 `sys_user_token` 建表脚本（共享库需全员同步执行幂等补丁） |

## 五、验收用例

| # | 场景 | 期望 |
| --- | --- | --- |
| 1 | 不带 token 请求 `/api/v1/system/users` | 401，不返回数据 |
| 2 | 以「工人」身份登录后请求 `/api/v1/system/users` | 403（工人权限里没有 `system:user`） |
| 3 | 以「工人」身份登录，查看侧边栏 | 仅出现 物料 / BOM / 工艺路线 及 领料单 / 完工报告；看不到用户、角色、采购、销售 |
| 4 | 「工人」直接手输 URL 访问 `/system/role` | 跳 403，不渲染页面 |
| 5 | 以「管理人员」登录 | 全部菜单与接口可用 |
| 6 | 在角色管理页取消「销售人员」的 `sales:order` 后，用该角色重新登录 | 销售订单菜单消失、接口 403 |
| 7 | 「部长」身份 | 可见各业务菜单，但看不到 用户 / 角色 / 权限 管理 |

## 六、影响面与风险

- **共享库变更**：方案 A 需要加表，必须全员在 Tailscale 连上后执行幂等补丁脚本，否则接口报 500。
- **联调成本**：业务模块接口挂权限需要各 owner 参与，建议先只保护 `system` 模块，观察一周再铺开。
- **登录态结构变更**：`bh-erp-user` 的存储结构会变，需提醒全员清站点数据后重新登录（与之前缓存问题同类）。
- **现有前端全部页面**默认可访问，改造后会出现"以前能点、现在点不了"，需要在群里提前说明。

## 七、遗留项

- 数据范围（本组织 / 仅本人 / 全部）未实现，角色描述中的相关说明目前仅为展示文案。
- 前端 `permissions` 字段目前无人消费，改造后才会真正生效。